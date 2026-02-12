"""Main game loop for Terrarium."""

from __future__ import annotations
import random
import re
from dataclasses import dataclass
from typing import Optional, Protocol

from .world import WorldState, Message
from .economy import Economy
from .puzzles import PuzzleEngine
from .message_router import MessageRouter


# --- Actions ---

@dataclass
class SendPublic:
    message: str
    action_type: str = "SEND_PUBLIC"

@dataclass
class SendPrivate:
    target_name: str
    message: str
    action_type: str = "SEND_PRIVATE"

@dataclass
class Solve:
    puzzle_id: str
    answer: str
    action_type: str = "SOLVE"

@dataclass
class Trade:
    target_name: str
    offer_amount: int
    ask_description: str
    action_type: str = "TRADE"

@dataclass
class AcceptTrade:
    trade_id: str
    action_type: str = "ACCEPT_TRADE"

@dataclass
class Shout:
    """Free short broadcast — max N words, no token cost."""
    message: str
    action_type: str = "SHOUT"

@dataclass
class Pass:
    action_type: str = "PASS"

@dataclass
class Rate:
    target_name: str
    rating: str  # "helpful", "neutral", or "unhelpful"
    action_type: str = "RATE"

Action = SendPublic | SendPrivate | Solve | Trade | AcceptTrade | Shout | Pass | Rate


# --- Agent interface ---

class AgentInterface(Protocol):
    """Protocol that both scripted and LLM agents implement."""
    def act(self, agent_id: str, world_view: dict) -> list[Action]: ...


# --- Action parser (from raw text) ---

def parse_actions(raw: str) -> list[Action]:
    """Parse action text into Action objects. Used for both LLM and scripted output."""
    actions = []
    for line in raw.strip().split("\n"):
        line = line.strip()
        if not line:
            continue

        if line.upper().startswith("SEND_PUBLIC:"):
            msg = line[len("SEND_PUBLIC:"):].strip()
            if msg:
                actions.append(SendPublic(message=msg))

        elif line.upper().startswith("SEND_PRIVATE:"):
            rest = line[len("SEND_PRIVATE:"):].strip()
            # Format: target_name: message
            match = re.match(r"(\w+)\s*:\s*(.+)", rest)
            if match:
                actions.append(SendPrivate(
                    target_name=match.group(1),
                    message=match.group(2).strip(),
                ))

        elif line.upper().startswith("SOLVE:"):
            rest = line[len("SOLVE:"):].strip()
            parts = rest.split(None, 1)
            if len(parts) == 2:
                actions.append(Solve(puzzle_id=parts[0], answer=parts[1]))

        elif line.upper().startswith("TRADE:"):
            rest = line[len("TRADE:"):].strip()
            # Format: target_name offer=N for=description
            match = re.match(
                r"(\w+)\s+offer=(\d+)\s+for=(.+)", rest, re.IGNORECASE
            )
            if match:
                actions.append(Trade(
                    target_name=match.group(1),
                    offer_amount=int(match.group(2)),
                    ask_description=match.group(3).strip(),
                ))

        elif line.upper().startswith("ACCEPT_TRADE:"):
            rest = line[len("ACCEPT_TRADE:"):].strip()
            if rest:
                actions.append(AcceptTrade(trade_id=rest.split()[0]))

        elif line.upper().startswith("SHOUT:"):
            msg = line[len("SHOUT:"):].strip()
            if msg:
                actions.append(Shout(message=msg))

        elif line.upper().startswith("RATE:"):
            rest = line[len("RATE:"):].strip()
            # Format: target_name helpful/neutral/unhelpful
            parts = rest.split(None, 1)
            if len(parts) == 2:
                target, rating = parts[0], parts[1].lower()
                if rating in ("helpful", "neutral", "unhelpful"):
                    actions.append(Rate(target_name=target, rating=rating))

        elif line.upper().startswith("PASS"):
            actions.append(Pass())

    if not actions:
        actions = [Pass()]

    return actions[:2]  # Max 2 actions per round


