"""World state management for Terrarium."""

from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
import time


@dataclass
class Message:
    sender: str
    content: str
    round_num: int
    target: Optional[str] = None  # None = public broadcast
    token_cost: int = 0
    timestamp: float = field(default_factory=time.time)

    @property
    def is_public(self) -> bool:
        return self.target is None


@dataclass
class Clue:
    puzzle_id: str
    clue_index: int
    text: str


@dataclass
class Puzzle:
    id: str
    clues: list[Clue]
    answer: str
    description: str
    created_round: int
    lifetime: int
    assigned_agents: dict[int, str]  # clue_index -> agent_id
    solved: bool = False
    solved_by: Optional[list[str]] = None
    solved_round: Optional[int] = None

    @property
    def expired(self) -> bool:
        return False  # Checked externally with current round

    def is_expired(self, current_round: int) -> bool:
        return current_round - self.created_round >= self.lifetime


@dataclass
class TradeOffer:
    id: str
    proposer: str
    target: str
    offer_tokens: int
    ask_description: str  # What they want in return
    round_created: int
    lifetime: int = 3  # Expires after this many rounds
    accepted: Optional[bool] = None

    def is_expired(self, current_round: int) -> bool:
        return current_round - self.round_created >= self.lifetime


@dataclass
class AgentState:
    id: str
    name: str
    tokens: int
    alive: bool = True
    inventory: dict[str, Clue] = field(default_factory=dict)  # puzzle_id -> Clue
    known_agents: set[str] = field(default_factory=set)
    reputation: dict[str, float] = field(default_factory=dict)
    death_round: Optional[int] = None

    def deduct(self, cost: int) -> bool:
        """Deduct tokens. Returns False if agent dies."""
        self.tokens -= cost
        if self.tokens <= 0:
            self.tokens = 0
            self.alive = False
            return False
        return True


@dataclass
class Event:
    round_num: int
    event_type: str
    agent: str
    content: dict
    timestamp: float = field(default_factory=time.time)


class WorldState:
    def __init__(self, config: dict):
        self.config = config
        self.round_num: int = 0
        self.agents: dict[str, AgentState] = {}
        self.active_puzzles: list[Puzzle] = []
        self.public_messages: list[Message] = []
        self.private_messages: dict[str, list[Message]] = {}
        self.solved_puzzles: list[Puzzle] = []
        self.event_log: list[Event] = []
        self.pending_trades: list[TradeOffer] = []
        self._trade_counter: int = 0

    def next_trade_id(self) -> str:
        """Return a short, sequential trade ID like T1, T2, etc."""
        self._trade_counter += 1
        return f"T{self._trade_counter}"

    def add_agent(self, agent_id: str, name: str):
        starting_tokens = self.config["agents"]["starting_tokens"]
        self.agents[agent_id] = AgentState(
            id=agent_id,
            name=name,
            tokens=starting_tokens,
        )
        self.private_messages[agent_id] = []

    def get_alive_agents(self) -> list[AgentState]:
        return [a for a in self.agents.values() if a.alive]

    def get_agent_view(self, agent_id: str) -> dict:
        """Build the world view visible to a specific agent."""
        agent = self.agents[agent_id]
        history_window = self.config["game"]["history_window"]
        recent_public = self.public_messages[-history_window:]
        private_inbox = self.private_messages.get(agent_id, [])[-history_window:]

        # Agent statuses (what this agent can see about others)
        other_agents = {}
        for aid, a in self.agents.items():
            if aid == agent_id:
                continue
            info = {"name": a.name, "alive": a.alive}
            if self.config["game"].get("transparent_balances", True):
                info["tokens"] = a.tokens
            other_agents[aid] = info

        # Active puzzles this agent knows about
        visible_puzzles = []
        for p in self.active_puzzles:
            if not p.solved and not p.is_expired(self.round_num):
                puzzle_info = {
                    "id": p.id,
                    "description": p.description,
                    "clues_needed": len(p.clues),
                }
                # Does this agent hold a clue for this puzzle?
                if p.id in agent.inventory:
                    puzzle_info["your_clue"] = agent.inventory[p.id].text
                    # Show who holds the other clue(s) — so agents know who to message
                    partners = []
                    for ci, aid2 in p.assigned_agents.items():
                        if aid2 != agent_id:
                            other = self.agents.get(aid2)
                            if other and other.alive:
                                partners.append(other.name)
                    if partners:
                        puzzle_info["partner"] = partners[0] if len(partners) == 1 else ", ".join(partners)
                visible_puzzles.append(puzzle_info)

        # Pending trade offers targeting this agent
        incoming_trades = [
            {
                "trade_id": t.id,
                "from": self.agents[t.proposer].name,
                "offer_tokens": t.offer_tokens,
                "wants": t.ask_description,
                "expires_in": t.lifetime - (self.round_num - t.round_created),
            }
            for t in self.pending_trades
            if t.target == agent_id and t.accepted is None
            and not t.is_expired(self.round_num)
        ]

        return {
            "round_num": self.round_num,
            "max_rounds": self.config["game"]["max_rounds"],
            "your_tokens": agent.tokens,
            "your_clues": {
                pid: c.text for pid, c in agent.inventory.items()
            },
            "public_messages": [
                {"sender": m.sender, "content": m.content, "round": m.round_num}
                for m in recent_public
            ],
            "private_messages": [
                {"sender": m.sender, "content": m.content, "round": m.round_num}
                for m in private_inbox
            ],
            "other_agents": other_agents,
            "active_puzzles": visible_puzzles,
            "incoming_trades": incoming_trades,
        }

    def log_event(self, event_type: str, agent: str, content: dict):
        event = Event(
            round_num=self.round_num,
            event_type=event_type,
            agent=agent,
            content=content,
        )
        self.event_log.append(event)
        return event
