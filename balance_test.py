"""Balance testing: run scripted agent games and analyze game economy.

Runs N games with mixed Cooperator/Defector/TitForTat agents and produces
statistics to help tune config parameters.

Usage:
    python balance_test.py [--config configs/default.yaml] [--games 50]
"""

from __future__ import annotations
import argparse
import json
import random
import sys
import yaml
from pathlib import Path
from collections import defaultdict

sys.path.insert(0, str(Path(__file__).parent))

from game.engine import GameEngine
from game.scripted import Cooperator, Defector, TitForTat


AGENT_CONFIGS = [
    ("Scout", "cooperator"),
    ("Trader", "tit_for_tat"),
    ("Oracle", "tit_for_tat"),
    ("Guardian", "cooperator"),
    ("Rogue", "defector"),
    ("Diplomat", "tit_for_tat"),
]


def create_agent(strategy: str):
    if strategy == "cooperator":
        return Cooperator()
    elif strategy == "defector":
        return Defector()
    elif strategy == "tit_for_tat":
        return TitForTat()
    raise ValueError(f"Unknown strategy: {strategy}")


def run_game(config: dict, seed: int | None = None) -> dict:
    """Run a single game and return stats."""
    if seed is not None:
        random.seed(seed)

    engine = GameEngine(config)
    agent_names = [name for name, _ in AGENT_CONFIGS]
    engine.setup_agents(agent_names)

    agents = {}
    strategies = {}
    for i, (name, strategy) in enumerate(AGENT_CONFIGS):
        aid = f"agent_{i}"
        agents[aid] = create_agent(strategy)
        strategies[aid] = strategy

    while not engine.is_game_over():
        engine.run_round(agents)

    stats = engine.get_final_stats()
    stats["strategies"] = {
        engine.world.agents[aid].name: strategies[aid]
        for aid in strategies
    }

    # Per-strategy survival info
    strategy_results = defaultdict(list)
    for aid, strat in strategies.items():
        agent = engine.world.agents[aid]
        strategy_results[strat].append({
            "name": agent.name,
            "survived": agent.alive,
            "final_tokens": agent.tokens,
            "death_round": agent.death_round,
        })
    stats["strategy_results"] = dict(strategy_results)

    # Count cooperative solves
    coop_solves = sum(
        1 for e in engine.world.event_log
        if e.event_type == "PUZZLE_SOLVED" and e.content.get("cooperative")
    )
    solo_solves = sum(
        1 for e in engine.world.event_log
        if e.event_type == "PUZZLE_SOLVED" and not e.content.get("cooperative")
    )
    stats["cooperative_solves"] = coop_solves
    stats["solo_solves"] = solo_solves

    return stats


