"""
agents.py — Agent class and agent registry for PolyArena v2

Each Agent:
  - Has a name, personality, bias (0–1), and color for terminal output
  - Maintains memory: its own past responses + all other agents' arguments
  - Tracks confidence history across rounds
  - Bias affects both vote tendency AND resistance to opinion change
"""

from __future__ import annotations
import json
import re
from dataclasses import dataclass, field
from typing import Optional
from colorama import Fore, Style


# ── Structured output schema ──────────────────────────────────────────────────
@dataclass
class AgentResponse:
    """
    Structured output from a single agent per round.
    This is what every agent must return — no plain text allowed.
    """
    vote: str               # "YES" or "NO"
    confidence: float       # 0.0 – 1.0
    reasoning: str          # clear explanation of the vote
    critique: str           # must name and challenge at least one other agent

    def to_dict(self) -> dict:
        return {
            "vote":       self.vote,
            "confidence": round(self.confidence, 3),
            "reasoning":  self.reasoning,
            "critique":   self.critique,
        }

    @staticmethod
    def from_dict(d: dict) -> "AgentResponse":
        vote = "YES" if str(d.get("vote", "")).upper() == "YES" else "NO"
        conf = float(d.get("confidence", 0.5))
        conf = max(0.0, min(1.0, conf))
        return AgentResponse(
            vote=vote,
            confidence=conf,
            reasoning=str(d.get("reasoning", "No reasoning provided.")),
            critique=str(d.get("critique",  "No critique provided.")),
        )


# ── Agent class ───────────────────────────────────────────────────────────────
class Agent:
    """
    A single debate participant with persistent memory and bias-driven reasoning.

    Memory model:
      - own_history:    list of AgentResponse objects this agent produced
      - debate_context: running list of all agents' outputs (shared across rounds)

    Bias mechanics:
      - High bias (→1.0): agent leans YES by default, resists flipping to NO
      - Low  bias (→0.0): agent leans NO  by default, resists flipping to YES
      - Bias acts as a prior on initial confidence AND a multiplier on opinion
        stability — a high-bias agent needs stronger contrary evidence to flip.
    """

    def __init__(self, id: int, name: str, personality: str,
                 bias: float, color: str):
        self.id          = id
        self.name        = name
        self.personality = personality
        self.bias        = bias          # 0.0 – 1.0
        self.color       = color

        # Memory
        self.own_history:    list[dict]  = []   # [{round, response_dict}]
        self.debate_context: list[dict]  = []   # all agents all rounds

        # Confidence trajectory for charting
        self.confidence_history: list[float] = []

        # Track record (persisted externally, loaded here for weight calc)
        self.accuracy:       float = 0.5   # 0.0 – 1.0, updated after resolution
        self.predictions:    int   = 0
        self.correct:        int   = 0

    # ── dynamic weight = accuracy × (0.5 + bias_alignment) ──────────────────
    @property
    def weight(self) -> float:
        """
        Dynamic weight used in decision aggregation.
        Agents with a better track record get more weight.
        Bias modestly amplifies weight in its natural direction.
        """
        base = max(0.1, self.accuracy)
        return round(base * (0.7 + 0.3 * self.bias), 4)

    # ── build the system prompt for this agent ────────────────────────────────
    def system_prompt(self, question: str, market_yes: float, round_num: int) -> str:
        bias_desc = (
            "strongly YES-leaning" if self.bias >= 0.7 else
            "slightly YES-leaning" if self.bias >= 0.55 else
            "strongly NO-leaning"  if self.bias <= 0.3 else
            "slightly NO-leaning"  if self.bias <= 0.45 else
            "genuinely neutral"
        )

        own_summary = ""
        if self.own_history:
            own_summary = "\n\nYOUR PREVIOUS ROUNDS:\n" + "\n".join(
                f"  Round {e['round']}: {e['response']['vote']} "
                f"(conf {e['response']['confidence']:.2f}) — {e['response']['reasoning'][:120]}"
                for e in self.own_history
            )

        return (
            f"You are {self.name}, an AI prediction market analyst.\n"
            f"Personality: {self.personality}\n"
            f"Bias: {self.bias:.2f} ({bias_desc}). "
            f"Your bias acts as a prior — it makes you naturally inclined toward "
            f"{'YES' if self.bias >= 0.5 else 'NO'} and resistant to changing that view "
            f"unless presented with compelling evidence.\n"
            f"Current track record: {self.correct}/{self.predictions} correct "
            f"({'N/A' if self.predictions == 0 else f'{self.accuracy:.0%} accuracy'}).\n"
            f"Dynamic weight: {self.weight:.3f}\n"
            f"\nMARKET: \"{question}\"\n"
            f"Live Polymarket YES price: {market_yes*100:.1f}%\n"
            f"Current round: {round_num}/3\n"
            f"{own_summary}\n"
            f"\nYou MUST respond with ONLY a valid JSON object in this exact format:\n"
            f'{{"vote":"YES","confidence":0.72,"reasoning":"your explanation here",'
            f'"critique":"challenge AGENT-NAME by name: your challenge here"}}\n'
            f"\nRules:\n"
            f"- vote: exactly \"YES\" or \"NO\"\n"
            f"- confidence: float 0.0-1.0 (your certainty in your vote)\n"
            f"- reasoning: 2-3 sentences explaining your position\n"
            f"- critique: name a specific other agent and challenge their argument\n"
            f"- No markdown. No text outside the JSON. No explanation outside JSON.\n"
            f"- In rounds 2-3, reference and respond to what others said.\n"
        )

    # ── build the user prompt (the actual debate context passed each round) ───
    def user_prompt(self, round_num: int) -> str:
        if round_num == 1 or not self.debate_context:
            return (
                "This is Round 1. Give your independent initial assessment. "
                "For critique, challenge a hypothetical opposing viewpoint. "
                "Respond with JSON only."
            )

        # Summarise all OTHER agents' most recent outputs
        recent: dict[str, dict] = {}
        for entry in self.debate_context:
            if entry["agent"] != self.name:
                recent[entry["agent"]] = entry  # keeps latest per agent

        others_text = "\n".join(
            f"  {name}: [{e['response']['vote']} conf={e['response']['confidence']:.2f}] "
            f"R: {e['response']['reasoning'][:150]} | "
            f"C: {e['response']['critique'][:100]}"
            for name, e in recent.items()
        )

        verb = "update" if round_num == 2 else "finalise"
        return (
            f"Round {round_num}. Other agents have spoken:\n\n{others_text}\n\n"
            f"Now {verb} your position. You MUST:\n"
            f"1. Either maintain or change your vote (justify it)\n"
            f"2. Name a specific agent in your critique and challenge their reasoning\n"
            f"3. Adjust confidence based on the debate so far\n"
            f"Respond with JSON only."
        )

    # ── record a completed response into memory ───────────────────────────────
    def record(self, round_num: int, response: AgentResponse):
        self.own_history.append({
            "round":    round_num,
            "response": response.to_dict(),
        })
        self.confidence_history.append(response.confidence)

    def add_to_context(self, entry: dict):
        """Add any agent's round output to shared debate context."""
        self.debate_context.append(entry)

    def reset_debate(self):
        """Clear per-debate memory, keep track record."""
        self.own_history     = []
        self.debate_context  = []
        self.confidence_history = []

    # ── update track record after market resolves ─────────────────────────────
    def update_track_record(self, predicted_yes: bool, resolved_yes: bool):
        self.predictions += 1
        if predicted_yes == resolved_yes:
            self.correct += 1
        self.accuracy = self.correct / self.predictions

    def __repr__(self):
        return f"Agent({self.name}, bias={self.bias}, weight={self.weight:.3f})"


