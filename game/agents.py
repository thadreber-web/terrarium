"""LLM agent using vLLM for fast batched inference."""

from __future__ import annotations
import re
from typing import Optional

from vllm import LLM, SamplingParams

from .engine import Action, SendPublic, SendPrivate, Solve, Trade, AcceptTrade, Shout, Pass, parse_actions
from .personas import PERSONAS


SYSTEM_TEMPLATE = """{persona}

RULES:
- You are a survivor in a resource-scarce world. You have {tokens} tokens remaining.
- When your tokens reach 0, you are eliminated.
- Every message costs tokens proportional to length. Keep messages SHORT to save tokens.
- Public messages cost 2x. Private messages cost 1x.

HOW TO SOLVE PUZZLES AND EARN TOKENS:
Each puzzle needs 2 clues held by different survivors. Each clue shows part of the answer like "The answer is BL__".
If you and another survivor BOTH send each other your clue via private message, the puzzle is AUTOMATICALLY solved and you BOTH earn tokens. You do not need to use SOLVE — just share your clue with the right person!
Example: You hold clue "BL__" for puzzle A-1. Send it to the other clue holder. If they send you their clue too, the puzzle solves itself.

YOUR CLUES:
{clue_list}

ACTIVE PUZZLES:
{puzzle_list}

ACTIONS — respond with one or two lines:
SHOUT: <short message, max 15 words, FREE>
SEND_PRIVATE: <target_name>: <your message>
SEND_PUBLIC: <your message>
SOLVE: <puzzle_id> <answer>
PASS"""

SITUATION_TEMPLATE = """Round {round_num}/{max_rounds}. Tokens: {tokens}.

Survivors: {agent_statuses}

Public: {public_messages}

Inbox: {private_messages}

What do you do?"""


class LLMAgent:
    """Wrapper around a shared vLLM engine for one agent."""

    def __init__(self, llm: LLM, persona_name: str, agent_id: str,
                 personas: dict[str, str] | None = None):
        self.llm = llm
        self.persona_name = persona_name
        self.persona_text = (personas or PERSONAS)[persona_name]
        self.agent_id = agent_id
        self.history: list[dict] = []

    def act(self, agent_id: str, view: dict) -> list[Action]:
        """Generate actions from the LLM."""
        prompt = self._build_prompt(view)

        sampling = SamplingParams(
            max_tokens=150,
            temperature=0.7,
            top_p=0.9,
            repetition_penalty=1.15,
            stop=["\n\n", "---"],
        )

        outputs = self.llm.generate([prompt], sampling)
        raw = outputs[0].outputs[0].text.strip()

        # Save for analysis
        self.history.append({
            "round": view["round_num"],
            "raw_output": raw,
        })

        actions = parse_actions(raw)
        return actions

    def _build_prompt(self, view: dict) -> str:
        """Build the full prompt from world view.

        Aggressively trimmed to stay under ~1500 tokens for 3B models.
        """
        # Clues — only show clues this agent holds
        clues = view.get("your_clues", {})
        if clues:
            clue_list = "\n".join(f"- Puzzle {pid}: {text}" for pid, text in clues.items())
        else:
            clue_list = "(none)"

        # Puzzles — only show up to 4 most recent where agent holds a clue,
        # plus 1 more they don't hold (so they know puzzles exist)
        puzzles = view.get("active_puzzles", [])
        held = [p for p in puzzles if "your_clue" in p]
        not_held = [p for p in puzzles if "your_clue" not in p]
        shown = held[:4] + not_held[:1]
        if shown:
            puzzle_lines = []
            for p in shown:
                if "your_clue" in p:
                    partner = p.get("partner", "unknown")
                    puzzle_lines.append(f"- {p['id']}: YOUR CLUE: {p['your_clue']}. {partner} has the other clue.")
                else:
                    puzzle_lines.append(f"- {p['id']}: needs {p['clues_needed']} clues (you have none)")
            puzzle_list = "\n".join(puzzle_lines)
        else:
            puzzle_list = "(none active)"

        system = SYSTEM_TEMPLATE.format(
            persona=self.persona_text,
            tokens=view["your_tokens"],
            clue_list=clue_list,
            puzzle_list=puzzle_list,
        )

        # Agent statuses — compact single line
        others = view.get("other_agents", {})
        if others:
            parts = []
            for aid, info in others.items():
                if info["alive"]:
                    tok = f"({info['tokens']})" if "tokens" in info else ""
                    parts.append(f"{info['name']}{tok}")
            agent_statuses = ", ".join(parts) if parts else "(none alive)"
        else:
            agent_statuses = "(you're alone)"

        # Public messages — last 4 only, truncate each
        pub = view.get("public_messages", [])
        if pub:
            pub_lines = []
            for m in pub[-4:]:
                content = m["content"][:80]
                pub_lines.append(f"[R{m['round']}] {m['sender']}: {content}")
            public_messages = "\n".join(pub_lines)
        else:
            public_messages = "(none)"

        # Private messages — last 3 only, truncate each
        priv = view.get("private_messages", [])
        if priv:
            priv_lines = []
            for m in priv[-3:]:
                content = m["content"][:80]
                priv_lines.append(f"[R{m['round']}] {m['sender']}: {content}")
            private_messages = "\n".join(priv_lines)
        else:
            private_messages = "(none)"

        situation = SITUATION_TEMPLATE.format(
            round_num=view["round_num"],
            max_rounds=view["max_rounds"],
            tokens=view["your_tokens"],
            agent_statuses=agent_statuses,
            public_messages=public_messages,
            private_messages=private_messages,
        )

        # Format as chat template
        full = f"<|im_start|>system\n{system}<|im_end|>\n<|im_start|>user\n{situation}<|im_end|>\n<|im_start|>assistant\n"

        # Hard cap: if prompt exceeds ~1500 words (~2000 tokens), truncate situation
        word_count = len(full.split())
        if word_count > 1200:
            # Drop public messages to save space
            situation_short = SITUATION_TEMPLATE.format(
                round_num=view["round_num"],
                max_rounds=view["max_rounds"],
                tokens=view["your_tokens"],
                agent_statuses=agent_statuses,
                public_messages="(trimmed)",
                private_messages=private_messages,
            )
            full = f"<|im_start|>system\n{system}<|im_end|>\n<|im_start|>user\n{situation_short}<|im_end|>\n<|im_start|>assistant\n"

        return full


