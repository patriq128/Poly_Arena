"""
debate_manager.py — Orchestrates the 3-round structured debate

Round structure:
  1. Independent — each agent gives initial opinion without seeing others
  2. Reactive    — each agent sees all Round-1 outputs, updates + critiques
  3. Final       — each agent sees Round-2 outputs, locks in final position

The manager:
  - Calls the Groq API for each agent each round
  - Parses structured JSON output
  - Populates agent memory after each round
  - Optionally pauses for human intervention between rounds
  - Returns full debate log for the Decision Engine
"""

from __future__ import annotations

import json
import re
import sys
import time
import textwrap
import threading
from typing import Optional

from colorama import Fore, Style
from groq import Groq

from agents import Agent, AgentResponse, build_agents


# ── Groq model fallback list ──────────────────────────────────────────────────
MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-70b-versatile",
    "mixtral-8x7b-32768",
    "llama3-70b-8192",
]

W = 82  # terminal width


# ── terminal helpers (local copy so debate_manager is self-contained) ─────────
def _hr(char="─", color=Fore.CYAN):
    print(color + char * W + Style.RESET_ALL)

def _cp(text, color=Fore.WHITE, end="\n"):
    print(color + text + Style.RESET_ALL, end=end)

def _spin(msg: str):
    stop = threading.Event()
    fr   = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
    def _run():
        i = 0
        while not stop.is_set():
            sys.stdout.write(f"\r{Fore.CYAN}{fr[i%10]} {msg}{Style.RESET_ALL}   ")
            sys.stdout.flush(); time.sleep(0.08); i += 1
        sys.stdout.write("\r" + " "*(len(msg)+12) + "\r")
        sys.stdout.flush()
    threading.Thread(target=_run, daemon=True).start()
    return stop

def _unspin(s): s.set(); time.sleep(0.12)


# ── Groq API call with model fallback ─────────────────────────────────────────
def _groq_call(client: Groq, system: str, user: str,
               history: Optional[list] = None) -> tuple[str, str]:
    """Returns (response_text, model_used). Falls back across MODELS."""
    messages = [{"role": "system", "content": system}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user})

    for model in MODELS:
        try:
            r = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=600,
                temperature=0.82,
            )
            return r.choices[0].message.content.strip(), model
        except Exception as e:
            if "rate" in str(e).lower() or "429" in str(e):
                time.sleep(2.5)
            continue
    return '{"vote":"NO","confidence":0.5,"reasoning":"API error.","critique":"N/A"}', MODELS[-1]


# ── parse raw LLM output into AgentResponse ───────────────────────────────────
def _parse_response(raw: str, agent: Agent) -> AgentResponse:
    """
    Robustly extract JSON from LLM output.
    Falls back gracefully if parsing fails, using agent bias as prior.
    """
    # strip markdown code fences
    cleaned = re.sub(r"```[a-z]*", "", raw).strip().strip("`").strip()

    # find the first {...} block
    m = re.search(r"\{.*?\}", cleaned, re.DOTALL)
    if m:
        cleaned = m.group(0)

    try:
        data = json.loads(cleaned)
        return AgentResponse.from_dict(data)
    except (json.JSONDecodeError, KeyError):
        # graceful fallback: use bias as prior
        fallback_vote = "YES" if agent.bias >= 0.5 else "NO"
        fallback_conf = agent.bias if agent.bias >= 0.5 else (1.0 - agent.bias)
        return AgentResponse(
            vote=fallback_vote,
            confidence=round(fallback_conf, 2),
            reasoning="Parse error — defaulting to bias prior.",
            critique="Could not parse response to issue critique.",
        )


# ── print a single agent's response to terminal ───────────────────────────────
def _print_response(agent: Agent, response: AgentResponse, round_num: int):
    vc   = Fore.GREEN if response.vote == "YES" else Fore.RED
    conf = response.confidence
    bar  = "█" * int(conf * 10) + "░" * (10 - int(conf * 10))

    print(
        f"  {agent.color}{agent.name:<10}{Style.RESET_ALL} "
        f"[{vc}{response.vote:>3}{Style.RESET_ALL}] "
        f"conf={conf:.2f} [{Fore.CYAN}{bar}{Style.RESET_ALL}]"
    )
    # reasoning
    r_lines = textwrap.wrap(f"  ↳ {response.reasoning}", width=W-4)
    for l in r_lines:
        _cp(l, Fore.WHITE)
    # critique (dimmer)
    c_lines = textwrap.wrap(f"  ✦ {response.critique}", width=W-4)
    for l in c_lines:
        _cp(l, Fore.LIGHTBLACK_EX)
    print()


