"""Tests for run_experiment.py — unified experiment runner."""

from __future__ import annotations

import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from run_experiment import load_experiment, build_run_args, apply_config_overrides


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mixed_experiment(tmp_path):
    """An experiment JSON with a model_map (triggers mixed mode)."""
    data = {
        "model_map": {
            "Sable": "Qwen/Qwen2.5-7B-Instruct-AWQ",
            "Vera": "Qwen/Qwen2.5-7B-Instruct-AWQ",
            "Marsh": "Qwen/Qwen2.5-7B-Instruct-AWQ",
            "Kip": "Qwen/Qwen2.5-3B-Instruct-AWQ",
            "Dove": "Qwen/Qwen2.5-3B-Instruct-AWQ",
            "Flint": "Qwen/Qwen2.5-3B-Instruct-AWQ",
        },
        "notes": "Mixed run A",
    }
    p = tmp_path / "mixed.json"
    p.write_text(json.dumps(data))
    return str(p), data


@pytest.fixture
def persona_experiment(tmp_path):
    """An experiment JSON with persona_overrides."""
    data = {
        "persona_overrides": {
            "Kip": "You are Kip. Trust no one."
        },
        "notes": "Adversarial injection",
    }
    p = tmp_path / "adversarial.json"
    p.write_text(json.dumps(data))
    return str(p), data


@pytest.fixture
def config_override_experiment(tmp_path):
    """An experiment JSON with config_overrides."""
    data = {
        "config_overrides": {
            "game": {
                "reputation_system": True,
            }
        },
        "notes": "Reputation system",
    }
    p = tmp_path / "reputation.json"
    p.write_text(json.dumps(data))
    return str(p), data


@pytest.fixture
def full_experiment(tmp_path):
    """An experiment JSON with all fields present."""
    data = {
        "model_map": {
            "Vera": "models/7b",
            "Kip": "models/3b",
            "Sable": "models/7b",
            "Marsh": "models/3b",
            "Dove": "models/7b",
            "Flint": "models/3b",
        },
        "persona_overrides": {
            "Kip": "Custom Kip persona.",
        },
        "config_overrides": {
            "game": {"reputation_system": True},
        },
        "notes": "Full experiment",
    }
    p = tmp_path / "full.json"
    p.write_text(json.dumps(data))
    return str(p), data


@pytest.fixture
def base_config():
    """A minimal base config dict resembling scarce.yaml."""
    return {
        "agents": {"count": 6, "starting_tokens": 700},
        "economy": {"passive_drain": 8, "puzzle_reward": 55},
        "game": {"max_rounds": 200, "messages_per_round": 2, "transparent_balances": True},
    }


# ---------------------------------------------------------------------------
# Tests: load_experiment
# ---------------------------------------------------------------------------