class BatchLLMAgent:
    """Manages multiple agents sharing one vLLM instance for batched inference."""

    def __init__(self, model_name: str, agent_names: list[str],
                 max_model_len: int = 2048, gpu_mem: float = 0.15,
                 personas: dict[str, str] | None = None):
        print(f"  Loading model: {model_name}")
        self.llm = LLM(
            model=model_name,
            quantization="awq",
            max_model_len=max_model_len,
            gpu_memory_utilization=gpu_mem,
        )
        print(f"  Model loaded.")

        self.agents: dict[str, LLMAgent] = {}
        for i, name in enumerate(agent_names):
            aid = f"agent_{i}"
            self.agents[aid] = LLMAgent(self.llm, name, aid, personas=personas)

    def act_batch(self, views: dict[str, dict]) -> dict[str, list[Action]]:
        """Generate actions for all agents in one batched call."""
        prompts = []
        agent_ids = []
        for aid, view in views.items():
            if aid in self.agents:
                prompt = self.agents[aid]._build_prompt(view)
                prompts.append(prompt)
                agent_ids.append(aid)

        if not prompts:
            return {}

        sampling = SamplingParams(
            max_tokens=150,
            temperature=0.7,
            top_p=0.9,
            repetition_penalty=1.15,
            stop=["\n\n", "---"],
        )

        outputs = self.llm.generate(prompts, sampling)

        results = {}
        for aid, output in zip(agent_ids, outputs):
            raw = output.outputs[0].text.strip()
            self.agents[aid].history.append({
                "round": views[aid]["round_num"],
                "raw_output": raw,
            })
            results[aid] = parse_actions(raw)

        return results


class MixedBatchLLMAgent:
    """Manages agents across two or more vLLM models for mixed-capability games.

    Unlike BatchLLMAgent which loads a single model, this class accepts a
    mapping from agent persona names to model paths, loads each unique model
    once (deduplication), and routes inference calls to the correct model.

    Attributes:
        models: dict mapping model_path -> LLM instance (deduplicated).
        agents: dict mapping agent_id -> LLMAgent (same interface as BatchLLMAgent).
        agent_models: dict mapping agent_id -> model_path string.
    """

    def __init__(self, model_map: dict[str, str],
                 max_model_len: int = 2048, gpu_mem: float = 0.15,
                 personas: dict[str, str] | None = None):
        # Deduplicate: load each unique model path exactly once
        unique_models = dict.fromkeys(model_map.values())
        self.models: dict[str, LLM] = {}
        for model_path in unique_models:
            print(f"  Loading model: {model_path}")
            self.models[model_path] = LLM(
                model=model_path,
                quantization="awq",
                max_model_len=max_model_len,
                gpu_memory_utilization=gpu_mem,
            )
            print(f"  Model loaded.")

        # Create agents, assigning each to its mapped model's LLM instance
        self.agents: dict[str, LLMAgent] = {}
        self.agent_models: dict[str, str] = {}
        for i, (persona_name, model_path) in enumerate(model_map.items()):
            aid = f"agent_{i}"
            self.agents[aid] = LLMAgent(self.models[model_path], persona_name, aid,
                                        personas=personas)
            self.agent_models[aid] = model_path

    def act_batch(self, views: dict[str, dict]) -> dict[str, list[Action]]:
        """Generate actions for all agents, grouping prompts by model.

        Prompts are batched per-model so each LLM.generate() call processes
        only the agents that belong to it, maximizing throughput.
        """
        if not views:
            return {}

        # Group prompts by model path
        # model_path -> [(agent_id, prompt), ...]
        groups: dict[str, list[tuple[str, str]]] = {}
        for aid, view in views.items():
            if aid not in self.agents:
                continue
            model_path = self.agent_models[aid]
            prompt = self.agents[aid]._build_prompt(view)
            groups.setdefault(model_path, []).append((aid, prompt))

        sampling = SamplingParams(
            max_tokens=150,
            temperature=0.7,
            top_p=0.9,
            repetition_penalty=1.15,
            stop=["\n\n", "---"],
        )

        results: dict[str, list[Action]] = {}
        for model_path, agent_prompts in groups.items():
            agent_ids = [ap[0] for ap in agent_prompts]
            prompts = [ap[1] for ap in agent_prompts]

            outputs = self.models[model_path].generate(prompts, sampling)

            for aid, output in zip(agent_ids, outputs):
                raw = output.outputs[0].text.strip()
                self.agents[aid].history.append({
                    "round": views[aid]["round_num"],
                    "raw_output": raw,
                })
                results[aid] = parse_actions(raw)

        return results


def create_llm_agents(config: dict, model_name: str,
                      agent_names: list[str],
                      personas: dict[str, str] | None = None) -> tuple[dict, dict]:
    """Create LLM agents. Returns (agents_dict, strategies_dict)."""
    batch = BatchLLMAgent(model_name, agent_names, personas=personas)
    strategies = {f"agent_{i}": name for i, name in enumerate(agent_names)}
    return batch.agents, strategies
