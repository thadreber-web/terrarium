"""Terrarium entry point — run a game with scripted or LLM agents.

Usage:
    python run.py --config configs/default.yaml --mode scripted
    python run.py --config configs/default.yaml --mode llm --model Qwen/Qwen2.5-3B-Instruct-AWQ
    python run.py --config configs/default.yaml --mode llm --rounds 20  # sanity check
"""

from __future__ import annotations
import argparse
import sys
import time
import yaml
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from game.engine import GameEngine
from game.scripted import Cooperator, Defector, TitForTat
from game.personas import PERSONAS, AGENT_NAMES
from game.logger import EventLogger
from game.metrics import MetricsComputer, DeceptionDetector
from analysis.visualize import plot_wealth_curves, plot_metrics_over_time

# Scripted agent configs (used only in scripted mode)
SCRIPTED_CONFIGS = [
    ("Vera", "tit_for_tat"),
    ("Kip", "cooperator"),
    ("Sable", "tit_for_tat"),
    ("Marsh", "defector"),
    ("Dove", "cooperator"),
    ("Flint", "defector"),
]


def create_scripted_agents(config: dict) -> tuple[dict, dict]:
    """Create scripted agents keyed by agent_id."""
    agents = {}
    strategies = {}
    for i, (name, strategy) in enumerate(SCRIPTED_CONFIGS):
        aid = f"agent_{i}"
        if strategy == "cooperator":
            agents[aid] = Cooperator()
        elif strategy == "defector":
            agents[aid] = Defector()
        elif strategy == "tit_for_tat":
            agents[aid] = TitForTat()
        strategies[aid] = strategy
    return agents, strategies


def run_game(config: dict, mode: str = "scripted", model_name: str = None,
             game_id: str = None, verbose: bool = False, max_rounds: int = None):
    """Run a single game."""
    if game_id is None:
        game_id = f"game_{int(time.time())}"

    if max_rounds is not None:
        config["game"]["max_rounds"] = max_rounds

    engine = GameEngine(config)
    agent_names = AGENT_NAMES

    engine.setup_agents(agent_names)

    batch_llm = None
    if mode == "scripted":
        agents, strategies = create_scripted_agents(config)
    elif mode == "llm":
        from game.agents import BatchLLMAgent
        batch_llm = BatchLLMAgent(model_name, agent_names)
        agents = batch_llm.agents
        strategies = {f"agent_{i}": name for i, name in enumerate(agent_names)}
    else:
        raise ValueError(f"Unknown mode: {mode}")

    logger = EventLogger("results", game_id)
    metrics = MetricsComputer()
    detector = DeceptionDetector()
    ground_truth_clues = {}

    print(f"\n  TERRARIUM — Game {game_id} ({mode} mode)")
    print(f"  Config: {config.get('_config_path', 'unknown')}")
    print(f"  Agents: {', '.join(agent_names)}")
    print(f"  {'='*50}")

    # Apply pre-solve bonus if configured (gives cooperative momentum)
    if engine.pre_solve_bonus > 0:
        engine.apply_pre_solve_bonus()
        print(f"  Pre-solve bonus: +{engine.pre_solve_bonus} tokens to each agent")

    while not engine.is_game_over():
        if mode == "llm" and batch_llm is not None:
            # Batched LLM inference: gather all views, generate in one call
            summary = _run_round_batched(engine, batch_llm)
        else:
            summary = engine.run_round(agents)

        # Update ground truth clues
        for event in engine.world.event_log:
            if event.event_type == "PUZZLE_CREATED" and event.round_num == engine.world.round_num:
                holders = event.content.get("clue_holders", {})
                puzzle_id = event.content.get("puzzle_id")
                for agent_name, clue_text in holders.items():
                    agent_id = engine._resolve_name_to_id(agent_name)
                    if agent_id:
                        ground_truth_clues[(agent_id, puzzle_id)] = clue_text

        # Scan for deception
        for event in engine.world.event_log:
            if (event.round_num == engine.world.round_num
                    and event.event_type in ("SEND_PUBLIC", "SEND_PRIVATE")):
                detector.scan_message({
                    "agent": event.agent,
                    "round": event.round_num,
                    "content": event.content.get("content", ""),
                    "target": event.content.get("target"),
                }, ground_truth_clues)

        all_events_dicts = [
            {"agent": e.agent, "round": e.round_num, "event_type": e.event_type}
            for e in engine.world.event_log
        ]
        detector.check_promise_fulfillment(all_events_dicts, engine.world.round_num)

        round_metrics = metrics.compute_round_metrics(engine.world)
        logger.log_round(engine.world, summary)

        # Print progress
        rnd = engine.world.round_num
        if verbose or rnd % 10 == 0 or rnd <= 3:
            alive = engine.world.get_alive_agents()
            tokens_str = ", ".join(f"{a.name}:{a.tokens}" for a in alive)
            deaths = summary.get("deaths", [])
            death_str = f" DEATHS: {deaths}" if deaths else ""
            print(f"  R{rnd:3d}: alive={len(alive)} [{tokens_str}]{death_str}")

            # In LLM verbose mode, print raw outputs
            if verbose and mode == "llm" and batch_llm:
                for aid, agent in batch_llm.agents.items():
                    if agent.history and agent.history[-1]["round"] == rnd:
                        raw = agent.history[-1]["raw_output"]
                        name = engine.world.agents[aid].name
                        print(f"        {name}: {raw[:120]}")

    # Game over
    final_stats = engine.get_final_stats()
    final_stats["deception_events"] = len(detector.deception_events)
    final_stats["promises_made"] = len(detector.promises)
    final_stats["promises_broken"] = sum(
        1 for p in detector.promises if p["fulfilled"] is False
    )
    final_stats["false_clues"] = sum(
        1 for s in detector.clue_shares if not s["truthful"]
    )

    logger.log_game_end(final_stats)
    logger.close()

    print(f"\n  {'='*50}")
    print(f"  GAME OVER — Round {final_stats['total_rounds']}")
    print(f"  Survivors: {', '.join(final_stats['survivors']) or 'none'}")
    print(f"  Puzzles solved: {final_stats['puzzles_solved']}")
    print(f"  Deception events: {final_stats['deception_events']}")
    print(f"  Promises: {final_stats['promises_made']} made, {final_stats['promises_broken']} broken")
    print(f"  False clues shared: {final_stats['false_clues']}")

    for name, tokens in final_stats["final_balances"].items():
        status = "ALIVE" if name in final_stats["survivors"] else "DEAD"
        strat = strategies.get(engine._resolve_name_to_id(name), "?")
        print(f"    {name:12s} ({strat:12s}): {tokens:5d} tokens [{status}]")
    print()

    fig_dir = Path("results") / game_id
    fig_dir.mkdir(parents=True, exist_ok=True)

    plot_wealth_curves(
        metrics.round_metrics,
        str(fig_dir / "wealth_curves.png"),
        title=f"Wealth Curves — {game_id}",
    )
    plot_metrics_over_time(
        metrics.round_metrics,
        str(fig_dir / "metrics_over_time.png"),
    )

    print(f"  Figures saved to {fig_dir}/")
    print(f"  Log saved to results/{game_id}/events.jsonl")

    return final_stats, metrics.round_metrics


