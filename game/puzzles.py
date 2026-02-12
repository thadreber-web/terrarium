"""Puzzle generation system for Terrarium.

Each puzzle has N clues distributed to different agents.
Each clue alone is ambiguous; combined clues uniquely identify the answer.
"""

from __future__ import annotations
import random
import string
from typing import TYPE_CHECKING

from .world import Puzzle, Clue

if TYPE_CHECKING:
    from .world import WorldState

# ---------------------------------------------------------------------------
# Puzzle bank — letter-fill style
#
# Each clue reveals part of the answer.  Combining two clues makes the full
# word obvious even for small LLMs (3B) because the task is mechanical
# pattern-matching, not inferential reasoning.
#
# Format: (["clue1 text", "clue2 text"], "ANSWER")
# ---------------------------------------------------------------------------
PUZZLE_BANK = [
    # Colors
    {
        "category": "color",
        "puzzles": [
            (["The answer is BL__", "The answer is __UE"], "BLUE"),
            (["The answer is R__", "The answer is _ED"], "RED"),
            (["The answer is GR___", "The answer is __EEN"], "GREEN"),
            (["The answer is YEL___", "The answer is ___LOW"], "YELLOW"),
            (["The answer is PUR___", "The answer is ___PLE"], "PURPLE"),
            (["The answer is OR____", "The answer is __ANGE"], "ORANGE"),
            (["The answer is WH___", "The answer is __ITE"], "WHITE"),
            (["The answer is BL___", "The answer is __ACK"], "BLACK"),
            (["The answer is PI__", "The answer is __NK"], "PINK"),
            (["The answer is GO__", "The answer is __LD"], "GOLD"),
        ],
    },
    # Animals
    {
        "category": "animal",
        "puzzles": [
            (["The answer is D__", "The answer is _OG"], "DOG"),
            (["The answer is C__", "The answer is _AT"], "CAT"),
            (["The answer is BI__", "The answer is __RD"], "BIRD"),
            (["The answer is FI__", "The answer is __SH"], "FISH"),
            (["The answer is SP____", "The answer is __IDER"], "SPIDER"),
            (["The answer is TUR___", "The answer is ___TLE"], "TURTLE"),
            (["The answer is ZE___", "The answer is __BRA"], "ZEBRA"),
            (["The answer is ELE_____", "The answer is ___PHANT"], "ELEPHANT"),
            (["The answer is KAN______", "The answer is ___GAROO"], "KANGAROO"),
            (["The answer is LI__", "The answer is __ON"], "LION"),
        ],
    },
    # Numbers
    {
        "category": "number",
        "puzzles": [
            (["The answer is SE___", "The answer is __VEN"], "SEVEN"),
            (["The answer is DO___", "The answer is __ZEN"], "DOZEN"),
            (["The answer is TH___", "The answer is __REE"], "THREE"),
            (["The answer is HUN____", "The answer is ___DRED"], "HUNDRED"),
            (["The answer is THIR____", "The answer is ____TEEN"], "THIRTEEN"),
            (["The answer is S__", "The answer is _IX"], "SIX"),
            (["The answer is EI___", "The answer is __GHT"], "EIGHT"),
            (["The answer is TWE___", "The answer is ___NTY"], "TWENTY"),
            (["The answer is FI__", "The answer is __VE"], "FIVE"),
            (["The answer is O__", "The answer is _NE"], "ONE"),
        ],
    },
    # Objects
    {
        "category": "object",
        "puzzles": [
            (["The answer is KET___", "The answer is ___TLE"], "KETTLE"),
            (["The answer is BO__", "The answer is __OK"], "BOOK"),
            (["The answer is CL___", "The answer is __OCK"], "CLOCK"),
            (["The answer is PI___", "The answer is __ANO"], "PIANO"),
            (["The answer is C__", "The answer is _UP"], "CUP"),
            (["The answer is KN___", "The answer is __IFE"], "KNIFE"),
            (["The answer is CH___", "The answer is __AIR"], "CHAIR"),
            (["The answer is COM______", "The answer is ___PUTER"], "COMPUTER"),
            (["The answer is GUI___", "The answer is ___TAR"], "GUITAR"),
            (["The answer is SI__", "The answer is __NK"], "SINK"),
        ],
    },
    # 3-clue puzzles (harder, for later configs)
    {
        "category": "place",
        "puzzles": [
            (["The answer is PA___", "The answer is __R_S", "The answer is ___IS"], "PARIS"),
            (["The answer is JA___", "The answer is __P_N", "The answer is ___AN"], "JAPAN"),
            (["The answer is EG___", "The answer is __Y_T", "The answer is ___PT"], "EGYPT"),
            (["The answer is BR____", "The answer is __AZ__", "The answer is ____IL"], "BRAZIL"),
            (["The answer is U__", "The answer is _S_", "The answer is __A"], "USA"),
        ],
    },
]


