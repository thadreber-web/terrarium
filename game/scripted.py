"""Scripted agents for game engine testing and balance tuning.

Three strategies:
  - Cooperator: Always shares clues, splits puzzles
  - Defector: Withholds clues, tries to solve alone, lies
  - TitForTat: Cooperates initially, mirrors what others do
"""

from __future__ import annotations
import random
from typing import TYPE_CHECKING

from .engine import (
    Action, SendPublic, SendPrivate, Solve, Trade, Pass, AgentInterface,
)

if TYPE_CHECKING:
    pass


class Cooperator:
    """Always shares clues openly, attempts cooperative solves."""

    def act(self, agent_id: str, view: dict) -> list[Action]:
        actions: list[Action] = []

        my_clues = view["your_clues"]  # {puzzle_id: clue_text}
        puzzles = view["active_puzzles"]
        others = view["other_agents"]
        inbox = view["private_messages"]

        # Check inbox for clues others shared with us
        for msg in inbox:
            if msg["round"] == view["round_num"]:
                # Someone sent us info — try to use it to solve
                for puzzle in puzzles:
                    pid = puzzle["id"]
                    if "your_clue" in puzzle:
                        # We have a clue AND received a message — try to solve
                        answer = self._guess_answer(puzzle, msg["content"])
                        if answer and len(actions) < 2:
                            actions.append(Solve(puzzle_id=pid, answer=answer))

        # Share any clues we hold publicly
        if my_clues and len(actions) < 2:
            # Pick a random clue to share
            pid, clue_text = random.choice(list(my_clues.items()))
            matching_puzzle = next((p for p in puzzles if p["id"] == pid), None)
            if matching_puzzle:
                actions.append(SendPublic(
                    message=f"I have a clue for {pid}: {clue_text}. Anyone want to work together?"
                ))

        # If we see someone shared a clue publicly and we have the other half
        for msg in view["public_messages"]:
            if msg["round"] >= view["round_num"] - 2:
                for puzzle in puzzles:
                    pid = puzzle["id"]
                    if pid in msg["content"] and "your_clue" in puzzle and len(actions) < 2:
                        answer = self._guess_answer(puzzle, msg["content"])
                        if answer:
                            actions.append(Solve(puzzle_id=pid, answer=answer))

        if not actions:
            actions.append(Pass())

        return actions[:2]

    def _guess_answer(self, puzzle: dict, other_info: str) -> str | None:
        """Simple keyword-matching to guess the answer from combined clues."""
        my_clue = puzzle.get("your_clue", "")
        combined = (my_clue + " " + other_info).upper()
        return _solve_from_keywords(combined)


class Defector:
    """Withholds clues, tries to solve alone, occasionally lies."""

    def act(self, agent_id: str, view: dict) -> list[Action]:
        actions: list[Action] = []

        puzzles = view["active_puzzles"]
        inbox = view["private_messages"]

        # Try to extract info from messages others send us without reciprocating
        for msg in inbox:
            for puzzle in puzzles:
                pid = puzzle["id"]
                if pid in msg.get("content", "") and "your_clue" in puzzle:
                    answer = self._guess_answer(puzzle, msg["content"])
                    if answer and len(actions) < 2:
                        actions.append(Solve(puzzle_id=pid, answer=answer))

        # Scan public messages for free information
        for msg in view["public_messages"]:
            if msg["round"] >= view["round_num"] - 2:
                for puzzle in puzzles:
                    pid = puzzle["id"]
                    if pid in msg["content"] and "your_clue" in puzzle and len(actions) < 2:
                        answer = self._guess_answer(puzzle, msg["content"])
                        if answer:
                            actions.append(Solve(puzzle_id=pid, answer=answer))

        # Occasionally send misleading public info (lie about clues)
        if random.random() < 0.15 and view["your_clues"] and len(actions) < 2:
            pid = random.choice(list(view["your_clues"].keys()))
            fake_clue = random.choice(["The answer is ZZ___",
                                       "The answer is __XXX",
                                       "The answer is QQ__",
                                       "The answer is ___WW"])
            actions.append(SendPublic(
                message=f"My clue for {pid}: {fake_clue}"
            ))

        # Never share real clues, just pass
        if not actions:
            actions.append(Pass())

        return actions[:2]

    def _guess_answer(self, puzzle: dict, other_info: str) -> str | None:
        my_clue = puzzle.get("your_clue", "")
        combined = (my_clue + " " + other_info).upper()
        return _solve_from_keywords(combined)


