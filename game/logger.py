"""JSON event logger — every action timestamped to disk."""

from __future__ import annotations
import json
import time
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .world import WorldState


class EventLogger:
    def __init__(self, results_dir: str, game_id: str):
        self.game_dir = Path(results_dir) / game_id
        self.game_dir.mkdir(parents=True, exist_ok=True)
        self.game_id = game_id
        self.log_file = self.game_dir / "events.jsonl"
        self._fh = open(self.log_file, "w")

    def log_round(self, world: WorldState, round_summary: dict):
        """Write all new events from this round to the log file."""
        for event in world.event_log:
            if event.round_num == world.round_num:
                record = {
                    "game_id": self.game_id,
                    "round": event.round_num,
                    "timestamp": event.timestamp,
                    "event_type": event.event_type,
                    "agent": event.agent,
                    **event.content,
                }
                self._fh.write(json.dumps(record) + "\n")
        self._fh.flush()

    def log_game_end(self, final_stats: dict):
        """Write final game summary."""
        record = {
            "game_id": self.game_id,
            "event_type": "GAME_END",
            "timestamp": time.time(),
            **final_stats,
        }
        self._fh.write(json.dumps(record, default=str) + "\n")
        self._fh.flush()

    def close(self):
        self._fh.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def load_game_log(log_path: str) -> list[dict]:
    """Load a JSONL game log into a list of events."""
    events = []
    with open(log_path) as f:
        for line in f:
            line = line.strip()
            if line:
                events.append(json.loads(line))
    return events
