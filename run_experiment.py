"""Unified Experiment Runner for Terrarium.

Reads an experiment JSON file, applies model-map, persona-overrides, and
config-overrides, then calls run_game() from run.py.  Supports --repeat N
for running replications.

Usage:
    python run_experiment.py experiments/mixed_run_a.json --config configs/scarce.yaml --repeat 2
    python run_experiment.py experiments/adversarial.json --config configs/scarce.yaml --model Qwen/Qwen2.5-7B-Instruct-AWQ
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import yaml
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from run import run_game
from game.personas import apply_persona_overrides


def load_experiment(path: str) -> dict:
    """Load an experiment definition from a JSON file.

    Args:
        path: Path to the experiment JSON file.

    Returns:
        The parsed experiment dict.

    Raises:
        FileNotFoundError: if the file does not exist.
        json.JSONDecodeError: if the file is not valid JSON.
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Experiment file not found: {path}")
    with open(p) as f:
        return json.load(f)


def build_run_args(
    experiment: dict,
    default_model: str | None = None,
    game_id_prefix: str | None = None,
    verbose: bool = False,
) -> dict:
    """Convert an experiment dict into keyword arguments for run_game().

    Args:
        experiment: Parsed experiment dict (from load_experiment).
        default_model: Default model name for LLM mode (when no model_map).
        game_id_prefix: Optional prefix for the game_id.
        verbose: Whether to enable verbose output.

    Returns:
        A dict of kwargs suitable for passing to run_game().
    """
    model_map = experiment.get("model_map")
    persona_overrides = experiment.get("persona_overrides")

    # Determine mode based on presence of model_map
    if model_map:
        mode = "mixed"
        model_map_raw = json.dumps(model_map)
        model_name = None
    else:
        mode = "llm"
        model_map_raw = None
        model_name = default_model

    # Apply persona overrides if present
    active_personas = None
    if persona_overrides:
        active_personas = apply_persona_overrides(persona_overrides)

    # Build game_id
    if game_id_prefix:
        game_id = f"{game_id_prefix}_{int(time.time())}"
    else:
        game_id = None  # let run_game generate it

    return {
        "mode": mode,
        "model_name": model_name,
        "model_map_raw": model_map_raw,
        "active_personas": active_personas,
        "game_id": game_id,
        "verbose": verbose,
    }


def apply_config_overrides(config: dict, overrides: dict | None) -> dict:
    """Deep-merge overrides into a base config dict.

    Performs a recursive merge: for keys whose values are dicts in both
    config and overrides, the merge is applied recursively.  For all other
    keys, the override value replaces the base value.

    The original config dict is NOT mutated.

    Args:
        config: Base configuration dict.
        overrides: Dict of overrides to merge in. May be None or empty.

    Returns:
        A new dict with overrides applied.
    """
    result = deepcopy(config)
    if not overrides:
        return result

    def _deep_merge(base: dict, updates: dict) -> dict:
        for key, value in updates.items():
            if (
                key in base
                and isinstance(base[key], dict)
                and isinstance(value, dict)
            ):
                _deep_merge(base[key], value)
            else:
                base[key] = deepcopy(value)
        return base

    _deep_merge(result, overrides)
    return result


def main():
    parser = argparse.ArgumentParser(
        description="Terrarium Experiment Runner: load experiment JSON and run game(s)."
    )
    parser.add_argument(
        "experiment",
        help="Path to experiment JSON file",
    )
    parser.add_argument(
        "--config",
        default="configs/default.yaml",
        help="Path to base YAML config file (default: configs/default.yaml)",
    )
    parser.add_argument(
        "--model",
        default="Qwen/Qwen2.5-3B-Instruct-AWQ",
        help="Default model for LLM mode (used when experiment has no model_map)",
    )
    parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Number of replications to run (default: 1)",
    )
    parser.add_argument(
        "--game-id-prefix",
        default=None,
        help="Prefix for game IDs (default: derived from experiment filename)",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose output during game",
    )
    args = parser.parse_args()

    # Load experiment definition
    experiment = load_experiment(args.experiment)

    # Derive game-id prefix from experiment filename if not provided
    game_id_prefix = args.game_id_prefix
    if game_id_prefix is None:
        game_id_prefix = Path(args.experiment).stem

    # Load base config
    with open(args.config) as f:
        config = yaml.safe_load(f)
    config["_config_path"] = args.config

    # Apply config overrides from experiment
    config_overrides = experiment.get("config_overrides")
    if config_overrides:
        config = apply_config_overrides(config, config_overrides)

    # Build run_game kwargs from experiment
    run_kwargs = build_run_args(
        experiment,
        default_model=args.model,
        game_id_prefix=game_id_prefix,
        verbose=args.verbose,
    )

    # Print experiment summary
    print(f"\n  EXPERIMENT: {args.experiment}")
    print(f"  Notes: {experiment.get('notes', '(none)')}")
    print(f"  Mode: {run_kwargs['mode']}")
    print(f"  Replications: {args.repeat}")
    if experiment.get("persona_overrides"):
        names = ", ".join(experiment["persona_overrides"].keys())
        print(f"  Persona overrides: {names}")
    if experiment.get("config_overrides"):
        print(f"  Config overrides: {json.dumps(config_overrides, indent=2)}")
    print()

    # Run replications
    all_results = []
    for i in range(args.repeat):
        if args.repeat > 1:
            print(f"\n  === Replication {i + 1}/{args.repeat} ===")
            # Generate unique game_id per replication
            rep_kwargs = dict(run_kwargs)
            rep_kwargs["game_id"] = f"{game_id_prefix}_rep{i + 1}_{int(time.time())}"
        else:
            rep_kwargs = run_kwargs

        final_stats, round_metrics = run_game(
            config=deepcopy(config),  # fresh copy per run
            mode=rep_kwargs["mode"],
            model_name=rep_kwargs.get("model_name"),
            game_id=rep_kwargs.get("game_id"),
            verbose=rep_kwargs.get("verbose", False),
            model_map_raw=rep_kwargs.get("model_map_raw"),
            active_personas=rep_kwargs.get("active_personas"),
        )
        all_results.append((final_stats, round_metrics))

    # Summary across replications
    if args.repeat > 1:
        print(f"\n  {'='*50}")
        print(f"  EXPERIMENT COMPLETE — {args.repeat} replications")
        for i, (stats, _) in enumerate(all_results):
            survivors = ", ".join(stats["survivors"]) or "none"
            print(f"    Rep {i + 1}: rounds={stats['total_rounds']}, "
                  f"survivors=[{survivors}], "
                  f"puzzles={stats['puzzles_solved']}")
        print()

    return all_results


if __name__ == "__main__":
    main()