class TitForTat:
    """Cooperates initially, mirrors what others do."""

    def __init__(self):
        self.trust: dict[str, float] = {}  # agent_name -> trust score
        self.shared_with: set[str] = set()  # agents we've shared clues with

    def act(self, agent_id: str, view: dict) -> list[Action]:
        actions: list[Action] = []
        puzzles = view["active_puzzles"]
        inbox = view["private_messages"]

        # Update trust based on incoming messages
        for msg in inbox:
            sender = msg["sender"]
            if sender not in self.trust:
                self.trust[sender] = 0.5

            # Positive: they shared info with us
            for puzzle in puzzles:
                if puzzle["id"] in msg.get("content", ""):
                    self.trust[sender] = min(1.0, self.trust[sender] + 0.2)

        # Try to solve if we have enough info
        for msg in inbox:
            if msg["round"] >= view["round_num"] - 2:
                for puzzle in puzzles:
                    pid = puzzle["id"]
                    if pid in msg.get("content", "") and "your_clue" in puzzle:
                        answer = self._guess_answer(puzzle, msg["content"])
                        if answer and len(actions) < 2:
                            actions.append(Solve(puzzle_id=pid, answer=answer))

        # Also check public messages
        for msg in view["public_messages"]:
            if msg["round"] >= view["round_num"] - 2:
                sender = msg["sender"]
                if sender not in self.trust:
                    self.trust[sender] = 0.5
                for puzzle in puzzles:
                    pid = puzzle["id"]
                    if pid in msg["content"] and "your_clue" in puzzle and len(actions) < 2:
                        self.trust[sender] = min(1.0, self.trust[sender] + 0.1)
                        answer = self._guess_answer(puzzle, msg["content"])
                        if answer:
                            actions.append(Solve(puzzle_id=pid, answer=answer))

        # Share clues with trusted agents or publicly if early game
        if view["your_clues"] and len(actions) < 2:
            pid, clue_text = random.choice(list(view["your_clues"].items()))

            # Find the most trusted alive agent we haven't shared with yet
            trusted = sorted(
                [(name, score) for name, score in self.trust.items()
                 if score >= 0.4 and name not in self.shared_with],
                key=lambda x: -x[1],
            )

            if trusted:
                target_name = trusted[0][0]
                actions.append(SendPrivate(
                    target_name=target_name,
                    message=f"I have a clue for {pid}: {clue_text}. Can you help solve it?",
                ))
                self.shared_with.add(target_name)
            elif view["round_num"] <= 10:
                # Early game: cooperate openly to build trust
                actions.append(SendPublic(
                    message=f"I have a clue for {pid}: {clue_text}. Looking for partners."
                ))

        if not actions:
            actions.append(Pass())

        return actions[:2]

    def _guess_answer(self, puzzle: dict, other_info: str) -> str | None:
        my_clue = puzzle.get("your_clue", "")
        combined = (my_clue + " " + other_info).upper()
        return _solve_from_keywords(combined)


# --- Shared puzzle-solving heuristic (letter-fill) ---

import re

_PATTERN_RE = re.compile(r"THE ANSWER IS ([A-Z_]+)")


def _solve_from_keywords(combined_text: str) -> str | None:
    """Overlay letter-fill patterns to reconstruct the answer.

    E.g. "The answer is BL__" + "The answer is __UE" → BLUE
    """
    text = combined_text.upper()
    patterns = _PATTERN_RE.findall(text)
    if not patterns:
        return None

    # All patterns should be the same length for the same puzzle
    max_len = max(len(p) for p in patterns)
    result = ["_"] * max_len

    for pat in patterns:
        for i, ch in enumerate(pat):
            if ch != "_" and i < max_len:
                result[i] = ch

    word = "".join(result)
    if "_" not in word:
        return word
    return None