class TestLoadExperiment:
    """load_experiment(path) should parse experiment JSON files."""

    def test_parses_model_map(self, mixed_experiment):
        """model_map should be parsed correctly from the JSON."""
        path, expected = mixed_experiment
        result = load_experiment(path)
        assert result["model_map"] == expected["model_map"]

    def test_parses_persona_overrides(self, persona_experiment):
        """persona_overrides should be parsed correctly from the JSON."""
        path, expected = persona_experiment
        result = load_experiment(path)
        assert result["persona_overrides"] == expected["persona_overrides"]

    def test_parses_config_overrides(self, config_override_experiment):
        """config_overrides should be parsed correctly from the JSON."""
        path, expected = config_override_experiment
        result = load_experiment(path)
        assert result["config_overrides"] == expected["config_overrides"]

    def test_parses_notes(self, mixed_experiment):
        """notes field should be preserved."""
        path, expected = mixed_experiment
        result = load_experiment(path)
        assert result["notes"] == expected["notes"]

    def test_missing_file_raises(self):
        """A nonexistent file should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError):
            load_experiment("/tmp/does_not_exist_experiment.json")

    def test_invalid_json_raises(self, tmp_path):
        """Malformed JSON should raise an error."""
        p = tmp_path / "bad.json"
        p.write_text("not json {{{")
        with pytest.raises(json.JSONDecodeError):
            load_experiment(str(p))

    def test_missing_optional_keys_default_to_none(self, tmp_path):
        """An experiment with only notes should still load; missing keys are absent."""
        p = tmp_path / "minimal.json"
        p.write_text(json.dumps({"notes": "bare experiment"}))
        result = load_experiment(str(p))
        assert result.get("model_map") is None
        assert result.get("persona_overrides") is None
        assert result.get("config_overrides") is None


# ---------------------------------------------------------------------------
# Tests: build_run_args
# ---------------------------------------------------------------------------

class TestBuildRunArgs:
    """build_run_args should convert experiment dict to run_game kwargs."""

    def test_mode_mixed_when_model_map_present(self, mixed_experiment):
        """When model_map is present, mode should be 'mixed'."""
        _, data = mixed_experiment
        args = build_run_args(data)
        assert args["mode"] == "mixed"

    def test_mode_llm_when_no_model_map(self, persona_experiment):
        """When no model_map, mode should be 'llm'."""
        _, data = persona_experiment
        args = build_run_args(data, default_model="Qwen/Qwen2.5-3B-Instruct-AWQ")
        assert args["mode"] == "llm"

    def test_model_map_raw_is_json_string(self, mixed_experiment):
        """model_map_raw should be a JSON string of the model_map."""
        _, data = mixed_experiment
        args = build_run_args(data)
        assert args["model_map_raw"] is not None
        parsed = json.loads(args["model_map_raw"])
        assert parsed == data["model_map"]

    def test_model_map_raw_none_when_no_model_map(self, persona_experiment):
        """model_map_raw should be None when no model_map in experiment."""
        _, data = persona_experiment
        args = build_run_args(data, default_model="m")
        assert args["model_map_raw"] is None

    def test_active_personas_set_from_overrides(self, persona_experiment):
        """active_personas should be populated from persona_overrides."""
        _, data = persona_experiment
        args = build_run_args(data, default_model="m")
        assert args["active_personas"] is not None
        assert args["active_personas"]["Kip"] == "You are Kip. Trust no one."

    def test_active_personas_none_when_no_overrides(self, mixed_experiment):
        """active_personas should be None when no persona_overrides."""
        _, data = mixed_experiment
        args = build_run_args(data)
        assert args["active_personas"] is None

    def test_default_model_used_for_llm_mode(self, persona_experiment):
        """model_name should come from default_model when mode is llm."""
        _, data = persona_experiment
        args = build_run_args(data, default_model="Qwen/Qwen2.5-7B-Instruct-AWQ")
        assert args["model_name"] == "Qwen/Qwen2.5-7B-Instruct-AWQ"

    def test_game_id_uses_prefix(self, mixed_experiment):
        """game_id should incorporate the provided prefix."""
        _, data = mixed_experiment
        args = build_run_args(data, game_id_prefix="exp_test")
        assert args["game_id"].startswith("exp_test")

    def test_full_experiment_has_all_fields(self, full_experiment):
        """A full experiment should produce mode=mixed with personas and model_map."""
        _, data = full_experiment
        args = build_run_args(data)
        assert args["mode"] == "mixed"
        assert args["model_map_raw"] is not None
        assert args["active_personas"] is not None
        assert args["active_personas"]["Kip"] == "Custom Kip persona."


# ---------------------------------------------------------------------------
# Tests: apply_config_overrides
# ---------------------------------------------------------------------------

class TestApplyConfigOverrides:
    """apply_config_overrides should deep-merge overrides into base config."""

    def test_deep_merge_adds_new_key(self, base_config):
        """A new key inside an existing section should be added."""
        overrides = {"game": {"reputation_system": True}}
        result = apply_config_overrides(base_config, overrides)
        assert result["game"]["reputation_system"] is True

    def test_deep_merge_preserves_unmodified_keys(self, base_config):
        """Existing keys not in overrides should be preserved."""
        overrides = {"game": {"reputation_system": True}}
        result = apply_config_overrides(base_config, overrides)
        assert result["game"]["max_rounds"] == 200
        assert result["game"]["messages_per_round"] == 2
        assert result["game"]["transparent_balances"] is True

    def test_deep_merge_overwrites_existing_key(self, base_config):
        """An existing key in overrides should be overwritten."""
        overrides = {"game": {"max_rounds": 100}}
        result = apply_config_overrides(base_config, overrides)
        assert result["game"]["max_rounds"] == 100

    def test_deep_merge_preserves_other_sections(self, base_config):
        """Sections not in overrides should be untouched."""
        overrides = {"game": {"reputation_system": True}}
        result = apply_config_overrides(base_config, overrides)
        assert result["agents"] == base_config["agents"]
        assert result["economy"] == base_config["economy"]

    def test_deep_merge_adds_new_section(self, base_config):
        """A new top-level section should be added."""
        overrides = {"new_section": {"key": "value"}}
        result = apply_config_overrides(base_config, overrides)
        assert result["new_section"]["key"] == "value"

    def test_empty_overrides_returns_same(self, base_config):
        """Empty overrides dict should return the config unchanged."""
        original = deepcopy(base_config)
        result = apply_config_overrides(base_config, {})
        assert result == original

    def test_none_overrides_returns_same(self, base_config):
        """None overrides should return the config unchanged."""
        original = deepcopy(base_config)
        result = apply_config_overrides(base_config, None)
        assert result == original

    def test_does_not_mutate_original(self, base_config):
        """The original config dict should not be mutated."""
        original = deepcopy(base_config)
        overrides = {"game": {"reputation_system": True}}
        apply_config_overrides(base_config, overrides)
        assert base_config == original

    def test_nested_deep_merge(self, base_config):
        """Deeply nested overrides should merge correctly."""
        overrides = {"economy": {"passive_drain": 12}}
        result = apply_config_overrides(base_config, overrides)
        assert result["economy"]["passive_drain"] == 12
        assert result["economy"]["puzzle_reward"] == 55  # preserved
