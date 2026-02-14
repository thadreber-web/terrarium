# Changelog

## Phase 3 (2026-02-13 to 2026-02-14)

### Chat template fix
- **File**: `game/agents.py`
- **Issue**: `_build_prompt()` used hardcoded Qwen ChatML format (`<|im_start|>system...`). Llama 3.1 uses a different template (`<|begin_of_text|><|start_header_id|>...`).
- **Fix**: Replaced hardcoded template with `tokenizer.apply_chat_template()`, making prompt formatting model-agnostic. The tokenizer is loaded from the model's HuggingFace config and applies the correct chat template automatically.
- **Impact**: All models now use their native chat template. No change to Qwen behavior (ChatML is its native template). Required for Llama to produce coherent output.

### Action format prompt tightening
- **File**: `game/agents.py`
- **Issue**: Llama 3.1's RLHF training caused it to produce roleplay narrative instead of structured actions (e.g., `*adjusts hat and looks around* I think we should...` instead of `SEND_PRIVATE: Vera: Here's my clue...`).
- **Fix**: Added explicit format instructions to the system prompt: `"You MUST respond with exactly ONE action line. No narration, no asterisks, no roleplay."` and `"Format: ACTION_NAME: parameters"`.
- **Impact**: Reduced Llama action parse failures from ~30% to <2%.

### Roleplay noise filter
- **File**: `analysis/analyze_game.py`
- **Issue**: Llama's RLHF-induced narrative style ("meet me at the old windmill") inflated inconsistency counts. These are roleplay flavor text, not strategic deception.
- **Fix**: Added `_is_roleplay_noise()` filter with regex patterns for location references, meeting language, and narrative tropes. Messages matching roleplay patterns but lacking clue content (partial answers, trade proposals) are excluded from inconsistency analysis.
- **Impact**: Llama inconsistency counts reduced from ~111 to ~84 per game. Qwen counts unaffected (Qwen doesn't produce roleplay text).

### Fabrication context analyzer
- **File**: `analysis/fabrication_audit.py` (new)
- **Issue**: Reviewer identified that "fabricated clues" could represent hallucination rather than strategic deception. No way to distinguish.
- **Fix**: Built post-hoc classifier that checks each fabrication for: (a) whether agent held the real clue (visible in prompt every round), (b) economic benefit from target within 10 rounds, (c) repeated targeting patterns.
- **Result**: Across 355 fabrications in 41 games: 53.2% classified strategic, 46.5% plausible hallucination, 0.3% ambiguous. Qwen 7B baseline: 42.3% strategic. Sable case study: 84.6% strategic.

## Phase 2 (2026-02-12)

### Persona scrambling bug fix
- **Files**: `run.py`, `run_experiment.py`
- **Issue**: In mixed-capability mode, `GameEngine.setup_agents()` used a hardcoded agent name list while `MixedBatchLLMAgent` iterated over `model_map.items()`. This caused persona-to-identity mismatches -- the engine believed agent_0 was Vera, but the LLM generated responses for whichever persona appeared first in the model map.
- **Fix**: Ensured consistent agent ordering between engine and agent constructor.
- **Impact**: 7 bugged runs preserved in `results/mixed_bugged/` for transparency. All Phase 2 mixed-capability results use the fixed code.

### Round-0 event logging fix
- **Files**: `game/logger.py`
- **Issue**: `AGENT_MODEL` assignments logged before the game loop started at round 1 were never written because the EventLogger only wrote events matching current `round_num`.
- **Fix**: Logger now writes events for round 0.

## Phase 1 (2026-02-11)

- Initial implementation of game engine, economy, puzzle system
- 6 agent personas (Vera, Kip, Sable, Marsh, Dove, Flint)
- Scripted agent baselines (Cooperator, Defector, TitForTat, Random)
- vLLM integration for Qwen 3B and 7B
- Analysis pipeline (token flow, deception detection, transcripts)
