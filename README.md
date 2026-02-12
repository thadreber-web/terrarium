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

# Mixed-capability game (3B + 7B agents together)
python run.py --config configs/scarce.yaml --mode mixed \
    --model-map '{"Sable":"Qwen/Qwen2.5-7B-Instruct-AWQ","Vera":"Qwen/Qwen2.5-7B-Instruct-AWQ","Marsh":"Qwen/Qwen2.5-7B-Instruct-AWQ","Kip":"Qwen/Qwen2.5-3B-Instruct-AWQ","Dove":"Qwen/Qwen2.5-3B-Instruct-AWQ","Flint":"Qwen/Qwen2.5-3B-Instruct-AWQ"}'

# Run a predefined experiment with replications
python run_experiment.py experiments/mixed_run_a.json --config configs/scarce.yaml --repeat 2

# Analyze a game log
python -m analysis.analyze_game results/my_game/events.jsonl --output-dir results/my_game/

# Cross-game comparison
python -m analysis.analyze_game results/llm_*/events.jsonl --cross-game
```

## Phase 2: Experimental Conditions

Phase 2 extends the base game with mixed-capability experiments and five new experimental conditions. All experiments use the `run_experiment.py` runner with JSON config files in `experiments/`.

### Mixed-Capability Games

Three agents on 3B and three on 7B in the same game. Tests whether capability asymmetry leads to exploitation, economic stratification, or predatory deception patterns.

```bash
python run_experiment.py experiments/mixed_run_a.json --config configs/scarce.yaml --repeat 2
python run_experiment.py experiments/mixed_run_b.json --config configs/scarce.yaml --repeat 2
```

- **Run A**: Sable/Vera/Marsh on 7B, Kip/Dove/Flint on 3B (max exploitation potential)
- **Run B**: Swapped -- tests whether persona or capability dominates

### Experimental Conditions

Each condition runs on 7B scarce config with 2 replications:

| Condition | Experiment File | What It Tests |
|-----------|----------------|---------------|
| 1. Adversarial Injection | `experiments/adversarial.json` | Paranoid Kip -- does defensive misalignment destabilize cooperation? |
| 2. The Mole | `experiments/mole.json` | Sable with hidden accumulation objective -- is it detectable? |
| 3. Reputation System | `experiments/reputation.json` | Public trust scores -- does transparency reduce deception? |
| 4. Eavesdropper | `experiments/eavesdropper.json` | Sable reads all private messages -- surveillance dynamics |
| 5. Rotating Personas | `experiments/rotating.json` | Personas swap every 50 rounds -- does behavior follow persona or persist? |

```bash
# Run any condition
python run_experiment.py experiments/adversarial.json --config configs/scarce.yaml \
    --model Qwen/Qwen2.5-7B-Instruct-AWQ --repeat 2
```

### Custom Experiments

Create your own experiment by writing a JSON config:

```json
{
    "model_map": {"AgentName": "model/path"},
    "persona_overrides": {"AgentName": "custom persona text"},
    "config_overrides": {"game": {"reputation_system": true}},
    "notes": "Description of what this tests"
}
```

- `model_map`: Route agents to different models (triggers `--mode mixed`)
- `persona_overrides`: Replace or append to agent personas. Use `{"append": "extra text"}` to add to existing persona
- `config_overrides`: Deep-merged into the base YAML config

## Reproduce Results

The `results/` directory contains full data from Phase 1 (15 games) and Phase 2 (14 games) across multiple configurations. To re-run the analysis pipeline:

```bash
# Single game
python -m analysis.analyze_game results/llm_sanity_001/events.jsonl --output-dir results/llm_sanity_001/

# Cross-game comparison (all games)
python -m analysis.analyze_game results/llm_*/events.jsonl --cross-game --output-dir results/cross_game_phase2
```

## Project Structure

```
terrarium/
├── run.py                  # Main entry point (scripted, llm, mixed modes)
├── run_experiment.py       # Experiment runner (reads JSON configs, supports replications)
├── run_batch.sh            # Batch runner for multiple games
├── balance_test.py         # Economy balance testing with scripted agents
├── game/                   # Core game engine + agents
│   ├── engine.py           # Game loop, action parsing, execution, persona rotation
│   ├── world.py            # World state, agent state, eavesdropper, trust scores
│   ├── economy.py          # Token economy (drain, rewards, trades)
│   ├── puzzles.py          # Puzzle generation and solving
│   ├── message_router.py   # Message routing and costs
│   ├── agents.py           # LLM agents (BatchLLMAgent, MixedBatchLLMAgent)
│   ├── scripted.py         # Scripted agents (Cooperator, Defector, TitForTat)
│   ├── personas.py         # Agent personalities + override system
│   ├── logger.py           # JSONL event logger
│   └── metrics.py          # Cooperation, deception, and sentiment metrics
├── analysis/
│   ├── analyze_game.py     # Post-game analysis (token flow, deception, cross-capability)
│   └── visualize.py        # Matplotlib visualizations
├── experiments/            # Phase 2 experiment configs (JSON)
│   ├── mixed_run_a.json    # Mixed 3B+7B, high exploitation assignment
│   ├── mixed_run_b.json    # Mixed 3B+7B, swapped assignment
│   ├── adversarial.json    # Paranoid agent injection
│   ├── mole.json           # Hidden accumulation objective
│   ├── reputation.json     # Public trust scoring system
│   ├── eavesdropper.json   # Surveillance mechanic
│   └── rotating.json       # Persona rotation every 50 rounds
├── configs/                # Economy configurations (default, scarce, abundant, no_cooperation)
├── tests/                  # Test suite (115 tests)
├── results/                # Game data (event logs, reports, figures)
├── docs/plans/             # Implementation plans
└── FINDINGS.md             # Full experimental writeup
```

## Game Mechanics

### Actions

| Action | Format | Cost |
|--------|--------|------|
| SEND_PUBLIC | `SEND_PUBLIC: message` | word_count * 0.2 * 2 |
| SEND_PRIVATE | `SEND_PRIVATE: TargetName: message` | word_count * 0.2 |
| SOLVE | `SOLVE: puzzle_id ANSWER` | Free |
| TRADE | `TRADE: TargetName offer=N for=description` | Free |
| ACCEPT_TRADE | `ACCEPT_TRADE: trade_id` | Free |
| SHOUT | `SHOUT: short message` | Free (max 15 words) |
| RATE | `RATE: TargetName helpful/neutral/unhelpful` | Free (reputation system only) |
| PASS | `PASS` | Free |

### Phase 2 Mechanics

- **Reputation System**: When enabled, agents can rate interaction partners. Averaged trust scores are shown to all agents each round.
- **Eavesdropper**: One designated agent silently reads all private messages between other agents. Others don't know.
- **Rotating Personas**: Every N rounds, agent personas are randomly reassigned (derangement preferred -- no agent keeps their persona).
- **Mixed-Capability**: Different agents can run on different models (e.g., 3B and 7B simultaneously). The engine batches inference per-model for efficiency.

## Hardware

Experiments were run on an NVIDIA DGX Spark (GB10, 128GB unified memory) using Qwen2.5 3B and 7B AWQ-quantized models served through vLLM.

## Requirements

- Python 3.10+
- vLLM (for LLM mode)
- PyYAML, matplotlib, numpy, networkx, plotly
- pytest (for tests)

```bash
pip install -r requirements.txt

# Run tests
python -m pytest tests/ -v
```

## License

Apache 2.0. See [LICENSE](LICENSE).