def _run_round_batched(engine: GameEngine, batch_llm) -> dict:
    """Run one round with batched LLM inference."""
    from game.agents import BatchLLMAgent

    engine.world.round_num += 1
    round_summary = {
        "round": engine.world.round_num,
        "deaths": [],
        "puzzles_created": [],
        "puzzles_solved": [],
        "puzzles_expired": [],
        "actions": {},
    }

    # 1. Generate new puzzles
    new_puzzles = engine.puzzle_engine.generate_puzzles(engine.world)
    engine.world.active_puzzles.extend(new_puzzles)
    round_summary["puzzles_created"] = [p.id for p in new_puzzles]

    # 2. Gather views for all alive agents
    alive = engine.world.get_alive_agents()
    views = {}
    for agent_state in alive:
        views[agent_state.id] = engine.world.get_agent_view(agent_state.id)

    # 3. Batch generate actions
    all_actions = batch_llm.act_batch(views)

    # 4. Execute actions
    for aid, actions in all_actions.items():
        msg_count = 0
        shout_used = False
        action_results = []
        for action in actions:
            from game.engine import SendPublic, SendPrivate, Shout
            if isinstance(action, (SendPublic, SendPrivate)):
                if msg_count >= engine.messages_per_round:
                    continue
                msg_count += 1
            elif isinstance(action, Shout):
                if shout_used:
                    continue
                shout_used = True
            result = engine.execute_action(aid, action)
            action_results.append((action.action_type, result))
        round_summary["actions"][aid] = action_results

    # 5. Check auto-solves (mutual clue sharing)
    auto_solved = engine.check_auto_solves()
    round_summary["puzzles_solved"].extend(
        s["puzzle_id"] for s in auto_solved
    )

    # 6. Passive drain
    deaths = engine.economy.apply_passive_drain(engine.world)
    round_summary["deaths"] = deaths

    # 7. Expire puzzles
    expired = engine.puzzle_engine.expire_puzzles(engine.world)
    round_summary["puzzles_expired"] = [p.id for p in expired]

    # 8. Expire old trade offers
    engine.world.pending_trades = [
        t for t in engine.world.pending_trades
        if not t.is_expired(engine.world.round_num) and t.accepted is None
    ]

    return round_summary


def main():
    parser = argparse.ArgumentParser(description="Terrarium: Multi-Agent LLM Survival")
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--mode", choices=["scripted", "llm"], default="scripted")
    parser.add_argument("--model", default="Qwen/Qwen2.5-3B-Instruct-AWQ")
    parser.add_argument("--game-id", default=None)
    parser.add_argument("--rounds", type=int, default=None, help="Override max rounds")
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    with open(args.config) as f:
        config = yaml.safe_load(f)
    config["_config_path"] = args.config

    run_game(config, args.mode, args.model, args.game_id, args.verbose, args.rounds)


if __name__ == "__main__":
    main()
