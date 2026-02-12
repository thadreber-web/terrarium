"""Tests for MixedBatchLLMAgent."""

from __future__ import annotations

from unittest.mock import MagicMock, patch, call

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_mock_output(text: str = "PASS") -> MagicMock:
    """Return a mock vLLM RequestOutput with .outputs[0].text = text."""
    inner = MagicMock()
    inner.text = text
    outer = MagicMock()
    outer.outputs = [inner]
    return outer


def _minimal_view(round_num: int = 1) -> dict:
    """Return the smallest valid game view for prompt building."""
    return {
        "round_num": round_num,
        "max_rounds": 10,
        "your_tokens": 100,
        "your_clues": {},
        "active_puzzles": [],
        "other_agents": {},
        "public_messages": [],
        "private_messages": [],
    }


MODEL_A = "models/small-3b"
MODEL_B = "models/large-7b"


# ---------------------------------------------------------------------------
# Test: agent-to-model assignment
# ---------------------------------------------------------------------------

class TestAgentToModelAssignment:
    """Each agent should be wired to the LLM instance for its mapped model."""

    @patch("game.agents.LLM")
    def test_agents_created_for_every_entry(self, MockLLM):
        """MixedBatchLLMAgent.agents should have one entry per model_map key."""
        MockLLM.return_value = MagicMock()

        from game.agents import MixedBatchLLMAgent

        model_map = {
            "Vera": MODEL_A,
            "Kip": MODEL_A,
            "Sable": MODEL_B,
        }
        batch = MixedBatchLLMAgent(model_map=model_map)

        assert set(batch.agents.keys()) == {"agent_0", "agent_1", "agent_2"}

    @patch("game.agents.LLM")
    def test_agents_use_correct_llm_instance(self, MockLLM):
        """Agents mapped to different models should hold different LLM refs."""
        llm_instances = {}

        def _make_llm(model, **kw):
            inst = MagicMock(name=f"LLM({model})")
            llm_instances[model] = inst
            return inst

        MockLLM.side_effect = _make_llm

        from game.agents import MixedBatchLLMAgent

        model_map = {
            "Vera": MODEL_A,
            "Kip": MODEL_A,
            "Sable": MODEL_B,
        }
        batch = MixedBatchLLMAgent(model_map=model_map)

        # Vera and Kip share MODEL_A's instance
        assert batch.agents["agent_0"].llm is llm_instances[MODEL_A]
        assert batch.agents["agent_1"].llm is llm_instances[MODEL_A]
        # Sable gets MODEL_B's instance
        assert batch.agents["agent_2"].llm is llm_instances[MODEL_B]

    @patch("game.agents.LLM")
    def test_model_dedup(self, MockLLM):
        """Two agents on the same model should share one LLM() call."""
        MockLLM.return_value = MagicMock()

        from game.agents import MixedBatchLLMAgent

        model_map = {
            "Vera": MODEL_A,
            "Kip": MODEL_A,
            "Sable": MODEL_A,
        }
        batch = MixedBatchLLMAgent(model_map=model_map)

        # Only one LLM instance should have been created
        assert MockLLM.call_count == 1

    @patch("game.agents.LLM")
    def test_two_distinct_models_loaded(self, MockLLM):
        """Two different model paths should trigger two LLM() calls."""
        MockLLM.return_value = MagicMock()

        from game.agents import MixedBatchLLMAgent

        model_map = {
            "Vera": MODEL_A,
            "Kip": MODEL_B,
        }
        batch = MixedBatchLLMAgent(model_map=model_map)

        assert MockLLM.call_count == 2


# ---------------------------------------------------------------------------
# Test: model metadata recording
# ---------------------------------------------------------------------------

class TestModelMetadata:
    """agent_models dict should record which model backs each agent."""

    @patch("game.agents.LLM")
    def test_agent_models_keys_match_agents(self, MockLLM):
        MockLLM.return_value = MagicMock()

        from game.agents import MixedBatchLLMAgent

        model_map = {
            "Vera": MODEL_A,
            "Kip": MODEL_B,
            "Sable": MODEL_B,
        }
        batch = MixedBatchLLMAgent(model_map=model_map)

        assert set(batch.agent_models.keys()) == set(batch.agents.keys())

    @patch("game.agents.LLM")
    def test_agent_models_values(self, MockLLM):
        MockLLM.return_value = MagicMock()

        from game.agents import MixedBatchLLMAgent

        model_map = {
            "Vera": MODEL_A,
            "Kip": MODEL_B,
            "Sable": MODEL_B,
        }
        batch = MixedBatchLLMAgent(model_map=model_map)

        assert batch.agent_models["agent_0"] == MODEL_A
        assert batch.agent_models["agent_1"] == MODEL_B
        assert batch.agent_models["agent_2"] == MODEL_B