# ── DebateManager ─────────────────────────────────────────────────────────────
class DebateManager:
    """
    Orchestrates a full 3-round structured debate across all agents.

    Usage:
        manager = DebateManager(client, agents, market, allow_human=True)
        log = manager.run()
    """

    def __init__(
        self,
        client:       Groq,
        agents:       list[Agent],
        market:       dict,
        allow_human:  bool = False,
    ):
        self.client      = client
        self.agents      = agents
        self.market      = market
        self.allow_human = allow_human
        self.log:        list[dict] = []   # full structured debate log
        self.model_used  = MODELS[0]
        self.chart_data: list[dict] = []

        # running vote tallies
        self._votes = {"YES": 0, "NO": 0}

    # ── main entry point ──────────────────────────────────────────────────────
    def run(self) -> list[dict]:
        """Run all 3 rounds and return the full debate log."""
        q   = self.market["question"]
        yp  = self.market["yes_price"]

        _cp(f"\n  🔴  DEBATE OPENED", Fore.RED + Style.BRIGHT)
        _cp(f"  {q}", Fore.WHITE + Style.BRIGHT)
        _cp(
            f"  Market  YES {yp*100:.1f}%  ·  NO {(1-yp)*100:.1f}%  "
            f"·  Vol ${self.market.get('volume', 0):,.0f}",
            Fore.CYAN,
        )
        _hr()

        # reset all agent memory for this debate
        for ag in self.agents:
            ag.reset_debate()

        # seed chart with market price
        self.chart_data = [{
            "step":      "Start",
            "yes_pct":   0,
            "no_pct":    0,
            "consensus": round(yp * 100, 1),
            "avg_conf":  0.5,
        }]

        for round_num in range(1, 4):
            self._run_round(round_num)

            # optional human intervention between rounds
            if self.allow_human and round_num < 3:
                self._human_intervention(round_num)

        return self.log

    # ── single round ──────────────────────────────────────────────────────────
    def _run_round(self, round_num: int):
        _hr("·", Fore.CYAN)
        round_labels = {1: "INDEPENDENT OPINIONS", 2: "REACTIVE DEBATE", 3: "FINAL POSITIONS"}
        _cp(
            f"  ── ROUND {round_num}/3 · {round_labels[round_num]}  [{self.model_used}] ──",
            Fore.CYAN + Style.BRIGHT,
        )
        _hr("·", Fore.CYAN)

        round_responses: list[dict] = []
        confidences: list[float]   = []

        for agent in self.agents:
            system = agent.system_prompt(
                self.market["question"],
                self.market["yes_price"],
                round_num,
            )
            user = agent.user_prompt(round_num)

            s = _spin(f"{agent.name} thinking (round {round_num})...")
            raw, self.model_used = _groq_call(self.client, system, user)
            _unspin(s)

            response = _parse_response(raw, agent)

            # apply bias resistance to confidence:
            # agents with strong bias require higher opposing confidence to update
            if len(agent.own_history) > 0:
                prev_vote = agent.own_history[-1]["response"]["vote"]
                if response.vote != prev_vote:
                    # penalise confidence flip relative to bias strength
                    resistance = abs(agent.bias - 0.5) * 0.4
                    response.confidence = max(0.1, response.confidence - resistance)

            # record into agent memory
            agent.record(round_num, response)

            entry = {
                "round":    round_num,
                "agent":    agent.name,
                "response": response.to_dict(),
                "weight":   agent.weight,
            }
            self.log.append(entry)
            round_responses.append(entry)
            confidences.append(response.confidence)

            # update running vote tally
            if response.vote == "YES":
                self._votes["YES"] += 1
            else:
                self._votes["NO"] += 1

            _print_response(agent, response, round_num)

        # after round: broadcast this round's outputs to ALL agents
        for entry in round_responses:
            for agent in self.agents:
                agent.add_to_context(entry)

        # update chart data
        total = self._votes["YES"] + self._votes["NO"]
        yes_pct = round(self._votes["YES"] / total * 100, 1) if total else 0
        avg_conf = round(sum(confidences) / len(confidences), 3) if confidences else 0.5
        consensus = round(
            self.market["yes_price"] * 0.6 + (self._votes["YES"] / max(total, 1)) * 0.4,
            4,
        ) * 100

        self.chart_data.append({
            "step":      f"R{round_num}-end",
            "yes_pct":   yes_pct,
            "no_pct":    round(100 - yes_pct, 1),
            "consensus": round(consensus, 1),
            "avg_conf":  avg_conf,
        })

        # per-step entries for the detailed confidence chart
        for i, (entry, conf) in enumerate(zip(round_responses, confidences)):
            ag_name = entry["agent"].split("-")[0]
            self.chart_data.append({
                "step":      f"R{round_num}·{ag_name}",
                "yes_pct":   round(self._votes["YES"] / max(self._votes["YES"]+self._votes["NO"],1)*100,1),
                "no_pct":    round(self._votes["NO"]  / max(self._votes["YES"]+self._votes["NO"],1)*100,1),
                "consensus": round(consensus, 1),
                "avg_conf":  conf,
                "agent":     entry["agent"],
                "vote":      entry["response"]["vote"],
            })

    # ── human intervention window ─────────────────────────────────────────────
    def _human_intervention(self, after_round: int):
        _hr("═", Fore.YELLOW)
        _cp(f"  👤  HUMAN INTERVENTION — after Round {after_round}", Fore.YELLOW + Style.BRIGHT)
        _cp("  You can inject a statement into the debate.", Fore.WHITE)
        _cp("  This will be added to all agents' context before the next round.", Fore.WHITE)
        _cp("  Press Enter to skip.", Fore.LIGHTBLACK_EX)
        _hr("═", Fore.YELLOW)

        msg = input(f"{Fore.YELLOW}  Your input: {Style.RESET_ALL}").strip()
        if not msg:
            return

        # inject as a special context entry attributed to HUMAN
        human_entry = {
            "round":  after_round,
            "agent":  "HUMAN",
            "response": {
                "vote":       "N/A",
                "confidence": 1.0,
                "reasoning":  msg,
                "critique":   "(human intervention)",
            },
            "weight": 1.0,
        }
        for agent in self.agents:
            agent.add_to_context(human_entry)

        _cp(f"  ✓ Your input has been added to all agents' context.", Fore.GREEN)
        time.sleep(0.8)
