"""Tests for the eavesdropper mechanic (Condition 4).

The eavesdropper is a designated agent that can read all private messages
between other agents.  Controlled by config key ``game.eavesdropper``.
"""

from __future__ import annotations

import pytest

from game.world import WorldState, Message


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base_config(**game_overrides) -> dict:
    """Return a minimal config dict with optional game-section overrides."""
    cfg = {
        "agents": {"starting_tokens": 100},
        "game": {
            "max_rounds": 10,
            "history_window": 10,
            "transparent_balances": True,
            "trade_lifetime": 3,
        },
    }
    cfg["game"].update(game_overrides)
    return cfg


def _setup_world(config: dict) -> WorldState:
    """Create a world with three agents and some private messages."""
    ws = WorldState(config)
    ws.add_agent("agent_0", "Vera")
    ws.add_agent("agent_1", "Kip")
    ws.add_agent("agent_2", "Sable")
    ws.round_num = 5

    # Private messages between Vera and Kip (NOT involving Sable)
    ws.private_messages["agent_0"].append(
        Message(sender="Kip", content="I have clue BL__ for puzzle A-1",
                round_num=4, target="agent_0")
    )
    ws.private_messages["agent_1"].append(
        Message(sender="Vera", content="Thanks! My clue is __UE",
                round_num=4, target="agent_1")
    )
    # A message in Sable's own inbox (from Kip to Sable)
    ws.private_messages["agent_2"].append(
        Message(sender="Kip", content="Hey Sable, team up?",
                round_num=5, target="agent_2")
    )
    return ws


# ---------------------------------------------------------------------------
# Tests: WorldState.get_agent_view() — intercepted_messages
# ---------------------------------------------------------------------------

class TestEavesdropperView:
    """get_agent_view should include intercepted_messages for the eavesdropper."""

    def test_eavesdropper_gets_intercepted_messages(self):
        """When agent IS the eavesdropper, view contains intercepted_messages."""
        config = _base_config(eavesdropper="agent_2")
        ws = _setup_world(config)

        view = ws.get_agent_view("agent_2")

        assert "intercepted_messages" in view
        assert isinstance(view["intercepted_messages"], list)
        assert len(view["intercepted_messages"]) > 0

    def test_intercepted_messages_are_from_others_inboxes(self):
        """intercepted_messages should contain messages from other agents' inboxes,
        NOT from the eavesdropper's own inbox."""
        config = _base_config(eavesdropper="agent_2")
        ws = _setup_world(config)

        view = ws.get_agent_view("agent_2")
        intercepted = view["intercepted_messages"]

        # Should contain messages from agent_0's and agent_1's inboxes
        senders = {m["sender"] for m in intercepted}
        assert "Kip" in senders or "Vera" in senders

        # Should NOT contain messages from the eavesdropper's own inbox
        contents = [m["content"] for m in intercepted]
        assert "Hey Sable, team up?" not in contents

    def test_intercepted_messages_format(self):
        """Each intercepted message should have sender, receiver, content, round."""
        config = _base_config(eavesdropper="agent_2")
        ws = _setup_world(config)

        view = ws.get_agent_view("agent_2")
        for msg in view["intercepted_messages"]:
            assert "sender" in msg
            assert "receiver" in msg
            assert "content" in msg
            assert "round" in msg

    def test_intercepted_messages_include_receiver(self):
        """Each intercepted message should identify who received it."""
        config = _base_config(eavesdropper="agent_2")
        ws = _setup_world(config)

        view = ws.get_agent_view("agent_2")
        receivers = {m["receiver"] for m in view["intercepted_messages"]}
        # Messages went to Vera (agent_0) and Kip (agent_1)
        assert "Vera" in receivers or "Kip" in receivers

    def test_non_eavesdropper_has_no_intercepted_messages(self):
        """When agent is NOT the eavesdropper, view should NOT contain intercepted_messages."""
        config = _base_config(eavesdropper="agent_2")
        ws = _setup_world(config)

        view_vera = ws.get_agent_view("agent_0")
        view_kip = ws.get_agent_view("agent_1")

        assert "intercepted_messages" not in view_vera
        assert "intercepted_messages" not in view_kip

    def test_no_eavesdropper_config_means_no_field(self):
        """When eavesdropper is not configured, no agent gets intercepted_messages."""
        config = _base_config()  # no eavesdropper key
        ws = _setup_world(config)

        for aid in ["agent_0", "agent_1", "agent_2"]:
            view = ws.get_agent_view(aid)
            assert "intercepted_messages" not in view

    def test_intercepted_messages_sorted_by_round(self):
        """intercepted_messages should be sorted by round number."""
        config = _base_config(eavesdropper="agent_2")
        ws = WorldState(config)
        ws.add_agent("agent_0", "Vera")
        ws.add_agent("agent_1", "Kip")
        ws.add_agent("agent_2", "Sable")
        ws.round_num = 10

        # Add messages at different rounds
        ws.private_messages["agent_0"].append(
            Message(sender="Kip", content="msg round 7", round_num=7, target="agent_0")
        )
        ws.private_messages["agent_1"].append(
            Message(sender="Vera", content="msg round 3", round_num=3, target="agent_1")
        )
        ws.private_messages["agent_0"].append(
            Message(sender="Kip", content="msg round 5", round_num=5, target="agent_0")
        )

        view = ws.get_agent_view("agent_2")
        rounds = [m["round"] for m in view["intercepted_messages"]]
        assert rounds == sorted(rounds)

    def test_intercepted_messages_limited_by_history_window(self):
        """intercepted_messages should be limited to the last history_window messages."""
        config = _base_config(eavesdropper="agent_2", history_window=3)
        ws = WorldState(config)
        ws.add_agent("agent_0", "Vera")
        ws.add_agent("agent_1", "Kip")
        ws.add_agent("agent_2", "Sable")
        ws.round_num = 20

        # Add more messages than history_window
        for i in range(10):
            ws.private_messages["agent_0"].append(
                Message(sender="Kip", content=f"message {i}", round_num=i + 1, target="agent_0")
            )

        view = ws.get_agent_view("agent_2")
        assert len(view["intercepted_messages"]) <= 3