# ---------------------------------------------------------------------------
# Test: act_batch routing
# ---------------------------------------------------------------------------

class TestActBatchRouting:
    """act_batch should group prompts by model and call each LLM once."""

    @patch("game.agents.LLM")
    def test_prompts_grouped_by_model(self, MockLLM):
        """Each model's generate() should be called once with only its agents' prompts."""
        llm_instances = {}

        def _make_llm(model, **kw):
            inst = MagicMock(name=f"LLM({model})")
            inst.generate.return_value = [_make_mock_output("PASS")]
            llm_instances[model] = inst
            return inst

        MockLLM.side_effect = _make_llm

        from game.agents import MixedBatchLLMAgent

        model_map = {
            "Vera": MODEL_A,
            "Kip": MODEL_B,
        }
        batch = MixedBatchLLMAgent(model_map=model_map)

        views = {
            "agent_0": _minimal_view(1),
            "agent_1": _minimal_view(1),
        }

        # Each model's generate returns one output per prompt
        llm_instances[MODEL_A].generate.return_value = [_make_mock_output("PASS")]
        llm_instances[MODEL_B].generate.return_value = [_make_mock_output("PASS")]

        results = batch.act_batch(views)

        # MODEL_A.generate called once with a list of 1 prompt
        assert llm_instances[MODEL_A].generate.call_count == 1
        prompts_a = llm_instances[MODEL_A].generate.call_args[0][0]
        assert len(prompts_a) == 1

        # MODEL_B.generate called once with a list of 1 prompt
        assert llm_instances[MODEL_B].generate.call_count == 1
        prompts_b = llm_instances[MODEL_B].generate.call_args[0][0]
        assert len(prompts_b) == 1

    @patch("game.agents.LLM")
    def test_results_returned_for_all_agents(self, MockLLM):
        """act_batch should return results keyed by every agent_id in views."""
        llm_instances = {}

        def _make_llm(model, **kw):
            inst = MagicMock(name=f"LLM({model})")
            llm_instances[model] = inst
            return inst

        MockLLM.side_effect = _make_llm

        from game.agents import MixedBatchLLMAgent

        model_map = {
            "Vera": MODEL_A,
            "Kip": MODEL_A,
            "Sable": MODEL_B,
        }
        batch = MixedBatchLLMAgent(model_map=model_map)

        views = {
            "agent_0": _minimal_view(1),
            "agent_1": _minimal_view(1),
            "agent_2": _minimal_view(1),
        }

        llm_instances[MODEL_A].generate.return_value = [
            _make_mock_output("PASS"),
            _make_mock_output("PASS"),
        ]
        llm_instances[MODEL_B].generate.return_value = [
            _make_mock_output("PASS"),
        ]

        results = batch.act_batch(views)

        assert set(results.keys()) == {"agent_0", "agent_1", "agent_2"}

    @patch("game.agents.LLM")
    def test_act_batch_empty_views(self, MockLLM):
        """act_batch with empty views should return empty dict without calling generate."""
        MockLLM.return_value = MagicMock()

        from game.agents import MixedBatchLLMAgent

        model_map = {"Vera": MODEL_A}
        batch = MixedBatchLLMAgent(model_map=model_map)

        results = batch.act_batch({})

        assert results == {}
        MockLLM.return_value.generate.assert_not_called()

    @patch("game.agents.LLM")
    def test_act_batch_records_history(self, MockLLM):
        """act_batch should append to each agent's history."""
        llm_inst = MagicMock()
        llm_inst.generate.return_value = [_make_mock_output("PASS")]
        MockLLM.return_value = llm_inst

        from game.agents import MixedBatchLLMAgent

        model_map = {"Vera": MODEL_A}
        batch = MixedBatchLLMAgent(model_map=model_map)

        views = {"agent_0": _minimal_view(3)}
        batch.act_batch(views)

        assert len(batch.agents["agent_0"].history) == 1
        assert batch.agents["agent_0"].history[0]["round"] == 3
        assert batch.agents["agent_0"].history[0]["raw_output"] == "PASS"