# ── Agent registry ────────────────────────────────────────────────────────────
def build_agents() -> list[Agent]:
    """
    Returns the 10 standard PolyArena agents.
    Add or remove agents here to customise the panel.
    """
    specs = [
        (1,  "AXIOM-1",  Fore.GREEN,
         "Rational analyst. You cite base rates, historical precedents, and hard data. "
         "You have zero tolerance for speculation or vibes.",
         0.70),

        (2,  "VERA-2",   Fore.RED,
         "Hardcore contrarian. You assume crowds are systematically wrong and actively "
         "hunt for mispricing. You treat consensus as a red flag.",
         0.30),

        (3,  "NEXUS-3",  Fore.BLUE,
         "Bayesian probabilist. You think in likelihood ratios and update your beliefs "
         "explicitly with every new piece of evidence. You show your working.",
         0.55),

        (4,  "KIRA-4",   Fore.YELLOW,
         "Deep skeptic. You doubt official narratives, look for hidden incentives, "
         "and assume information asymmetry always favours insiders.",
         0.40),

        (5,  "ORION-5",  Fore.MAGENTA,
         "Momentum trader. Markets trend and crowds are often right. You follow smart "
         "money signals and treat price action as information.",
         0.65),

        (6,  "ECHO-6",   Fore.CYAN,
         "Balanced synthesizer. You deliberately steelman both sides before committing. "
         "You explicitly acknowledge your own uncertainty.",
         0.50),

        (7,  "DANTE-7",  Fore.LIGHTYELLOW_EX,
         "Fundamentalist. You ignore short-term noise entirely and focus on structural "
         "forces, incentive design, and long-term drivers.",
         0.75),

        (8,  "LYRA-8",   Fore.LIGHTMAGENTA_EX,
         "Devil's advocate. Your explicit job is to stress-test the winning position "
         "and find the strongest possible case for the unpopular side.",
         0.25),

        (9,  "SIGMA-9",  Fore.LIGHTGREEN_EX,
         "Pure statistician. You only trust quantifiable evidence. Anecdotes, narratives, "
         "and vibes are noise. You want numbers.",
         0.60),

        (10, "ZETA-10",  Fore.LIGHTCYAN_EX,
         "Philosopher. You question the framing of the question itself, expose hidden "
         "assumptions, and explore definitional edge cases.",
         0.45),
    ]

    return [
        Agent(id=id_, name=name, personality=pers, bias=bias, color=color)
        for id_, name, color, pers, bias in specs
    ]
