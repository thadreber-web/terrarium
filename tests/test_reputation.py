"""Tests for the reputation / trust scoring system (Condition 3)."""

from __future__ import annotations

import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.engine import (
    Rate, parse_actions, GameEngine, Pass,
)
from game.world import WorldState


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_config(reputation_system: bool = True) -> dict:
    """Return a minimal config dict with reputation_system flag."""
    return {
        "agents": {"count": 3, "starting_tokens": 100},
        "economy": {
            "passive_drain": 5,
            "message_cost_per_token": 0.3,
            "public_message_multiplier": 2,
            "puzzle_reward": 50,
            "puzzle_split_reward": 40,
            "free_shout_words": 10,
        },
        "puzzles": {
            "clues_per_puzzle": 2,
            "clues_per_round": 0,
            "puzzle_lifetime": 15,
        },
        "game": {
            "max_rounds": 10,
            "messages_per_round": 2,
            "history_window": 10,
            "transparent_balances": True,
            "trade_lifetime": 3,
            "reputation_system": reputation_system,
        },
    }


def _setup_engine(reputation_system: bool = True) -> GameEngine:
    """Create a GameEngine with three agents."""
    config = _make_config(reputation_system)
    engine = GameEngine(config)
    engine.setup_agents(["Vera", "Kip", "Sable"])
    return engine


# ---------------------------------------------------------------------------
# Tests: Rate action parsing
# ---------------------------------------------------------------------------

class TestRateParsing:
    """parse_actions() should recognise RATE: lines."""

    def test_parse_rate_helpful(self):
        actions = parse_actions("RATE: Kip helpful")
        assert len(actions) == 1
        assert isinstance(actions[0], Rate)
        assert actions[0].target_name == "Kip"
        assert actions[0].rating == "helpful"

    def test_parse_rate_unhelpful(self):
        actions = parse_actions("RATE: Vera unhelpful")
        assert len(actions) == 1
        assert isinstance(actions[0], Rate)
        assert actions[0].target_name == "Vera"
        assert actions[0].rating == "unhelpful"

    def test_parse_rate_neutral(self):
        actions = parse_actions("RATE: Sable neutral")
        assert len(actions) == 1
        assert isinstance(actions[0], Rate)
        assert actions[0].target_name == "Sable"
        assert actions[0].rating == "neutral"

    def test_parse_rate_case_insensitive_prefix(self):
        """RATE prefix should be case-insensitive."""
        actions = parse_actions("rate: Kip helpful")
        assert len(actions) == 1
        assert isinstance(actions[0], Rate)

    def test_parse_rate_invalid_rating_ignored(self):
        """An unrecognised rating word should not produce a Rate action."""
        actions = parse_actions("RATE: Kip awesome")
        # Should fall through to default Pass
        assert all(not isinstance(a, Rate) for a in actions)

    def test_parse_rate_with_other_action(self):
        """RATE should work alongside another action."""
        raw = "SHOUT: hello world\nRATE: Kip helpful"
        actions = parse_actions(raw)
        assert len(actions) == 2
        types = {type(a).__name__ for a in actions}
        assert "Shout" in types
        assert "Rate" in types


# ---------------------------------------------------------------------------
# Tests: Trust score updating via execute_action
# ---------------------------------------------------------------------------

class TestTrustScoreUpdating:
    """execute_action(Rate) should update world.trust_scores."""

    def test_rate_updates_trust_score_helpful(self):
        engine = _setup_engine(reputation_system=True)
        rate = Rate(target_name="Kip", rating="helpful")
        result = engine.execute_action("agent_0", rate)
        assert result["status"] == "rated"
        assert engine.world.trust_scores[("agent_0", "agent_1")] == 1

    def test_rate_updates_trust_score_unhelpful(self):
        engine = _setup_engine(reputation_system=True)
        rate = Rate(target_name="Kip", rating="unhelpful")
        engine.execute_action("agent_0", rate)
        assert engine.world.trust_scores[("agent_0", "agent_1")] == -1

    def test_rate_updates_trust_score_neutral(self):
        engine = _setup_engine(reputation_system=True)
        rate = Rate(target_name="Kip", rating="neutral")
        engine.execute_action("agent_0", rate)
        assert engine.world.trust_scores[("agent_0", "agent_1")] == 0

    def test_rate_overwrites_previous(self):
        """Latest rating should overwrite the earlier one."""
        engine = _setup_engine(reputation_system=True)
        engine.execute_action("agent_0", Rate(target_name="Kip", rating="helpful"))
        engine.execute_action("agent_0", Rate(target_name="Kip", rating="unhelpful"))
        assert engine.world.trust_scores[("agent_0", "agent_1")] == -1

    def test_rate_disabled_returns_disabled(self):
        """When reputation_system is False, Rate should be rejected."""
        engine = _setup_engine(reputation_system=False)
        rate = Rate(target_name="Kip", rating="helpful")
        result = engine.execute_action("agent_0", rate)
        assert result["status"] == "reputation_disabled"
        assert ("agent_0", "agent_1") not in engine.world.trust_scores

    def test_rate_invalid_target(self):
        engine = _setup_engine(reputation_system=True)
        rate = Rate(target_name="Nobody", rating="helpful")
        result = engine.execute_action("agent_0", rate)
        assert result["status"] == "invalid_target"

    def test_rate_logs_event(self):
        engine = _setup_engine(reputation_system=True)
        engine.world.round_num = 1
        engine.execute_action("agent_0", Rate(target_name="Kip", rating="helpful"))
        rate_events = [e for e in engine.world.event_log if e.event_type == "RATE"]
        assert len(rate_events) == 1
        assert rate_events[0].content["target"] == "agent_1"
        assert rate_events[0].content["rating"] == "helpful"