class PuzzleEngine:
    def __init__(self, config: dict):
        self.clues_per_puzzle = config["puzzles"]["clues_per_puzzle"]
        self.clues_per_round = config["puzzles"]["clues_per_round"]
        self.puzzle_lifetime = config["puzzles"]["puzzle_lifetime"]
        self._puzzle_counter = 0
        self._used_puzzles: set[str] = set()
        # Build pool of available puzzles matching clue count
        self._pool = []
        for category in PUZZLE_BANK:
            for clue_texts, answer in category["puzzles"]:
                if len(clue_texts) == self.clues_per_puzzle:
                    self._pool.append((category["category"], clue_texts, answer))
        random.shuffle(self._pool)
        self._pool_index = 0

    def _next_puzzle_id(self) -> str:
        self._puzzle_counter += 1
        letter = random.choice(string.ascii_uppercase)
        return f"{letter}-{self._puzzle_counter}"

    def generate_puzzles(self, world: WorldState) -> list[Puzzle]:
        """Generate new puzzles for this round and assign clues to agents."""
        alive_agents = world.get_alive_agents()
        if len(alive_agents) < self.clues_per_puzzle:
            return []

        new_puzzles = []
        for _ in range(self.clues_per_round):
            # Pick a puzzle from the pool
            if self._pool_index >= len(self._pool):
                # Reshuffle and reuse
                random.shuffle(self._pool)
                self._pool_index = 0

            category, clue_texts, answer = self._pool[self._pool_index]
            self._pool_index += 1

            puzzle_id = self._next_puzzle_id()

            # Pick agents to receive clues
            recipients = random.sample(alive_agents, self.clues_per_puzzle)

            clues = []
            assigned = {}
            for i, (agent, text) in enumerate(zip(recipients, clue_texts)):
                clue = Clue(puzzle_id=puzzle_id, clue_index=i, text=text)
                clues.append(clue)
                assigned[i] = agent.id
                # Add to agent inventory
                agent.inventory[puzzle_id] = clue

            desc = (f"Puzzle {puzzle_id} ({category}): Each clue shows part of the word. "
                    f"Combine the {len(clues)} letter patterns to spell the answer.")
            puzzle = Puzzle(
                id=puzzle_id,
                clues=clues,
                answer=answer,
                description=desc,
                created_round=world.round_num,
                lifetime=self.puzzle_lifetime,
                assigned_agents=assigned,
            )
            new_puzzles.append(puzzle)

            world.log_event("PUZZLE_CREATED", "system", {
                "puzzle_id": puzzle_id,
                "category": category,
                "answer": answer,
                "clue_holders": {
                    agent.name: text
                    for agent, text in zip(recipients, clue_texts)
                },
            })

        return new_puzzles

    def check_answer(self, puzzle: Puzzle, answer: str) -> bool:
        """Check if an answer is correct."""
        return answer.strip().upper() == puzzle.answer.upper()

    def expire_puzzles(self, world: WorldState) -> list[Puzzle]:
        """Remove expired puzzles and clean up inventory."""
        expired = []
        still_active = []
        for puzzle in world.active_puzzles:
            if puzzle.is_expired(world.round_num) and not puzzle.solved:
                expired.append(puzzle)
                # Remove clues from agent inventories
                for agent in world.agents.values():
                    agent.inventory.pop(puzzle.id, None)
                world.log_event("PUZZLE_EXPIRED", "system", {
                    "puzzle_id": puzzle.id,
                })
            else:
                still_active.append(puzzle)
        world.active_puzzles = still_active
        return expired