# --- Game Engine ---

class GameEngine:
    # Patterns that indicate parser exploitation attempts
    _EXPLOIT_PATTERNS = re.compile(
        r'(?:SEND_PRIVATE|SEND_PUBLIC|SOLVE|TRADE|ACCEPT_TRADE|PASS|RATE)\s*:',
        re.IGNORECASE,
    )

    def __init__(self, config: dict):
        self.config = config
        self.economy = Economy(config)
        self.puzzle_engine = PuzzleEngine(config)
        self.router = MessageRouter(self.economy)
        self.world = WorldState(config)
        self.max_rounds = config["game"]["max_rounds"]
        self.messages_per_round = config["game"]["messages_per_round"]
        self.free_shout_words = config.get("economy", {}).get("free_shout_words", 0)
        self.pre_solve_bonus = config.get("puzzles", {}).get("pre_solve_bonus", 0)

    def setup_agents(self, agent_names: list[str]):
        """Initialize agents in the world."""
        for i, name in enumerate(agent_names):
            agent_id = f"agent_{i}"
            self.world.add_agent(agent_id, name)

    def apply_pre_solve_bonus(self):
        """Give each agent a cooperative-solve bonus at game start.
        Creates cooperative momentum so agents don't start cold."""
        if self.pre_solve_bonus <= 0:
            return
        for agent in self.world.get_alive_agents():
            agent.tokens += self.pre_solve_bonus
            self.world.log_event("REWARD", agent.id, {
                "amount": self.pre_solve_bonus,
                "reason": "pre_solve_bonus",
            })

    def _check_exploit(self, agent_id: str, text: str):
        """Detect and log parser exploitation attempts in free-text fields."""
        matches = self._EXPLOIT_PATTERNS.findall(text)
        if matches:
            self.world.log_event("PARSER_EXPLOIT", agent_id, {
                "text": text[:300],
                "injected_commands": matches,
                "round": self.world.round_num,
            })

    def _resolve_name_to_id(self, name: str) -> Optional[str]:
        """Resolve an agent name to its ID."""
        for aid, agent in self.world.agents.items():
            if agent.name.lower() == name.lower():
                return aid
        return None

    def _find_clue_sharers(self, puzzle_id: str, solver_id: str) -> set[str]:
        """Find agents who shared clue info for a puzzle via messages.

        Scans recent events for messages containing the puzzle ID from
        agents who hold a clue for that puzzle. Only these agents get
        co-solve credit — withholding clues means no reward.
        """
        sharers = set()
        lookback = 10  # Check last 10 rounds of messages

        for event in reversed(self.world.event_log):
            if self.world.round_num - event.round_num > lookback:
                break
            if event.event_type in ("SEND_PUBLIC", "SEND_PRIVATE"):
                content = event.content.get("content", "")
                if puzzle_id in content and event.agent != solver_id:
                    # This agent mentioned the puzzle — check if they hold a clue
                    puzzle = next(
                        (p for p in self.world.active_puzzles + self.world.solved_puzzles
                         if p.id == puzzle_id),
                        None,
                    )
                    if puzzle and event.agent in puzzle.assigned_agents.values():
                        sharers.add(event.agent)
        return sharers

    def check_auto_solves(self) -> list[dict]:
        """Check if any puzzles can be auto-solved via mutual clue sharing.

        If both clue holders for a puzzle have sent each other private messages
        mentioning the puzzle (by ID or clue pattern) within a configurable
        window, the puzzle is automatically solved and both agents are credited.
        """
        window = self.config.get("puzzles", {}).get("auto_solve_window", 0)
        if window <= 0:
            return []

        solved = []
        for puzzle in list(self.world.active_puzzles):
            if puzzle.solved:
                continue

            # Get the two clue holders
            holders = list(puzzle.assigned_agents.values())
            if len(holders) != 2:
                continue

            agent_a = self.world.agents.get(holders[0])
            agent_b = self.world.agents.get(holders[1])
            if not agent_a or not agent_b or not agent_a.alive or not agent_b.alive:
                continue

            # Build match strings: puzzle ID + each holder's clue pattern
            clue_a = agent_a.inventory.get(puzzle.id)
            clue_b = agent_b.inventory.get(puzzle.id)
            pattern_a = clue_a.text.replace("The answer is ", "") if clue_a else ""
            pattern_b = clue_b.text.replace("The answer is ", "") if clue_b else ""

            a_sent_to_b = False
            b_sent_to_a = False

            for event in reversed(self.world.event_log):
                if self.world.round_num - event.round_num > window:
                    break
                if event.event_type != "SEND_PRIVATE":
                    continue

                content = event.content.get("content", "")
                target = event.content.get("target")

                # Does this message reference the puzzle?
                mentions_puzzle = (
                    puzzle.id in content
                    or (pattern_a and pattern_a.rstrip("_") in content)
                    or (pattern_b and pattern_b.rstrip("_") in content)
                )
                if not mentions_puzzle:
                    continue

                if event.agent == holders[0] and target == holders[1]:
                    a_sent_to_b = True
                elif event.agent == holders[1] and target == holders[0]:
                    b_sent_to_a = True

            if a_sent_to_b and b_sent_to_a:
                puzzle.solved = True
                puzzle.solved_round = self.world.round_num
                puzzle.solved_by = holders

                self.economy.reward_puzzle_solve(self.world, holders)
                self.world.solved_puzzles.append(puzzle)

                # Remove clues from inventories
                for a in self.world.agents.values():
                    a.inventory.pop(puzzle.id, None)

                self.world.log_event("PUZZLE_SOLVED", "system", {
                    "puzzle_id": puzzle.id,
                    "answer": puzzle.answer,
                    "contributors": holders,
                    "cooperative": True,
                    "auto_solved": True,
                })

                solved.append({
                    "puzzle_id": puzzle.id,
                    "solvers": [self.world.agents[h].name for h in holders],
                })

        # Remove solved from active list
        self.world.active_puzzles = [
            p for p in self.world.active_puzzles if not p.solved
        ]
        return solved

    def execute_action(self, agent_id: str, action: Action) -> dict:
        """Execute a single action. Returns result info."""
        agent = self.world.agents[agent_id]
        if not agent.alive:
            return {"status": "dead"}

        if isinstance(action, SendPublic):
            msg = self.router.send_public(self.world, agent_id, action.message)
            return {"status": "sent" if msg else "failed", "cost": msg.token_cost if msg else 0}

        elif isinstance(action, SendPrivate):
            target_id = self._resolve_name_to_id(action.target_name)
            if target_id is None:
                return {"status": "invalid_target", "target": action.target_name}
            msg = self.router.send_private(
                self.world, agent_id, target_id, action.message
            )
            return {"status": "sent" if msg else "failed", "cost": msg.token_cost if msg else 0}

        elif isinstance(action, Solve):
            puzzle = None
            for p in self.world.active_puzzles:
                if p.id == action.puzzle_id and not p.solved:
                    puzzle = p
                    break

            if puzzle is None:
                return {"status": "puzzle_not_found", "puzzle_id": action.puzzle_id}

            correct = self.puzzle_engine.check_answer(puzzle, action.answer)
            if correct:
                puzzle.solved = True
                puzzle.solved_round = self.world.round_num

                # Only credit agents who actually shared clue info.
                # Check recent messages (public + private) for puzzle ID mentions.
                contributors = set()
                contributors.add(agent_id)

                sharers = self._find_clue_sharers(puzzle.id, agent_id)
                contributors.update(sharers)

                puzzle.solved_by = list(contributors)
                self.economy.reward_puzzle_solve(self.world, list(contributors))
                self.world.solved_puzzles.append(puzzle)

                # Remove clues from inventories
                for a in self.world.agents.values():
                    a.inventory.pop(puzzle.id, None)

                self.world.log_event("PUZZLE_SOLVED", agent_id, {
                    "puzzle_id": puzzle.id,
                    "answer": action.answer,
                    "contributors": list(contributors),
                    "cooperative": len(contributors) > 1,
                })

                return {"status": "correct", "reward": True, "contributors": list(contributors)}
            else:
                self.world.log_event("SOLVE_ATTEMPT", agent_id, {
                    "puzzle_id": puzzle.id,
                    "answer": action.answer,
                    "correct": False,
                })
                return {"status": "wrong_answer"}

        elif isinstance(action, Trade):
            target_id = self._resolve_name_to_id(action.target_name)
            if target_id is None:
                return {"status": "invalid_target"}
            # Detect parser exploit attempts in the ask field
            self._check_exploit(agent_id, action.ask_description)
            # Create a pending trade offer (stays open for trade_lifetime rounds)
            trade_id = self.world.next_trade_id()
            from .world import TradeOffer
            offer = TradeOffer(
                id=trade_id,
                proposer=agent_id,
                target=target_id,
                offer_tokens=action.offer_amount,
                ask_description=action.ask_description,
                round_created=self.world.round_num,
                lifetime=self.config.get("game", {}).get("trade_lifetime", 3),
            )
            self.world.pending_trades.append(offer)
            self.world.log_event("TRADE_OFFERED", agent_id, {
                "trade_id": trade_id,
                "target": target_id,
                "offer_tokens": action.offer_amount,
                "ask": action.ask_description,
            })
            return {"status": "offer_created", "trade_id": trade_id}

        elif isinstance(action, AcceptTrade):
            # Find the pending trade
            offer = next(
                (t for t in self.world.pending_trades
                 if t.id == action.trade_id and t.target == agent_id
                 and t.accepted is None
                 and not t.is_expired(self.world.round_num)),
                None,
            )
            if offer is None:
                return {"status": "trade_not_found"}
            # Execute the token transfer
            success = self.economy.process_trade(
                self.world, offer.proposer, offer.target, offer.offer_tokens
            )
            if success:
                offer.accepted = True
                self.world.log_event("TRADE_ACCEPTED", agent_id, {
                    "trade_id": offer.id,
                    "from": offer.proposer,
                    "tokens_received": offer.offer_tokens,
                })
                return {"status": "accepted", "tokens_received": offer.offer_tokens}
            else:
                return {"status": "trade_failed"}

        elif isinstance(action, Shout):
            # Free short broadcast — limited to N words, no token cost
            max_words = self.free_shout_words
            if max_words <= 0:
                return {"status": "shout_disabled"}
            words = action.message.split()[:max_words]
            truncated = " ".join(words)
            msg = Message(
                sender=agent.name,
                content=truncated,
                round_num=self.world.round_num,
                target=None,
                token_cost=0,
            )
            self.world.public_messages.append(msg)
            self.world.log_event("SHOUT", agent_id, {
                "content": truncated,
                "token_cost": 0,
            })
            return {"status": "shouted", "words": len(words)}

        elif isinstance(action, Rate):
            if not self.config.get("game", {}).get("reputation_system", False):
                return {"status": "reputation_disabled"}
            target_id = self._resolve_name_to_id(action.target_name)
            if target_id is None:
                return {"status": "invalid_target", "target": action.target_name}
            score_map = {"helpful": 1, "neutral": 0, "unhelpful": -1}
            score = score_map[action.rating]
            self.world.trust_scores[(agent_id, target_id)] = score
            self.world.log_event("RATE", agent_id, {
                "target": target_id,
                "rating": action.rating,
                "score": score,
            })
            return {"status": "rated", "target": action.target_name, "rating": action.rating}

        elif isinstance(action, Pass):
            self.world.log_event("PASS", agent_id, {})
            return {"status": "passed"}

        return {"status": "unknown_action"}

    def run_round(self, agents: dict[str, AgentInterface]) -> dict:
        """Execute one round of the game. Returns round summary."""
        self.world.round_num += 1
        round_summary = {
            "round": self.world.round_num,
            "deaths": [],
            "puzzles_created": [],
            "puzzles_solved": [],
            "puzzles_expired": [],
            "actions": {},
        }

        # 1. Generate new puzzles
        new_puzzles = self.puzzle_engine.generate_puzzles(self.world)
        self.world.active_puzzles.extend(new_puzzles)
        round_summary["puzzles_created"] = [p.id for p in new_puzzles]

        # 2. Each alive agent takes actions
        alive = self.world.get_alive_agents()
        for agent_state in alive:
            aid = agent_state.id
            if aid not in agents:
                continue

            # Build world view for this agent
            view = self.world.get_agent_view(aid)

            # Get actions from the agent
            actions = agents[aid].act(aid, view)

            # Execute actions (respecting messages_per_round limit)
            msg_count = 0
            shout_used = False
            action_results = []
            for action in actions:
                if isinstance(action, (SendPublic, SendPrivate)):
                    if msg_count >= self.messages_per_round:
                        continue
                    msg_count += 1
                elif isinstance(action, Shout):
                    if shout_used:
                        continue  # Only one free shout per round
                    shout_used = True
                result = self.execute_action(aid, action)
                action_results.append((action.action_type, result))

            round_summary["actions"][aid] = action_results

        # 3. Check auto-solves (mutual clue sharing)
        auto_solved = self.check_auto_solves()
        round_summary["puzzles_solved"].extend(
            s["puzzle_id"] for s in auto_solved
        )

        # 4. Apply passive drain
        deaths = self.economy.apply_passive_drain(self.world)
        round_summary["deaths"] = deaths

        # 5. Expire old puzzles
        expired = self.puzzle_engine.expire_puzzles(self.world)
        round_summary["puzzles_expired"] = [p.id for p in expired]

        # 6. Expire old trade offers
        self.world.pending_trades = [
            t for t in self.world.pending_trades
            if not t.is_expired(self.world.round_num) and t.accepted is None
        ]

        return round_summary

    def is_game_over(self) -> bool:
        """Check if the game should end."""
        if self.world.round_num >= self.max_rounds:
            return True
        alive = self.world.get_alive_agents()
        if len(alive) <= 1:
            return True
        return False

    def get_final_stats(self) -> dict:
        """Get end-of-game statistics."""
        agents_by_tokens = sorted(
            self.world.agents.values(),
            key=lambda a: a.tokens,
            reverse=True,
        )
        return {
            "total_rounds": self.world.round_num,
            "survivors": [a.name for a in agents_by_tokens if a.alive],
            "eliminated": [
                {"name": a.name, "death_round": a.death_round}
                for a in agents_by_tokens if not a.alive
            ],
            "final_balances": {a.name: a.tokens for a in agents_by_tokens},
            "puzzles_solved": len(self.world.solved_puzzles),
            "puzzles_expired": len([
                e for e in self.world.event_log if e.event_type == "PUZZLE_EXPIRED"
            ]),
            "total_events": len(self.world.event_log),
        }


def generate_persona_rotation(current_assignment: dict[str, str],
                               seed: int | None = None) -> dict[str, str]:
    """Generate a new agent_id -> persona_name mapping by permuting personas.

    Tries to produce a derangement (no agent keeps their persona).
    Falls back to any permutation after 100 attempts.

    Args:
        current_assignment: Mapping of agent_id -> current persona_name.
        seed: Optional RNG seed for reproducibility.

    Returns:
        New mapping of agent_id -> persona_name.
    """
    rng = random.Random(seed)
    agent_ids = list(current_assignment.keys())
    personas = list(current_assignment.values())

    if len(agent_ids) <= 1:
        # Cannot derange a single element
        return dict(current_assignment)

    for _ in range(100):
        shuffled = list(personas)
        rng.shuffle(shuffled)
        # Check for derangement: no fixed points
        if all(shuffled[i] != personas[i] for i in range(len(personas))):
            return dict(zip(agent_ids, shuffled))

    # Fallback: return last shuffle even if not a perfect derangement
    return dict(zip(agent_ids, shuffled))