def analyze_results(all_stats: list[dict]):
    """Print analysis of game balance across all runs."""
    n = len(all_stats)
    print(f"\n{'='*70}")
    print(f"  BALANCE TEST RESULTS ({n} games)")
    print(f"{'='*70}\n")

    # Game length
    rounds = [s["total_rounds"] for s in all_stats]
    print(f"  Game Length:")
    print(f"    Mean: {sum(rounds)/n:.0f} rounds")
    print(f"    Min:  {min(rounds)}  Max: {max(rounds)}")
    target = "150-200"
    in_range = sum(1 for r in rounds if 150 <= r <= 200)
    print(f"    In target range ({target}): {in_range}/{n} ({100*in_range/n:.0f}%)")
    print()

    # Survivors
    survivor_counts = [len(s["survivors"]) for s in all_stats]
    print(f"  Survivors at Game End:")
    print(f"    Mean: {sum(survivor_counts)/n:.1f}")
    print(f"    Min:  {min(survivor_counts)}  Max: {max(survivor_counts)}")
    print()

    # Strategy survival rates
    strategy_survival = defaultdict(lambda: {"games": 0, "survived": 0, "tokens": [], "death_rounds": []})
    for stats in all_stats:
        for strat, results in stats["strategy_results"].items():
            for r in results:
                strategy_survival[strat]["games"] += 1
                if r["survived"]:
                    strategy_survival[strat]["survived"] += 1
                    strategy_survival[strat]["tokens"].append(r["final_tokens"])
                else:
                    strategy_survival[strat]["death_rounds"].append(r["death_round"] or 0)

    print(f"  Strategy Survival Rates:")
    print(f"    {'Strategy':<15} {'Survival%':>10} {'Avg Tokens':>12} {'Avg Death Rd':>13}")
    print(f"    {'-'*50}")
    for strat in ["cooperator", "tit_for_tat", "defector"]:
        s = strategy_survival[strat]
        rate = 100 * s["survived"] / s["games"] if s["games"] else 0
        avg_tok = sum(s["tokens"]) / len(s["tokens"]) if s["tokens"] else 0
        avg_death = sum(s["death_rounds"]) / len(s["death_rounds"]) if s["death_rounds"] else float("inf")
        print(f"    {strat:<15} {rate:>9.1f}% {avg_tok:>11.0f} {avg_death:>12.0f}")
    print()

    # Puzzle economy
    coop = [s["cooperative_solves"] for s in all_stats]
    solo = [s["solo_solves"] for s in all_stats]
    total_solved = [s["puzzles_solved"] for s in all_stats]
    total_expired = [s.get("puzzles_expired", 0) for s in all_stats]
    print(f"  Puzzle Economy:")
    print(f"    Avg puzzles solved/game:   {sum(total_solved)/n:.1f}")
    print(f"    Avg cooperative solves:    {sum(coop)/n:.1f}")
    print(f"    Avg solo solves:           {sum(solo)/n:.1f}")
    print(f"    Avg puzzles expired:       {sum(total_expired)/n:.1f}")
    coop_rate = sum(coop) / max(1, sum(total_solved))
    print(f"    Cooperation rate:          {100*coop_rate:.1f}%")
    print()

    # Balance verdict
    print(f"  BALANCE VERDICT:")
    issues = []

    avg_rounds = sum(rounds) / n
    if avg_rounds < 100:
        issues.append(f"  - Games too short ({avg_rounds:.0f} rounds). Reduce passive_drain or increase starting_tokens.")
    elif avg_rounds > 200:
        issues.append(f"  - Games too long ({avg_rounds:.0f} rounds). Increase passive_drain or reduce starting_tokens.")

    coop_surv = strategy_survival["cooperator"]["survived"] / max(1, strategy_survival["cooperator"]["games"])
    tft_surv = strategy_survival["tit_for_tat"]["survived"] / max(1, strategy_survival["tit_for_tat"]["games"])
    def_surv = strategy_survival["defector"]["survived"] / max(1, strategy_survival["defector"]["games"])

    if coop_surv < 0.3:
        issues.append(f"  - Cooperators dying too much ({100*coop_surv:.0f}%). Increase puzzle_reward.")
    if tft_surv < 0.3:
        issues.append(f"  - Tit-for-tat dying too much ({100*tft_surv:.0f}%). Economy too harsh.")
    if def_surv > 0.7:
        issues.append(f"  - Defectors surviving too easily ({100*def_surv:.0f}%). Free-riding isn't punished enough.")
    if def_surv > coop_surv:
        issues.append(f"  - Defectors survive more than cooperators! Cooperation isn't rewarded enough.")

    if sum(total_solved) / n < 5:
        issues.append(f"  - Very few puzzles solved ({sum(total_solved)/n:.1f}/game). Check puzzle answer matching logic.")

    if not issues:
        print("    BALANCED! Cooperator/TfT survive, defector struggles.")
    else:
        print("    NEEDS TUNING:")
        for issue in issues:
            print(issue)

    print(f"\n{'='*70}\n")

    return {
        "avg_rounds": avg_rounds,
        "avg_survivors": sum(survivor_counts) / n,
        "coop_survival": coop_surv,
        "tft_survival": tft_surv,
        "defector_survival": def_surv,
        "avg_puzzles_solved": sum(total_solved) / n,
        "cooperation_rate": coop_rate,
        "issues": issues,
    }


def main():
    parser = argparse.ArgumentParser(description="Terrarium balance test")
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--games", type=int, default=50)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    with open(args.config) as f:
        config = yaml.safe_load(f)

    print(f"Running {args.games} games with config: {args.config}")

    all_stats = []
    for i in range(args.games):
        stats = run_game(config, seed=i)
        all_stats.append(stats)
        if args.verbose:
            survivors = ", ".join(stats["survivors"]) or "none"
            print(f"  Game {i+1:3d}: {stats['total_rounds']:3d} rounds, "
                  f"solved={stats['puzzles_solved']:2d}, "
                  f"survivors=[{survivors}]")
        elif (i + 1) % 10 == 0:
            print(f"  ... {i+1}/{args.games} games complete")

    verdict = analyze_results(all_stats)

    # Save raw results
    out_path = Path("logs/balance_test_results.json")
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(all_stats, f, indent=2, default=str)
    print(f"Raw results saved to {out_path}")


if __name__ == "__main__":
    main()
