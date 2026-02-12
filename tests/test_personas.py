"""Tests for persona override system."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from game.personas import PERSONAS, AGENT_NAMES, apply_persona_overrides


# ---------------------------------------------------------------------------
# Tests: apply_persona_overrides
# ---------------------------------------------------------------------------

class TestApplyPersonaOverridesReplace:
    """Override with a string should replace the entire persona text."""

    def test_replace_single_persona(self):
        """A string override replaces the persona text entirely."""
        overrides = {"Vera": "New Vera persona text."}
        result = apply_persona_overrides(overrides)
        assert result["Vera"] == "New Vera persona text."

    def test_replace_preserves_others(self):
        """Overriding one persona should leave the rest untouched."""
        overrides = {"Vera": "Custom Vera."}
        result = apply_persona_overrides(overrides)
        assert result["Kip"] == PERSONAS["Kip"]
        assert result["Sable"] == PERSONAS["Sable"]
        assert result["Marsh"] == PERSONAS["Marsh"]
        assert result["Dove"] == PERSONAS["Dove"]
        assert result["Flint"] == PERSONAS["Flint"]

    def test_replace_multiple_personas(self):
        """Multiple string overrides all take effect."""
        overrides = {
            "Vera": "Custom Vera.",
            "Kip": "Custom Kip.",
        }
        result = apply_persona_overrides(overrides)
        assert result["Vera"] == "Custom Vera."
        assert result["Kip"] == "Custom Kip."
        assert result["Sable"] == PERSONAS["Sable"]


class TestApplyPersonaOverridesAppend:
    """Override with {"append": text} should append to existing persona."""

    def test_append_to_persona(self):
        """A dict with 'append' key should add text to the end."""
        overrides = {"Vera": {"append": " Extra trait."}}
        result = apply_persona_overrides(overrides)
        assert result["Vera"] == PERSONAS["Vera"] + " Extra trait."

    def test_append_preserves_others(self):
        """Appending to one persona leaves the rest unchanged."""
        overrides = {"Kip": {"append": " Also cautious."}}
        result = apply_persona_overrides(overrides)
        assert result["Vera"] == PERSONAS["Vera"]
        assert result["Kip"] == PERSONAS["Kip"] + " Also cautious."

    def test_append_multiple(self):
        """Multiple append overrides all work."""
        overrides = {
            "Vera": {"append": " A."},
            "Kip": {"append": " B."},
        }
        result = apply_persona_overrides(overrides)
        assert result["Vera"] == PERSONAS["Vera"] + " A."
        assert result["Kip"] == PERSONAS["Kip"] + " B."


class TestApplyPersonaOverridesMixed:
    """Mixed replace and append overrides should both work."""

    def test_mix_replace_and_append(self):
        overrides = {
            "Vera": "Completely new Vera.",
            "Kip": {"append": " Extra."},
        }
        result = apply_persona_overrides(overrides)
        assert result["Vera"] == "Completely new Vera."
        assert result["Kip"] == PERSONAS["Kip"] + " Extra."


class TestApplyPersonaOverridesValidation:
    """Invalid agent names should raise ValueError."""

    def test_invalid_name_raises(self):
        overrides = {"Nonexistent": "text"}
        with pytest.raises(ValueError, match="Nonexistent"):
            apply_persona_overrides(overrides)

    def test_invalid_name_among_valid(self):
        """Even one bad name should raise before applying anything."""
        overrides = {
            "Vera": "ok",
            "BadName": "nope",
        }
        with pytest.raises(ValueError, match="BadName"):
            apply_persona_overrides(overrides)


class TestApplyPersonaOverridesEmpty:
    """Empty overrides should return a copy of PERSONAS."""

    def test_empty_overrides_returns_defaults(self):
        result = apply_persona_overrides({})
        assert result == PERSONAS

    def test_empty_overrides_returns_copy(self):
        """The returned dict should be a new object, not the global PERSONAS."""
        result = apply_persona_overrides({})
        assert result is not PERSONAS


class TestApplyPersonaOverridesImmutability:
    """apply_persona_overrides must not mutate the global PERSONAS dict."""

    def test_global_not_mutated(self):
        original_vera = PERSONAS["Vera"]
        overrides = {"Vera": "Mutant Vera."}
        apply_persona_overrides(overrides)
        assert PERSONAS["Vera"] == original_vera


# ---------------------------------------------------------------------------
# Tests: LLMAgent personas parameter
# ---------------------------------------------------------------------------

class TestLLMAgentPersonasParam:
    """LLMAgent.__init__ should accept an optional personas dict."""

    @patch("game.agents.LLM")
    def test_default_uses_global_personas(self, MockLLM):
        """Without personas param, agent uses global PERSONAS."""
        from game.agents import LLMAgent
        mock_llm = MagicMock()
        agent = LLMAgent(mock_llm, "Vera", "agent_0")
        assert agent.persona_text == PERSONAS["Vera"]

    @patch("game.agents.LLM")
    def test_custom_personas_used(self, MockLLM):
        """With personas param, agent uses the provided dict."""
        from game.agents import LLMAgent
        mock_llm = MagicMock()
        custom = {"Vera": "Custom persona text."}
        agent = LLMAgent(mock_llm, "Vera", "agent_0", personas=custom)
        assert agent.persona_text == "Custom persona text."


class TestBatchLLMAgentPersonasParam:
    """BatchLLMAgent should accept and thread personas parameter."""

    @patch("game.agents.LLM")
    def test_personas_threaded_to_agents(self, MockLLM):
        MockLLM.return_value = MagicMock()
        from game.agents import BatchLLMAgent
        custom = {**PERSONAS, "Vera": "Batch custom Vera."}
        batch = BatchLLMAgent("some-model", ["Vera", "Kip"], personas=custom)
        assert batch.agents["agent_0"].persona_text == "Batch custom Vera."
        assert batch.agents["agent_1"].persona_text == PERSONAS["Kip"]


class TestMixedBatchLLMAgentPersonasParam:
    """MixedBatchLLMAgent should accept and thread personas parameter."""

    @patch("game.agents.LLM")
    def test_personas_threaded_to_agents(self, MockLLM):
        MockLLM.return_value = MagicMock()
        from game.agents import MixedBatchLLMAgent
        custom = {**PERSONAS, "Vera": "Mixed custom Vera."}
        model_map = {"Vera": "models/a", "Kip": "models/a"}
        batch = MixedBatchLLMAgent(model_map=model_map, personas=custom)
        assert batch.agents["agent_0"].persona_text == "Mixed custom Vera."
        assert batch.agents["agent_1"].persona_text == PERSONAS["Kip"]
