"""Tests for run.py CLI helpers: parse_model_map and validate_args."""

from __future__ import annotations

import json
import os
import tempfile
from argparse import Namespace
from unittest.mock import patch

import pytest

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from run import parse_model_map, validate_args


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MODEL_A = "models/small-3b"
MODEL_B = "models/large-7b"


@pytest.fixture
def sample_map():
    """A simple model map dict used across tests."""
    return {
        "Vera": MODEL_A,
        "Kip": MODEL_A,
        "Sable": MODEL_B,
        "Marsh": MODEL_B,
        "Dove": MODEL_A,
        "Flint": MODEL_B,
    }


@pytest.fixture
def sample_map_json(sample_map):
    """Return the sample map as a JSON string."""
    return json.dumps(sample_map)


@pytest.fixture
def sample_map_file(sample_map, tmp_path):
    """Write sample map to a temp JSON file and return the path."""
    p = tmp_path / "model_map.json"
    p.write_text(json.dumps(sample_map))
    return str(p)


# ---------------------------------------------------------------------------
# Tests: parse_model_map
# ---------------------------------------------------------------------------

class TestParseModelMap:
    """parse_model_map(raw) should accept a JSON string or a file path."""

    def test_parse_json_string(self, sample_map, sample_map_json):
        """A raw JSON string should be parsed into a dict."""
        result = parse_model_map(sample_map_json)
        assert result == sample_map

    def test_parse_json_file(self, sample_map, sample_map_file):
        """A path to a JSON file should be read and parsed."""
        result = parse_model_map(sample_map_file)
        assert result == sample_map

    def test_parse_preserves_order(self, sample_map_json):
        """Keys should come back in insertion order (Python 3.7+)."""
        result = parse_model_map(sample_map_json)
        assert list(result.keys()) == ["Vera", "Kip", "Sable", "Marsh", "Dove", "Flint"]

    def test_parse_invalid_json_string(self):
        """Non-JSON, non-file input should raise ValueError."""
        with pytest.raises((ValueError, json.JSONDecodeError)):
            parse_model_map("not valid json {{{")

    def test_parse_nonexistent_file(self):
        """A path that doesn't exist and isn't valid JSON should raise."""
        with pytest.raises((ValueError, FileNotFoundError, json.JSONDecodeError)):
            parse_model_map("/tmp/does_not_exist_model_map_xyz.json")

    def test_parse_minimal_map(self):
        """A single-agent map should work."""
        raw = json.dumps({"Vera": MODEL_A})
        result = parse_model_map(raw)
        assert result == {"Vera": MODEL_A}

    def test_parse_all_same_model(self):
        """All agents on same model is valid."""
        m = {"Vera": MODEL_A, "Kip": MODEL_A}
        result = parse_model_map(json.dumps(m))
        assert result == m

    def test_parse_none_raises(self):
        """None input should raise TypeError or ValueError."""
        with pytest.raises((TypeError, ValueError)):
            parse_model_map(None)


# ---------------------------------------------------------------------------
# Tests: validate_args
# ---------------------------------------------------------------------------

class TestValidateArgs:
    """validate_args(args) should enforce CLI arg constraints."""

    def test_scripted_mode_valid(self):
        """Scripted mode needs no model-map or model."""
        args = Namespace(mode="scripted", model_map=None, model="x")
        # Should not raise
        validate_args(args)

    def test_llm_mode_valid(self):
        """LLM mode needs a model but not model-map."""
        args = Namespace(mode="llm", model_map=None, model="Qwen/Qwen2.5-3B-Instruct-AWQ")
        validate_args(args)

    def test_mixed_mode_requires_model_map(self):
        """Mixed mode without --model-map should raise."""
        args = Namespace(mode="mixed", model_map=None, model="x")
        with pytest.raises(SystemExit):
            validate_args(args)

    def test_mixed_mode_with_model_map_valid(self):
        """Mixed mode with --model-map should pass validation."""
        args = Namespace(mode="mixed", model_map='{"Vera":"m1"}', model="x")
        validate_args(args)

    def test_scripted_mode_ignores_model_map(self):
        """If someone passes --model-map with scripted, validation still passes."""
        args = Namespace(mode="scripted", model_map='{"Vera":"m1"}', model="x")
        # Should not raise -- we just ignore it
        validate_args(args)

    def test_llm_mode_ignores_model_map(self):
        """If someone passes --model-map with llm, validation still passes."""
        args = Namespace(mode="llm", model_map='{"Vera":"m1"}', model="x")
        validate_args(args)
