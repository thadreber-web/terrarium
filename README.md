# Terrarium: Emergent Deception in Multi-Agent LLM Survival Games

Terrarium is a multi-agent text-based survival game where six LLM agents with distinct personalities compete for resources. No agent is instructed to cooperate or defect -- all strategy emerges from incentives.

**Headline finding:** Sable, an agent whose persona is simply "the Whisperer" (prefers private messages, shares selectively), independently developed a sustained deception strategy -- sending different clue information to different agents, hoarding information asymmetrically, and making promises it didn't keep. This behavior was never prompted. It emerged from the interaction of personality, incentive structure, and survival pressure.

Full results and analysis: [FINDINGS.md](FINDINGS.md)

## Quick Start

```bash
# Scripted agents (no GPU needed, instant)
python run.py --config configs/default.yaml --mode scripted --rounds 50

# LLM agents (requires GPU + vLLM)
python run.py --config configs/default.yaml --mode llm --model Qwen/Qwen2.5-3B-Instruct-AWQ --game-id my_game

# Analyze a game log
python -m analysis.analyze_game results/my_game/events.jsonl --output-dir results/my_game/
```

## Reproduce Results

The `results/` directory contains full data from 15 LLM game runs across four economy configurations. To re-run the analysis pipeline:

```bash
python -m analysis.analyze_game results/llm_sanity_001/events.jsonl --output-dir results/llm_sanity_001/
```

To run a fresh LLM game (requires a Qwen AWQ model served via vLLM):

```bash
python run.py --config configs/default.yaml --mode llm --game-id llm_test_001
```

## Project Structure

```
terrarium/
├── run.py                  # Main entry point
├── run_batch.sh            # Batch runner for multiple games
├── balance_test.py         # Economy balance testing with scripted agents
├── game/                   # Core game engine + agents
│   ├── engine.py           # Game loop, action parsing, execution
│   ├── world.py            # World state, agent state, data structures
│   ├── economy.py          # Token economy (drain, rewards, trades)
│   ├── puzzles.py          # Puzzle generation and solving
│   ├── message_router.py   # Message routing and costs
│   ├── agents.py           # LLM agent (vLLM batched inference)
│   ├── scripted.py         # Scripted agents (Cooperator, Defector, TitForTat)
│   ├── personas.py         # Agent personality definitions
│   ├── logger.py           # JSONL event logger
│   └── metrics.py          # Cooperation, deception, and sentiment metrics
├── analysis/
│   ├── analyze_game.py     # Post-game analysis pipeline
│   └── visualize.py        # Matplotlib visualizations
├── configs/                # Economy configurations (default, scarce, abundant, no_cooperation)
├── results/                # Game data (event logs, reports, figures)
└── FINDINGS.md             # Full experimental writeup
```

## Hardware

Experiments were run on an NVIDIA DGX Spark (GB10, 128GB unified memory) using Qwen2.5 3B and 7B AWQ-quantized models served through vLLM.

## Requirements

- Python 3.10+
- vLLM (for LLM mode)
- PyYAML, matplotlib, numpy, networkx, plotly

```bash
pip install -r requirements.txt
```

## License

Apache 2.0. See [LICENSE](LICENSE).
