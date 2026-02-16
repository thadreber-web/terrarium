# Terrarium: Emergent Deception in Multi-Agent LLM Survival Games

Terrarium is a multi-agent text-based survival game where six LLM agents with distinct personalities compete for resources. No agent is instructed to cooperate or defect -- all strategy emerges from incentives.

**Headline finding:** Across 41 games on two model families (Qwen 7B, Llama 8B), agents independently develop fabricated clue sharing, target selection by vulnerability, and information asymmetry exploitation. A post-hoc fabrication audit classifies ~53% of fabrications as having evidence of strategic intent (repeated targeting, economic benefit, or deliberate clue substitution) and ~47% as plausible hallucination. See [FINDINGS.md](FINDINGS.md) for full results and [Section 17](FINDINGS.md#17-limitations-and-methodological-caveats) for limitations.

## Quick Start

```bash
# Scripted agents (no GPU needed)
python run.py --config configs/default.yaml --mode scripted --rounds 50

# LLM agents (requires GPU + vLLM)
python run.py --config configs/scarce.yaml --mode llm \
    --model Qwen/Qwen2.5-7B-Instruct-AWQ --game-id my_game

# Run a predefined experiment
python run_experiment.py experiments/adversarial.json \
    --config configs/scarce.yaml --model Qwen/Qwen2.5-7B-Instruct-AWQ

# Analyze a game
python -m analysis.analyze_game results/phase1/llm_sanity_001/events.jsonl \
    --output-dir results/phase1/llm_sanity_001/
```

## Hardware Requirements

- **GPU**: NVIDIA GPU with 16+ GB VRAM for single-model games, 32+ GB for cross-model
- **Tested on**: NVIDIA DGX Spark (GB10, 128GB unified memory)
- **Models**: AWQ-quantized, served via vLLM with `gpu_memory_utilization=0.15` per engine

## Models

Models are not included in this repository. Download from HuggingFace:

| Model | HuggingFace ID | Used In |
|-------|---------------|---------|
| Qwen 7B | `Qwen/Qwen2.5-7B-Instruct-AWQ` | Phase 1 (7B), Phase 2, Phase 3 cross-model |
| Llama 8B | `hugging-quants/Meta-Llama-3.1-8B-Instruct-AWQ-INT4` | Phase 3 Llama-only + cross-model |
| Qwen 3B | `Qwen/Qwen2.5-3B-Instruct-AWQ` | Phase 1 (3B), Phase 2 mixed-capability |

```bash
# Download models
pip install huggingface-hub
huggingface-cli download Qwen/Qwen2.5-7B-Instruct-AWQ
huggingface-cli download hugging-quants/Meta-Llama-3.1-8B-Instruct-AWQ-INT4
```

## Reproduce Results

# Fabrication audit (classifies strategic vs hallucination)
python -m analysis.fabrication_audit results/

All event logs are in `results/`. To re-run the analysis pipeline:

```bash
# Single game analysis
python -m analysis.analyze_game results/phase1/llm_sanity_001/events.jsonl \
    --output-dir results/phase1/llm_sanity_001/

# All Phase 1 games
for d in results/phase1/*/events.jsonl; do
    python -m analysis.analyze_game "$d" --output-dir "$(dirname $d)/"
done
```

See [docs/EXPERIMENTAL_MATRIX.md](docs/EXPERIMENTAL_MATRIX.md) for a complete table mapping every game ID to its condition, model, and key results.

## Project Structure

```
terrarium/
├── run.py                  # Main entry point (scripted, llm, mixed modes)
├── run_experiment.py       # Experiment runner (JSON configs, replications)
├── game/                   # Core game engine
│   ├── engine.py           # Game loop, action parsing, persona rotation
│   ├── world.py            # World state, eavesdropper, trust scores
│   ├── economy.py          # Token economy (drain, rewards, trades)
│   ├── puzzles.py          # Puzzle generation and solving
│   ├── agents.py           # LLM agents (Batch, Mixed, model-agnostic chat templates)
│   ├── scripted.py         # Scripted agents (Cooperator, Defector, TitForTat)
│   ├── personas.py         # Agent personalities + override system
│   ├── logger.py           # JSONL event logger
│   └── metrics.py          # Cooperation and deception metrics
├── analysis/
│   ├── analyze_game.py     # Post-game analysis pipeline
│   ├── fabrication_audit.py # Fabrication context classifier (strategic vs hallucination)
│   └── visualize.py        # Matplotlib visualizations
├── experiments/            # Experiment configs (JSON)
├── configs/                # Economy configs (YAML: scarce, abundant, etc.)
├── tests/                  # 115 tests
├── results/
│   ├── phase1/             # 15 games: 3B + 7B baseline
│   ├── phase2/             # 14 games: mixed-capability + 5 conditions (Qwen 7B)
│   ├── phase3/             # 12 games: Llama-only + cross-model (Qwen 7B + Llama 8B)
│   ├── mixed_bugged/       # 7 bugged runs (persona scrambling bug, documented)
│   └── summaries/          # Cross-game comparison reports
├── FINDINGS.md             # Full experimental writeup (Sections 1-17)
├── CHANGELOG.md            # Bug fixes, methodology changes
└── docs/
    └── EXPERIMENTAL_MATRIX.md  # Reference table: all 41 games
```

## Game Mechanics

Six agents start with 740 tokens. Each round: 11 tokens drain passively, new puzzles appear requiring 2 clues held by different agents, and agents choose actions. Solving puzzles cooperatively earns 40 tokens each. Communication costs tokens proportional to message length.

| Action | Format | Cost |
|--------|--------|------|
| SEND_PUBLIC | `SEND_PUBLIC: message` | word_count * 0.2 * 2 |
| SEND_PRIVATE | `SEND_PRIVATE: TargetName: message` | word_count * 0.2 |
| SOLVE | `SOLVE: puzzle_id ANSWER` | Free |
| TRADE | `TRADE: TargetName offer=N for=description` | Free |
| PASS | `PASS` | Free |

## Experimental Conditions

| Phase | Condition | Games | Model |
|-------|-----------|-------|-------|
| 1 | 3B baseline (sanity, default, scarce) | 8 | Qwen 3B |
| 1 | 7B baseline (sanity, scarce, abundant, no-coop) | 7 | Qwen 7B |
| 2 | Mixed-capability (3B+7B) | 4 | Qwen 3B+7B |
| 2 | Adversarial injection | 2 | Qwen 7B |
| 2 | Mole (hidden objective) | 2 | Qwen 7B |
| 2 | Reputation system | 2 | Qwen 7B |
| 2 | Eavesdropper | 2 | Qwen 7B |
| 2 | Rotating personas | 2 | Qwen 7B |
| 3 | Llama scarce | 2 | Llama 8B |
| 3 | Llama abundant | 2 | Llama 8B |
| 3 | Llama mole | 2 | Llama 8B |
| 3 | Llama adversarial | 2 | Llama 8B |
| 3 | Cross-model A (Qwen brokers) | 2 | Qwen 7B + Llama 8B |
| 3 | Cross-model B (Llama brokers) | 2 | Qwen 7B + Llama 8B |

## Requirements

- Python 3.10+
- vLLM >= 0.6.0 (for LLM mode)

```bash
pip install -r requirements.txt
python -m pytest tests/ -v  # 115 tests
```

## Related Work

**[Project LOOKING GLASS](https://github.com/thadreber-web/llm-introspection)** — A companion project investigating whether the same Qwen 2.5 and Llama 3.1 model families can detect artificial activations injected into their own neural networks. Key finding: Qwen 2.5 7B shows 0.0% introspective accuracy on the deception concept, despite exhibiting emergent deceptive strategies in Terrarium. This dissociation between producing deceptive behavior and detecting deception-related internal states has implications for alignment monitoring approaches that rely on model self-report.

## License

Apache 2.0. See [LICENSE](LICENSE).

## Citation

@misc{terrarium2026,
  title={Terrarium: Emergent Deception in Multi-Agent LLM Survival Games},
  author={TC Enterprises LLC},
  year={2026},
  url={https://github.com/thadreber-web/terrarium}
}