# ---------------------------------------------------------------------------
# Tests: Prompt building — intercepted messages in agent prompt
# ---------------------------------------------------------------------------

class TestEavesdropperPrompt:
    """_build_prompt should include intercepted messages when present in view."""

    def _minimal_view(self, **overrides) -> dict:
        """Return the smallest valid game view for prompt building."""
        view = {
            "round_num": 5,
            "max_rounds": 10,
            "your_tokens": 100,
            "your_clues": {},
            "active_puzzles": [],
            "other_agents": {},
            "public_messages": [],
            "private_messages": [],
        }
        view.update(overrides)
        return view

    def test_prompt_includes_intercepted_section(self):
        """When intercepted_messages exists in view, prompt should contain
        an 'Intercepted' section."""
        from unittest.mock import MagicMock
        from game.agents import LLMAgent

        llm = MagicMock()
        agent = LLMAgent(llm, "Sable", "agent_2")

        view = self._minimal_view(intercepted_messages=[
            {"sender": "Vera", "receiver": "Kip", "content": "I have clue BL__ for puzzle A-1", "round": 5},
            {"sender": "Kip", "receiver": "Vera", "content": "Thanks! My clue is __UE", "round": 5},
        ])

        prompt = agent._build_prompt(view)

        assert "Intercepted" in prompt
        assert "Vera->Kip" in prompt or "Vera→Kip" in prompt
        assert "BL__" in prompt

    def test_prompt_no_intercepted_when_absent(self):
        """When intercepted_messages is NOT in view, prompt should not have the section."""
        from unittest.mock import MagicMock
        from game.agents import LLMAgent

        llm = MagicMock()
        agent = LLMAgent(llm, "Vera", "agent_0")

        view = self._minimal_view()  # no intercepted_messages key

        prompt = agent._build_prompt(view)

        assert "Intercepted" not in prompt

    def test_prompt_limits_to_3_intercepted(self):
        """Prompt should show at most 3 intercepted messages."""
        from unittest.mock import MagicMock
        from game.agents import LLMAgent

        llm = MagicMock()
        agent = LLMAgent(llm, "Sable", "agent_2")

        msgs = [
            {"sender": "Vera", "receiver": "Kip", "content": f"message {i}", "round": i}
            for i in range(6)
        ]
        view = self._minimal_view(intercepted_messages=msgs)

        prompt = agent._build_prompt(view)

        # Count occurrences of the intercepted message pattern
        import re
        matches = re.findall(r"Vera->Kip:", prompt)
        assert len(matches) <= 3

    def test_prompt_truncates_content_to_60_chars(self):
        """Intercepted message content should be truncated to 60 characters."""
        from unittest.mock import MagicMock
        from game.agents import LLMAgent

        llm = MagicMock()
        agent = LLMAgent(llm, "Sable", "agent_2")

        long_content = "A" * 100
        view = self._minimal_view(intercepted_messages=[
            {"sender": "Vera", "receiver": "Kip", "content": long_content, "round": 5},
        ])

        prompt = agent._build_prompt(view)

        # The full 100-char string should NOT appear in the prompt
        assert long_content not in prompt
        # But the truncated version (first 60 chars) should
        assert "A" * 60 in prompt

    def test_prompt_empty_intercepted_no_section(self):
        """When intercepted_messages is an empty list, no section should appear."""
        from unittest.mock import MagicMock
        from game.agents import LLMAgent

        llm = MagicMock()
        agent = LLMAgent(llm, "Sable", "agent_2")

        view = self._minimal_view(intercepted_messages=[])

        prompt = agent._build_prompt(view)

        assert "Intercepted" not in prompt
