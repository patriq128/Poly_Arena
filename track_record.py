"""
track_record.py — Persistent agent performance tracking

Stores past predictions per agent, compares against resolved outcomes,
and dynamically adjusts agent weights (accuracy scores) over time.

Storage format: polyarena_saves/track_record.json
{
  "AXIOM-1": {
    "predictions": 12,
    "correct":      8,
    "accuracy":  0.667,
    "history": [
      {
        "question":     "Will BTC hit $100k?",
        "market_id":    "abc123",
        "predicted":    "YES",
        "confidence":   0.72,
        "resolved":     "YES",    // null if unresolved
        "correct":      true,
        "timestamp":    "2026-01-15T10:30:00"
      },
      ...
    ]
  },
  ...
}
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from colorama import Fore, Style

from agents import Agent

TRACK_FILE = Path("polyarena_saves") / "track_record.json"


# ── TrackRecord ───────────────────────────────────────────────────────────────
class TrackRecord:
    """
    Loads, updates, and saves agent prediction history.

    Typical workflow:
      1. After a debate: record_predictions(agents, result, market)
      2. When a market resolves: resolve_market(market_id, outcome)
      3. Agents' weights (accuracy) are recalculated automatically
    """

    def __init__(self):
        self.data: dict = self._load()

    # ── persistence ───────────────────────────────────────────────────────────
    def _load(self) -> dict:
        if TRACK_FILE.exists():
            try:
                return json.loads(TRACK_FILE.read_text())
            except Exception:
                pass
        return {}

    def save(self):
        TRACK_FILE.parent.mkdir(exist_ok=True)
        TRACK_FILE.write_text(json.dumps(self.data, indent=2))

    # ── record new predictions (call right after a debate) ────────────────────
    def record_predictions(
        self,
        agents:    list[Agent],
        result:    dict,          # DebateResult.to_dict()
        market:    dict,
    ):
        """
        Log each agent's final vote as a prediction for this market.
        Outcome is initially null (unresolved).
        """
        market_id = market.get("id", "unknown")
        question  = market.get("question", "")
        ts        = datetime.now().isoformat()

        for agent in agents:
            name   = agent.name
            fv     = result["agent_final_votes"].get(name, {})
            vote   = fv.get("vote",       "NO")
            conf   = fv.get("confidence", 0.5)

            if name not in self.data:
                self.data[name] = {
                    "predictions": 0,
                    "correct":     0,
                    "accuracy":    0.5,
                    "history":     [],
                }

            self.data[name]["history"].append({
                "question":   question,
                "market_id":  market_id,
                "predicted":  vote,
                "confidence": conf,
                "resolved":   None,    # filled in when market resolves
                "correct":    None,
                "timestamp":  ts,
            })
            self.data[name]["predictions"] = len(self.data[name]["history"])

        self.save()
        print(
            f"{Fore.GREEN}  ✓ Track record updated for {len(agents)} agents.{Style.RESET_ALL}"
        )

    # ── resolve a market and update accuracy ──────────────────────────────────
    def resolve_market(self, market_id: str, outcome: str) -> int:
        """
        Mark all unresolved predictions for market_id as correct/incorrect.
        outcome: "YES" or "NO"
        Returns number of agents updated.
        """
        outcome = outcome.upper()
        updated = 0

        for name, agent_data in self.data.items():
            for entry in agent_data["history"]:
                if entry["market_id"] == market_id and entry["resolved"] is None:
                    entry["resolved"] = outcome
                    entry["correct"]  = (entry["predicted"] == outcome)
                    updated += 1

            # recompute accuracy from history
            resolved = [e for e in agent_data["history"] if e["resolved"] is not None]
            if resolved:
                correct   = sum(1 for e in resolved if e["correct"])
                agent_data["predictions"] = len(resolved)
                agent_data["correct"]     = correct
                agent_data["accuracy"]    = round(correct / len(resolved), 4)

        self.save()
        return updated

    # ── push accuracy back into live Agent objects ─────────────────────────────
    def apply_to_agents(self, agents: list[Agent]):
        """Update each Agent's .accuracy, .predictions, .correct from stored data."""
        for agent in agents:
            d = self.data.get(agent.name)
            if d:
                agent.accuracy    = d.get("accuracy",    0.5)
                agent.predictions = d.get("predictions", 0)
                agent.correct     = d.get("correct",     0)

    # ── leaderboard ───────────────────────────────────────────────────────────
    def leaderboard(self) -> list[tuple[str, float, int, int]]:
        """Returns [(name, accuracy, correct, total)] sorted by accuracy desc."""
        rows = []
        for name, d in self.data.items():
            total = d.get("predictions", 0)
            if total > 0:
                rows.append((name, d["accuracy"], d["correct"], total))
        return sorted(rows, key=lambda x: x[1], reverse=True)

    # ── print leaderboard to terminal ─────────────────────────────────────────
    def print_leaderboard(self):
        board = self.leaderboard()
        print(f"\n{Fore.CYAN}  ── AGENT LEADERBOARD ──────────────────────────────{Style.RESET_ALL}")
        if not board:
            print(f"{Fore.YELLOW}  No resolved predictions yet.{Style.RESET_ALL}")
            return

        print(f"  {'Agent':<12}  {'Accuracy':>8}  {'Correct':>7}  {'Total':>5}  {'Bar'}")
        print(f"  {'─'*12}  {'─'*8}  {'─'*7}  {'─'*5}  {'─'*20}")
        for name, acc, correct, total in board:
            bar   = "█" * int(acc * 20) + "░" * (20 - int(acc * 20))
            color = Fore.GREEN if acc >= 0.6 else (Fore.YELLOW if acc >= 0.4 else Fore.RED)
            print(
                f"  {color}{name:<12}{Style.RESET_ALL}  "
                f"{acc:>7.1%}  {correct:>7}  {total:>5}  {color}{bar}{Style.RESET_ALL}"
            )
        print()

    # ── pending resolutions ───────────────────────────────────────────────────
    def pending_resolutions(self) -> list[dict]:
        """Return list of unique markets that have unresolved predictions."""
        seen = set()
        pending = []
        for name, d in self.data.items():
            for e in d["history"]:
                if e["resolved"] is None and e["market_id"] not in seen:
                    seen.add(e["market_id"])
                    pending.append({
                        "market_id": e["market_id"],
                        "question":  e["question"],
                        "timestamp": e["timestamp"],
                    })
        return pending
