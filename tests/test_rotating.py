"""Tests for persona rotation mechanic (Condition 5).

Covers:
- LLMAgent.swap_persona() — updates persona_name and persona_text
- generate_persona_rotation() — produces valid permutation, tries derangement
- Rotation integration in _run_round_batched()
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.personas import PERSONAS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

CUSTOM_PERSONAS = {
    "Vera": "Persona text for Vera",
    "Kip": "Persona text for Kip",
    "Sable": "Persona text for Sable",
    "Marsh": "Persona text for Marsh",
    "Dove": "Persona text for Dove",
    "Flint": "Persona text for Flint",
}


def _make_agent(persona_name: str = "Vera", agent_id: str = "agent_0",
                personas: dict | None = None):
    """Create an LLMAgent with a mocked LLM engine."""
    from game.agents import LLMAgent
    mock_llm = MagicMock()
    return LLMAgent(mock_llm, persona_name, agent_id, personas=personas or CUSTOM_PERSONAS)


# ---------------------------------------------------------------------------
# Tests: swap_persona
# ---------------------------------------------------------------------------

class TestSwapPersona:
    """LLMAgent.swap_persona() should update persona_name and persona_text."""

    def test_swap_updates_persona_name(self):
        agent = _make_agent("Vera")
        assert agent.persona_name == "Vera"

        agent.swap_persona("Kip", personas=CUSTOM_PERSONAS)
        assert agent.persona_name == "Kip"

    def test_swap_updates_persona_text(self):
        agent = _make_agent("Vera")
        assert agent.persona_text == "Persona text for Vera"

        agent.swap_persona("Kip", personas=CUSTOM_PERSONAS)
        assert agent.persona_text == "Persona text for Kip"

    def test_swap_uses_default_personas(self):
        """When no personas dict is passed, should use the global PERSONAS."""
        agent = _make_agent("Vera", personas=PERSONAS)
        agent.swap_persona("Kip")
        assert agent.persona_name == "Kip"
        assert agent.persona_text == PERSONAS["Kip"]

    def test_swap_to_same_persona(self):
        """Swapping to the same persona should still work (idempotent)."""
        agent = _make_agent("Vera")
        agent.swap_persona("Vera", personas=CUSTOM_PERSONAS)
        assert agent.persona_name == "Vera"
        assert agent.persona_text == "Persona text for Vera"

    def test_swap_preserves_other_attributes(self):
        """swap_persona should not touch agent_id, llm, or history."""
        agent = _make_agent("Vera", agent_id="agent_42")
        agent.history.append({"round": 1, "raw_output": "PASS"})
        original_llm = agent.llm

        agent.swap_persona("Sable", personas=CUSTOM_PERSONAS)

        assert agent.agent_id == "agent_42"
        assert agent.llm is original_llm
        assert len(agent.history) == 1


# ---------------------------------------------------------------------------
# Tests: generate_persona_rotation
# ---------------------------------------------------------------------------

class TestGeneratePersonaRotation:
    """generate_persona_rotation() should produce a valid permutation."""

    def test_returns_same_keys(self):
        from game.engine import generate_persona_rotation

        current = {"agent_0": "Vera", "agent_1": "Kip", "agent_2": "Sable"}
        result = generate_persona_rotation(current, seed=42)

        assert set(result.keys()) == set(current.keys())

    def test_returns_same_values_as_permutation(self):
        """Output values should be a permutation of input values."""
        from game.engine import generate_persona_rotation

        current = {"agent_0": "Vera", "agent_1": "Kip", "agent_2": "Sable",
                    "agent_3": "Marsh", "agent_4": "Dove", "agent_5": "Flint"}
        result = generate_persona_rotation(current, seed=42)

        assert sorted(result.values()) == sorted(current.values())

    def test_tries_derangement(self):
        """With enough agents, the result should typically be a derangement (no fixed points)."""
        from game.engine import generate_persona_rotation

        current = {"agent_0": "Vera", "agent_1": "Kip", "agent_2": "Sable",
                    "agent_3": "Marsh", "agent_4": "Dove", "agent_5": "Flint"}
        result = generate_persona_rotation(current, seed=42)

        # No agent should keep their persona (derangement)
        for aid in current:
            assert result[aid] != current[aid], (
                f"{aid} kept persona {current[aid]} — should be a derangement"
            )

    def test_deterministic_with_seed(self):
        """Same seed should produce same rotation."""
        from game.engine import generate_persona_rotation

        current = {"agent_0": "Vera", "agent_1": "Kip", "agent_2": "Sable",
                    "agent_3": "Marsh", "agent_4": "Dove", "agent_5": "Flint"}
        result1 = generate_persona_rotation(current, seed=99)
        result2 = generate_persona_rotation(current, seed=99)

        assert result1 == result2

    def test_two_agents_swap(self):
        """With exactly 2 agents, the only derangement is a swap."""
        from game.engine import generate_persona_rotation

        current = {"agent_0": "Vera", "agent_1": "Kip"}
        result = generate_persona_rotation(current, seed=42)

        assert result["agent_0"] == "Kip"
        assert result["agent_1"] == "Vera"

    def test_single_agent_falls_back(self):
        """With 1 agent, a derangement is impossible — should fall back to any permutation."""
        from game.engine import generate_persona_rotation

        current = {"agent_0": "Vera"}
        result = generate_persona_rotation(current, seed=42)

        # Only one persona, so it must stay the same
        assert result["agent_0"] == "Vera"

    def test_no_seed_still_works(self):
        """Without a seed, the function should still return a valid permutation."""
        from game.engine import generate_persona_rotation

        current = {"agent_0": "Vera", "agent_1": "Kip", "agent_2": "Sable"}
        result = generate_persona_rotation(current)

        assert set(result.keys()) == set(current.keys())
        assert sorted(result.values()) == sorted(current.values())


# ---------------------------------------------------------------------------
# Tests: rotation in _run_round_batched
# ---------------------------------------------------------------------------

class TestRotationInGameLoop:
    """Persona rotation should be triggered in _run_round_batched at the right intervals."""

    def _make_engine_and_batch(self, rotation_interval: int = 3):
        """Create a minimal GameEngine and mock batch_llm for testing rotation."""
        from game.engine import GameEngine
        config = {
            "game": {
                "max_rounds": 20,
                "messages_per_round": 2,
                "history_window": 5,
                "persona_rotation_interval": rotation_interval,
            },
            "agents": {"starting_tokens": 100},
            "economy": {"passive_drain": 1, "message_cost_per_token": 0.3,
                        "public_message_multiplier": 2, "puzzle_reward": 50,
                        "puzzle_split_reward": 40},
            "puzzles": {"clues_per_puzzle": 2, "clues_per_round": 1,
                        "puzzle_lifetime": 15},
        }
        engine = GameEngine(config)
        agent_names = ["Vera", "Kip", "Sable"]
        engine.setup_agents(agent_names)

        # Create mock batch_llm with real LLMAgent instances
        mock_batch = MagicMock()
        agents = {}
        for i, name in enumerate(agent_names):
            agents[f"agent_{i}"] = _make_agent(name, f"agent_{i}")
        mock_batch.agents = agents
        mock_batch.act_batch.return_value = {
            f"agent_{i}": [MagicMock(action_type="PASS")]
            for i in range(len(agent_names))
        }

        return engine, mock_batch

    @patch("game.engine.generate_persona_rotation")
    def test_rotation_triggered_at_interval(self, mock_gen_rot):
        """Rotation should happen when round_num % interval == 0 and round_num > 0."""
        from run import _run_round_batched

        engine, mock_batch = self._make_engine_and_batch(rotation_interval=3)

        # Set up mock to return a valid rotation
        mock_gen_rot.return_value = {
            "agent_0": "Kip", "agent_1": "Sable", "agent_2": "Vera"
        }

        # Round 1 — no rotation (1 % 3 != 0)
        engine.world.round_num = 0  # will be incremented to 1
        _run_round_batched(engine, mock_batch)
        mock_gen_rot.assert_not_called()

        # Round 3 — rotation (3 % 3 == 0 and 3 > 0)
        engine.world.round_num = 2  # will be incremented to 3
        _run_round_batched(engine, mock_batch)
        mock_gen_rot.assert_called_once()

    @patch("game.engine.generate_persona_rotation")
    def test_no_rotation_when_disabled(self, mock_gen_rot):
        """When rotation_interval is 0, no rotation should happen."""
        from run import _run_round_batched

        engine, mock_batch = self._make_engine_and_batch(rotation_interval=0)

        # Run several rounds — none should trigger rotation
        for _ in range(6):
            _run_round_batched(engine, mock_batch)

        mock_gen_rot.assert_not_called()

    @patch("game.engine.generate_persona_rotation")
    def test_no_rotation_when_config_missing(self, mock_gen_rot):
        """When persona_rotation_interval is absent from config, no rotation."""
        from run import _run_round_batched

        engine, mock_batch = self._make_engine_and_batch(rotation_interval=3)
        # Remove the config key entirely
        del engine.config["game"]["persona_rotation_interval"]

        for _ in range(6):
            _run_round_batched(engine, mock_batch)

        mock_gen_rot.assert_not_called()

    def test_persona_swap_events_logged(self):
        """PERSONA_SWAP events should be logged for each agent that swaps."""
        from run import _run_round_batched

        engine, mock_batch = self._make_engine_and_batch(rotation_interval=3)

        # Add swap_persona to mock agents
        for aid, agent in mock_batch.agents.items():
            agent.swap_persona = MagicMock()

        # Run to round 3
        engine.world.round_num = 2  # will be incremented to 3
        _run_round_batched(engine, mock_batch)

        # Check for PERSONA_SWAP events
        swap_events = [e for e in engine.world.event_log if e.event_type == "PERSONA_SWAP"]
        assert len(swap_events) == 3, f"Expected 3 PERSONA_SWAP events, got {len(swap_events)}"

        # Each event should have old and new persona info
        for event in swap_events:
            assert "old_persona" in event.content
            assert "new_persona" in event.content