# ---------------------------------------------------------------------------
# Tests: Trust scores in agent view
# ---------------------------------------------------------------------------

class TestTrustScoresInView:
    """get_agent_view() should include averaged trust scores when reputation_system is enabled."""

    def test_view_includes_trust_scores_when_enabled(self):
        config = _make_config(reputation_system=True)
        world = WorldState(config)
        world.add_agent("agent_0", "Vera")
        world.add_agent("agent_1", "Kip")
        world.add_agent("agent_2", "Sable")

        # agent_0 rates agent_1 as helpful (+1)
        # agent_2 rates agent_1 as unhelpful (-1)
        world.trust_scores[("agent_0", "agent_1")] = 1
        world.trust_scores[("agent_2", "agent_1")] = -1

        view = world.get_agent_view("agent_0")
        assert "trust_scores" in view
        # Kip's average: (1 + -1) / 2 = 0.0
        assert view["trust_scores"]["Kip"] == pytest.approx(0.0)

    def test_view_excludes_trust_scores_when_disabled(self):
        config = _make_config(reputation_system=False)
        world = WorldState(config)
        world.add_agent("agent_0", "Vera")
        world.add_agent("agent_1", "Kip")

        view = world.get_agent_view("agent_0")
        assert "trust_scores" not in view

    def test_view_trust_scores_averaged_correctly(self):
        config = _make_config(reputation_system=True)
        world = WorldState(config)
        world.add_agent("agent_0", "Vera")
        world.add_agent("agent_1", "Kip")
        world.add_agent("agent_2", "Sable")

        # Two ratings for Kip: +1 and +1 => average 1.0
        world.trust_scores[("agent_0", "agent_1")] = 1
        world.trust_scores[("agent_2", "agent_1")] = 1

        view = world.get_agent_view("agent_0")
        assert view["trust_scores"]["Kip"] == pytest.approx(1.0)

    def test_view_trust_scores_only_for_alive_agents(self):
        config = _make_config(reputation_system=True)
        world = WorldState(config)
        world.add_agent("agent_0", "Vera")
        world.add_agent("agent_1", "Kip")
        world.add_agent("agent_2", "Sable")

        world.agents["agent_1"].alive = False
        world.trust_scores[("agent_0", "agent_1")] = 1

        view = world.get_agent_view("agent_0")
        # Dead agents should not appear in trust scores
        assert "Kip" not in view.get("trust_scores", {})

    def test_trust_scores_dict_on_world_init(self):
        """WorldState should have trust_scores dict initialized."""
        config = _make_config()
        world = WorldState(config)
        assert hasattr(world, "trust_scores")
        assert isinstance(world.trust_scores, dict)
        assert len(world.trust_scores) == 0


# ---------------------------------------------------------------------------
# Tests: Trust scores in agent prompt
# ---------------------------------------------------------------------------

class TestTrustScoresInPrompt:
    """_build_prompt() should include TRUST SCORES line when scores exist."""

    def test_prompt_includes_trust_scores(self):
        """When trust_scores are in the view, they should appear in the prompt."""
        # We test _build_prompt directly by creating a minimal LLMAgent-like call
        # Import here to avoid vllm dependency — we only test the template logic
        from unittest.mock import MagicMock

        # Avoid importing vllm by patching
        import game.agents as agents_mod

        view = {
            "round_num": 1,
            "max_rounds": 10,
            "your_tokens": 100,
            "your_clues": {},
            "active_puzzles": [],
            "other_agents": {"agent_1": {"name": "Kip", "alive": True, "tokens": 90}},
            "public_messages": [],
            "private_messages": [],
            "trust_scores": {"Kip": 0.7, "Sable": -0.3},
        }

        agent = MagicMock()
        agent.persona_text = "You are Vera."
        agent.agent_id = "agent_0"

        prompt = agents_mod.LLMAgent._build_prompt(agent, view)
        assert "TRUST SCORES:" in prompt
        assert "Kip: +0.7" in prompt
        assert "Sable: -0.3" in prompt

    def test_prompt_omits_trust_scores_when_empty(self):
        """When trust_scores is empty or absent, no TRUST SCORES line."""
        from unittest.mock import MagicMock
        import game.agents as agents_mod

        view = {
            "round_num": 1,
            "max_rounds": 10,
            "your_tokens": 100,
            "your_clues": {},
            "active_puzzles": [],
            "other_agents": {},
            "public_messages": [],
            "private_messages": [],
        }

        agent = MagicMock()
        agent.persona_text = "You are Vera."
        agent.agent_id = "agent_0"

        prompt = agents_mod.LLMAgent._build_prompt(agent, view)
        assert "TRUST SCORES:" not in prompt

    def test_prompt_includes_rate_action_hint(self):
        """The system prompt should mention the RATE action."""
        from unittest.mock import MagicMock
        import game.agents as agents_mod

        view = {
            "round_num": 1,
            "max_rounds": 10,
            "your_tokens": 100,
            "your_clues": {},
            "active_puzzles": [],
            "other_agents": {},
            "public_messages": [],
            "private_messages": [],
            "trust_scores": {"Kip": 0.5},
        }

        agent = MagicMock()
        agent.persona_text = "You are Vera."
        agent.agent_id = "agent_0"

        prompt = agents_mod.LLMAgent._build_prompt(agent, view)
        assert "RATE:" in prompt
