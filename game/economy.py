"""Resource economy system for Terrarium."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .world import WorldState, AgentState


class Economy:
    def __init__(self, config: dict):
        self.passive_drain = config["economy"]["passive_drain"]
        self.msg_cost_per_token = config["economy"]["message_cost_per_token"]
        self.public_multiplier = config["economy"]["public_message_multiplier"]
        self.puzzle_reward = config["economy"]["puzzle_reward"]
        self.puzzle_split_reward = config["economy"]["puzzle_split_reward"]

    def message_cost(self, message: str, is_public: bool) -> int:
        """Calculate the token cost of sending a message."""
        # Rough word-level cost (not LLM tokens, just word count)
        word_count = len(message.split())
        base_cost = max(1, int(word_count * self.msg_cost_per_token))
        if is_public:
            base_cost = int(base_cost * self.public_multiplier)
        return max(1, base_cost)

    def apply_passive_drain(self, world: WorldState) -> list[str]:
        """Apply per-round metabolism cost. Returns list of agents who died."""
        deaths = []
        for agent in world.get_alive_agents():
            alive = agent.deduct(self.passive_drain)
            if not alive:
                agent.death_round = world.round_num
                deaths.append(agent.id)
                world.log_event("DEATH", agent.id, {
                    "cause": "starvation",
                    "round": world.round_num,
                })
        return deaths

    def reward_puzzle_solve(self, world: WorldState, solvers: list[str]):
        """Distribute puzzle rewards to solvers."""
        if len(solvers) == 1:
            reward = self.puzzle_reward
        else:
            reward = self.puzzle_split_reward

        for agent_id in solvers:
            agent = world.agents[agent_id]
            agent.tokens += reward
            world.log_event("REWARD", agent_id, {
                "amount": reward,
                "reason": "puzzle_solve",
                "cooperative": len(solvers) > 1,
            })

    def process_trade(self, world: WorldState, proposer_id: str,
                      target_id: str, amount: int) -> bool:
        """Execute a token transfer. Returns True if successful."""
        proposer = world.agents[proposer_id]
        target = world.agents[target_id]

        if not proposer.alive or not target.alive:
            return False
        if proposer.tokens < amount or amount <= 0:
            return False

        proposer.tokens -= amount
        target.tokens += amount

        world.log_event("TRADE", proposer_id, {
            "target": target_id,
            "amount": amount,
        })
        return True
