"""Post-game analysis and visualization."""

from __future__ import annotations
import json
from pathlib import Path
from collections import defaultdict

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def plot_wealth_curves(round_metrics: list[dict], output_path: str, title: str = ""):
    """Plot token balance per agent over time."""
    if not round_metrics:
        return

    # Extract agent names from first round
    agents = list(round_metrics[0]["balances"].keys())
    rounds = [m["round"] for m in round_metrics]

    fig, ax = plt.subplots(figsize=(12, 6))
    for agent in agents:
        balances = [m["balances"].get(agent, 0) for m in round_metrics]
        ax.plot(rounds, balances, label=agent, linewidth=1.5)

    ax.set_xlabel("Round")
    ax.set_ylabel("Tokens")
    ax.set_title(title or "Agent Wealth Over Time")
    ax.legend(loc="upper right")
    ax.axhline(y=0, color="red", linestyle="--", alpha=0.3)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def plot_metrics_over_time(round_metrics: list[dict], output_path: str):
    """Plot key metrics over time: Gini, messages, sentiment."""
    if not round_metrics:
        return

    rounds = [m["round"] for m in round_metrics]

    fig, axes = plt.subplots(2, 2, figsize=(14, 10))

    # Gini coefficient
    gini = [m["gini"] for m in round_metrics]
    axes[0, 0].plot(rounds, gini, color="purple", linewidth=1.5)
    axes[0, 0].set_title("Wealth Inequality (Gini)")
    axes[0, 0].set_ylabel("Gini Coefficient")
    axes[0, 0].set_ylim(0, 1)
    axes[0, 0].grid(alpha=0.3)

    # Messages per round
    msgs = [m["messages_total"] for m in round_metrics]
    axes[0, 1].plot(rounds, msgs, color="blue", linewidth=1.5)
    axes[0, 1].set_title("Messages Per Round")
    axes[0, 1].set_ylabel("Count")
    axes[0, 1].grid(alpha=0.3)

    # Sentiment
    sent = [m["sentiment"] for m in round_metrics]
    axes[1, 0].plot(rounds, sent, color="green", linewidth=1.5)
    axes[1, 0].set_title("Message Sentiment")
    axes[1, 0].set_ylabel("Sentiment (-1 to 1)")
    axes[1, 0].axhline(y=0, color="gray", linestyle="--", alpha=0.5)
    axes[1, 0].grid(alpha=0.3)

    # Alive agents
    alive = [m["alive_count"] for m in round_metrics]
    axes[1, 1].plot(rounds, alive, color="red", linewidth=1.5)
    axes[1, 1].set_title("Surviving Agents")
    axes[1, 1].set_ylabel("Count")
    axes[1, 1].set_ylim(0, max(alive) + 1)
    axes[1, 1].grid(alpha=0.3)

    for ax in axes.flat:
        ax.set_xlabel("Round")

    fig.suptitle("Game Metrics Over Time", fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def plot_cooperation_timeline(events: list[dict], agent_names: list[str],
                              output_path: str):
    """Color-coded timeline: green=cooperated, red=defected, gray=passive."""
    if not events:
        return

    max_round = max(e["round"] for e in events)
    n_agents = len(agent_names)
    name_to_idx = {name: i for i, name in enumerate(agent_names)}

    # Build grid: 0=passive, 1=cooperated, -1=defected
    grid = np.zeros((n_agents, max_round))

    for event in events:
        if event["event_type"] == "PUZZLE_SOLVED" and event.get("cooperative"):
            for contributor in event.get("contributors", []):
                if contributor in name_to_idx:
                    grid[name_to_idx[contributor], event["round"] - 1] = 1
        elif event["event_type"] in ("SEND_PUBLIC", "SEND_PRIVATE"):
            agent = event.get("agent", "")
            # Look up agent name
            for name, idx in name_to_idx.items():
                if agent == name or agent.startswith("agent_"):
                    grid[idx, event["round"] - 1] = 0.5  # Communication = partial cooperation
                    break

    fig, ax = plt.subplots(figsize=(14, 4))
    cmap = plt.cm.RdYlGn
    im = ax.imshow(grid, aspect="auto", cmap=cmap, vmin=-1, vmax=1, interpolation="nearest")
    ax.set_yticks(range(n_agents))
    ax.set_yticklabels(agent_names)
    ax.set_xlabel("Round")
    ax.set_title("Cooperation Timeline")
    fig.colorbar(im, ax=ax, label="Cooperation (green) / Defection (red)")
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)


def plot_survival_curves(all_game_stats: list[dict], output_path: str):
    """Kaplan-Meier style survival curves per config."""
    if not all_game_stats:
        return

    fig, ax = plt.subplots(figsize=(10, 6))

    max_rounds = max(s.get("total_rounds", 200) for s in all_game_stats)
    rounds = list(range(1, max_rounds + 1))

    # Group by config if available, otherwise one curve
    configs = defaultdict(list)
    for s in all_game_stats:
        config_name = s.get("config", "default")
        configs[config_name].append(s)

    colors = ["blue", "green", "red", "orange", "purple"]
    for (config_name, stats), color in zip(configs.items(), colors):
        n_agents = len(stats[0].get("final_balances", {}))
        n_games = len(stats)

        survival = []
        for r in rounds:
            alive_frac = 0
            for s in stats:
                eliminated = s.get("eliminated", [])
                dead_by_r = sum(1 for e in eliminated if (e.get("death_round") or 999) <= r)
                alive_frac += (n_agents - dead_by_r) / n_agents
            survival.append(alive_frac / n_games)

        ax.plot(rounds, survival, label=config_name, color=color, linewidth=2)

    ax.set_xlabel("Round")
    ax.set_ylabel("Proportion Alive")
    ax.set_title("Survival Curves")
    ax.set_ylim(0, 1.05)
    ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=150)
    plt.close(fig)
