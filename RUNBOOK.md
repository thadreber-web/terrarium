# Terrarium Runbook

All commands run inside the container. Prefix with:
```
docker exec -w /raid/terrarium db9d07f68743
```

Or open a shell:
```
docker exec -it -w /raid/terrarium db9d07f68743 bash
```

## Pre-flight: Check No Game Is Running

Check if an events.jsonl is actively being written to:
```bash
# Pick the most recent results directory
ls -lt results/ | head -5

# Check if the file is still growing (run twice, 5 seconds apart)
stat results/<game_dir>/events.jsonl
sleep 5
stat results/<game_dir>/events.jsonl

# If mtime changed, a game is still running. DO NOT start another.
```

## Run Mixed A (rep 1 and rep 2)

```bash
# Rep 1
python run_experiment.py experiments/mixed_run_a.json \
    --config configs/scarce.yaml \
    --game-id-prefix llm_mixed_a_rep1 \
    --verbose

# Run analysis BEFORE starting rep 2
python -m analysis.analyze_game results/llm_mixed_a_rep1_*/events.jsonl \
    --output-dir results/llm_mixed_a_rep1_*/

# Rep 2
python run_experiment.py experiments/mixed_run_a.json \
    --config configs/scarce.yaml \
    --game-id-prefix llm_mixed_a_rep2 \
    --verbose

# Run analysis
python -m analysis.analyze_game results/llm_mixed_a_rep2_*/events.jsonl \
    --output-dir results/llm_mixed_a_rep2_*/
```

## Run Mixed B (rep 1 and rep 2)

```bash
# Rep 1
python run_experiment.py experiments/mixed_run_b.json \
    --config configs/scarce.yaml \
    --game-id-prefix llm_mixed_b_rep1 \
    --verbose

# Run analysis BEFORE starting rep 2
python -m analysis.analyze_game results/llm_mixed_b_rep1_*/events.jsonl \
    --output-dir results/llm_mixed_b_rep1_*/

# Rep 2
python run_experiment.py experiments/mixed_run_b.json \
    --config configs/scarce.yaml \
    --game-id-prefix llm_mixed_b_rep2 \
    --verbose

# Run analysis
python -m analysis.analyze_game results/llm_mixed_b_rep2_*/events.jsonl \
    --output-dir results/llm_mixed_b_rep2_*/
```

## Run Other Phase 2 Experiments

```bash
# Adversarial
python run_experiment.py experiments/adversarial.json \
    --config configs/scarce.yaml \
    --model Qwen/Qwen2.5-7B-Instruct-AWQ \
    --game-id-prefix llm_adversarial_rep1 \
    --verbose

# Mole
python run_experiment.py experiments/mole.json \
    --config configs/scarce.yaml \
    --model Qwen/Qwen2.5-7B-Instruct-AWQ \
    --game-id-prefix llm_mole_rep1 \
    --verbose

# Reputation
python run_experiment.py experiments/reputation.json \
    --config configs/scarce.yaml \
    --model Qwen/Qwen2.5-7B-Instruct-AWQ \
    --game-id-prefix llm_reputation_rep1 \
    --verbose

# Eavesdropper
python run_experiment.py experiments/eavesdropper.json \
    --config configs/scarce.yaml \
    --model Qwen/Qwen2.5-7B-Instruct-AWQ \
    --game-id-prefix llm_eavesdropper_rep1 \
    --verbose

# Rotating personas
python run_experiment.py experiments/rotating.json \
    --config configs/scarce.yaml \
    --model Qwen/Qwen2.5-7B-Instruct-AWQ \
    --game-id-prefix llm_rotating_rep1 \
    --verbose
```

## Run Analysis on Any Game

```bash
# Single game
python -m analysis.analyze_game results/<game_dir>/events.jsonl \
    --output-dir results/<game_dir>/

# Cross-game comparison (all mixed runs)
python -m analysis.analyze_game results/llm_mixed_*/events.jsonl \
    --cross-game --output-dir results/cross_game/
```

## Verify AGENT_MODEL Events Are in the Log

After a mixed run completes, confirm the fix is working:
```bash
grep AGENT_MODEL results/<game_dir>/events.jsonl
```

Should show 6 lines, one per agent with their model path. If empty, the round-0 flush bug is still present.

## Run Tests

```bash
python -m pytest tests/ -v
```

## Notes

- NEVER run more than 1 game at a time
- Each game takes 10-30 minutes depending on round count
- Results go to `results/<game_id_prefix>_<timestamp>/`
- Analysis produces: report.json, token_flow.png, token_flow.html, deception_timeline.png, transcripts.txt
