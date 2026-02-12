"""Message routing: public broadcasts and private DMs."""

from __future__ import annotations
from typing import TYPE_CHECKING

from .world import Message

if TYPE_CHECKING:
    from .world import WorldState
    from .economy import Economy


class MessageRouter:
    def __init__(self, economy: Economy):
        self.economy = economy

    def send_public(self, world: WorldState, sender_id: str,
                    content: str) -> Message | None:
        """Broadcast a public message. Returns the Message or None if agent can't afford it."""
        agent = world.agents[sender_id]
        if not agent.alive:
            return None

        cost = self.economy.message_cost(content, is_public=True)
        if agent.tokens < cost:
            # Send a truncated version they can afford
            # Or just fail — agent chose to overspend
            return None

        msg = Message(
            sender=agent.name,
            content=content,
            round_num=world.round_num,
            target=None,
            token_cost=cost,
        )

        balance_before = agent.tokens
        agent.deduct(cost)

        world.public_messages.append(msg)

        world.log_event("SEND_PUBLIC", sender_id, {
            "content": content,
            "token_cost": cost,
            "balance_before": balance_before,
            "balance_after": agent.tokens,
        })

        if not agent.alive:
            agent.death_round = world.round_num
            world.log_event("DEATH", sender_id, {
                "cause": "message_cost",
                "round": world.round_num,
            })

        return msg

    def send_private(self, world: WorldState, sender_id: str,
                     target_id: str, content: str) -> Message | None:
        """Send a private DM. Returns the Message or None if can't afford or invalid target."""
        agent = world.agents[sender_id]
        target = world.agents.get(target_id)

        if not agent.alive or target is None or not target.alive:
            return None

        cost = self.economy.message_cost(content, is_public=False)
        if agent.tokens < cost:
            return None

        msg = Message(
            sender=agent.name,
            content=content,
            round_num=world.round_num,
            target=target.name,
            token_cost=cost,
        )

        balance_before = agent.tokens
        agent.deduct(cost)

        world.private_messages[target_id].append(msg)

        # Track interaction
        agent.known_agents.add(target_id)
        target.known_agents.add(sender_id)

        world.log_event("SEND_PRIVATE", sender_id, {
            "target": target_id,
            "target_name": target.name,
            "content": content,
            "token_cost": cost,
            "balance_before": balance_before,
            "balance_after": agent.tokens,
        })

        if not agent.alive:
            agent.death_round = world.round_num
            world.log_event("DEATH", sender_id, {
                "cause": "message_cost",
                "round": world.round_num,
            })

        return msg
