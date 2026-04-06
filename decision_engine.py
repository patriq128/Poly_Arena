"""
decision_engine.py — Final decision aggregation + Meta-Agent Judge

The Decision Engine:
  1. Aggregates all agent outputs using confidence × weight
  2. Computes disagreement score (variance of YES confidence"""
decision_engine.py — Final decision aggregation + Meta-Agent Judge

The Decision Engine:
  1. Aggregates all agent outputs using confidence × weight
  2. Computes disagreement score (variance of YES confidence values)
  3. Extracts key arguments from all 3 rounds
  4. Calls the Meta-Agent Judge for an independent verdict

The Meta-Agent Judge:
  - Reviews ALL reasoning from ALL rounds
  - Identifies strongest and weakest arguments
  - Produces a final verdict with full explanation
  - Does NOT simply follow the majority — it can override
"""

from __future__ import annotations

import json
import re
import time
import textwrap
from dataclasses import dataclass

import numpy as np
from colorama import Fore, Style
from groq import Groq

from agents import Agent
from debate_manager import MODELS, W, _groq_call, _hr, _cp, _spin, _unspin


# ── Final decision dataclass ──────────────────────────────────────────────────
@dataclass
class DebateResult:
    """
    Complete output of a finished debate — everything you need for display,
    saving, graphing, and track record updates.
    """
    question:          str
    final_decision:    str          # "YES" or "NO"
    confidence_score:  float        # 0.0 – 1.0
    disagreement_score: float       # 0.0 – 1.0 (high = agents strongly disagreed)

    # weighted vote breakdown
    weighted_yes:      float
    weighted_no:       float
    raw_yes_count:     int
    raw_no_count:      int

    # judge output
    judge_verdict:     str          # "YES" or "NO"
    judge_reasoning:   str
    judge_strongest:   str          # name of agent with strongest argument
    judge_weakest:     str          # name of agent with weakest argument

    # summaries
    key_arguments:     list[str]    # top arguments extracted by the engine
    agent_final_votes: dict         # {agent_name: {"vote":..,"confidence":..}}

    # metadata
    market_yes_price:  float
    model_used:        str

    def to_dict(self) -> dict:
        return self.__dict__

    @property
    def consensus_direction(self) -> str:
        """Whether AI consensus is more bullish/bearish than market."""
        ai_yes = self.confidence_score if self.final_decision == "YES" else 1 - self.confidence_score
        if ai_yes > self.market_yes_price + 0.05:
            return "▲ AI MORE BULLISH THAN MARKET"
        elif ai_yes < self.market_yes_price - 0.05:
            return "▼ AI MORE BEARISH THAN MARKET"
        return "═ AI IN LINE WITH MARKET"


# ── DecisionEngine ────────────────────────────────────────────────────────────
class DecisionEngine:
    """
    Takes the full debate log and agent list, produces a DebateResult.

    Aggregation method:
      For each agent, take their FINAL round response.
      weighted_yes = sum(confidence × weight) for YES voters
      weighted_no  = sum(confidence × weight) for NO  voters
      Winner = argmax(weighted_yes, weighted_no)
      Confidence score = winner_weight / (weighted_yes + weighted_no)

    Disagreement score:
      Variance of YES-normalised confidence values.
      YES voter confidence kept as-is, NO voter confidence negated.
      High variance → agents strongly disagreed.
    """

    def __init__(self, client: Groq, agents: list[Agent], debate_log: list[dict], market: dict):
        self.client     = client
        self.agents     = agents
        self.log        = debate_log
        self.market     = market
        self.agent_map  = {a.name: a for a in agents}

    def compute(self) -> DebateResult:
        """Run full aggregation + judge. Returns DebateResult."""
        _hr()
        _cp("  ⚙️   DECISION ENGINE COMPUTING...", Fore.CYAN + Style.BRIGHT)
        _hr()

        # ── 1. Get each agent's FINAL position (round 3 if available) ─────────
        final_by_agent: dict[str, dict] = {}
        for entry in self.log:
            # later entries overwrite earlier — so we end up with the last round
            final_by_agent[entry["agent"]] = entry

        # ── 2. Weighted aggregation ───────────────────────────────────────────
        weighted_yes = 0.0
        weighted_no  = 0.0
        raw_yes = raw_no = 0
        agent_final_votes: dict[str, dict] = {}
        signed_confidences: list[float] = []   # for disagreement score

        for name, entry in final_by_agent.items():
            ag = self.agent_map.get(name)
            if ag is None:
                continue
            resp = entry["response"]
            vote = resp["vote"]
            conf = float(resp["confidence"])
            wt   = ag.weight

            agent_final_votes[name] = {"vote": vote, "confidence": conf, "weight": wt}

            if vote == "YES":
                weighted_yes += conf * wt
                raw_yes      += 1
                signed_confidences.append(conf)
            else:
                weighted_no  += conf * wt
                raw_no       += 1
                signed_confidences.append(-conf)

        total_w = weighted_yes + weighted_no
        if total_w == 0:
            total_w = 1.0  # guard against division by zero

        final_decision = "YES" if weighted_yes >= weighted_no else "NO"
        confidence_score = round(
            (weighted_yes if final_decision == "YES" else weighted_no) / total_w, 4
        )

        # ── 3. Disagreement score (variance of signed confidences) ────────────
        if len(signed_confidences) >= 2:
            disagreement_score = round(float(np.var(signed_confidences)), 4)
        else:
            disagreement_score = 0.0
        # normalise to 0-1 range (max possible variance ≈ 1.0 when half are +1, half -1)
        disagreement_score = round(min(1.0, disagreement_score * 2), 4)

        _cp(f"  Weighted YES: {weighted_yes:.3f}  |  Weighted NO: {weighted_no:.3f}", Fore.WHITE)
        _cp(f"  Raw votes:    {raw_yes} YES  /  {raw_no} NO", Fore.WHITE)
        _cp(f"  Disagreement score: {disagreement_score:.3f} "
            f"({'HIGH — agents strongly disagreed' if disagreement_score > 0.4 else 'LOW — broad consensus'})",
            Fore.YELLOW if disagreement_score > 0.4 else Fore.GREEN)

        # ── 4. Extract key arguments ──────────────────────────────────────────
        key_arguments = self._extract_key_arguments(final_by_agent)

        # ── 5. Call the Judge ─────────────────────────────────────────────────
        judge_verdict, judge_reasoning, judge_strongest, judge_weakest, model_used = \
            self._run_judge(final_by_agent, final_decision, confidence_score)

        return DebateResult(
            question          = self.market["question"],
            final_decision    = judge_verdict,   # Judge has final say
            confidence_score  = confidence_score,
            disagreement_score= disagreement_score,
            weighted_yes      = round(weighted_yes, 4),
            weighted_no       = round(weighted_no, 4),
            raw_yes_count     = raw_yes,
            raw_no_count      = raw_no,
            judge_verdict     = judge_verdict,
            judge_reasoning   = judge_reasoning,
            judge_strongest   = judge_strongest,
            judge_weakest     = judge_weakest,
            key_arguments     = key_arguments,
            agent_final_votes = agent_final_votes,
            market_yes_price  = self.market["yes_price"],
            model_used        = model_used,
        )

    # ── extract key arguments ─────────────────────────────────────────────────
    def _extract_key_arguments(self, final_by_agent: dict) -> list[str]:
        """Pull the most informative reasoning snippets from all agents."""
        args = []
        for name, entry in final_by_agent.items():
            r = entry["response"]
            args.append(
                f"[{r['vote']} {r['confidence']:.2f}] {name}: {r['reasoning'][:180]}"
            )
        return args

    # ── Meta-Agent Judge ──────────────────────────────────────────────────────
    def _run_judge(
        self,
        final_by_agent: dict,
        panel_decision: str,
        panel_confidence: float,
    ) -> tuple[str, str, str, str, str]:
        """
        The Judge reviews all agents' reasoning and produces an independent verdict.
        Returns (verdict, reasoning, strongest_agent, weakest_agent, model_used).
        """
        _hr("─", Fore.MAGENTA)
        _cp("  ⚖️   META-AGENT JUDGE DELIBERATING...", Fore.MAGENTA + Style.BRIGHT)
        _hr("─", Fore.MAGENTA)

        # build full reasoning summary for the judge
        all_reasoning = "\n".join(
            f"{name} [{r['response']['vote']} conf={r['response']['confidence']:.2f}]:\n"
            f"  Reasoning: {r['response']['reasoning']}\n"
            f"  Critique:  {r['response']['critique']}"
            for name, r in final_by_agent.items()
        )

        agent_names = list(final_by_agent.keys())

        system = (
            "You are JUDGE-PRIME, an impartial meta-agent reviewing a multi-agent "
            "prediction market debate. Your role:\n"
            "1. Read all agents' final reasoning carefully\n"
            "2. Identify the SINGLE strongest argument (regardless of vote direction)\n"
            "3. Identify the SINGLE weakest argument\n"
            "4. Produce your OWN independent verdict — you are NOT obligated to follow "
            "the majority. Override if the minority made a better case.\n"
            "5. Explain your verdict in 3-5 sentences.\n\n"
            "Respond ONLY with valid JSON in this exact format:\n"
            '{"verdict":"YES","reasoning":"your explanation","'
            'strongest_agent":"AGENT-NAME","weakest_agent":"AGENT-NAME"}\n'
            "No markdown. No text outside JSON."
        )

        user = (
            f'Market question: "{self.market["question"]}"\n'
            f"Live market YES price: {self.market['yes_price']*100:.1f}%\n\n"
            f"Panel decision (before your review): {panel_decision} "
            f"(confidence {panel_confidence:.2f})\n\n"
            f"ALL AGENTS' FINAL REASONING:\n{all_reasoning}\n\n"
            f"Available agent names: {', '.join(agent_names)}\n\n"
            "Produce your independent JSON verdict now."
        )

        s = _spin("Judge deliberating...")
        raw, model_used = _groq_call(self.client, system, user)
        _unspin(s)

        # parse judge output
        try:
            cleaned = re.sub(r"```[a-z]*", "", raw).strip().strip("`")
            m = re.search(r"\{.*?\}", cleaned, re.DOTALL)
            if m:
                data = json.loads(m.group(0))
            else:
                data = json.loads(cleaned)

            verdict   = "YES" if str(data.get("verdict","")).upper() == "YES" else "NO"
            reasoning = str(data.get("reasoning", "No reasoning provided."))
            strongest = str(data.get("strongest_agent", agent_names[0]))
            weakest   = str(data.get("weakest_agent",   agent_names[-1]))
        except Exception:
            verdict   = panel_decision  # fall back to panel
            reasoning = "Judge parse error — deferring to panel majority."
            strongest = agent_names[0]
            weakest   = agent_names[-1]

        # print judge output
        vc = Fore.GREEN if verdict == "YES" else Fore.RED
        _cp(f"\n  JUDGE VERDICT: {vc}{verdict}{Style.RESET_ALL}", Fore.WHITE + Style.BRIGHT)
        for line in textwrap.wrap(f"  {reasoning}", W-2):
            _cp(line, Fore.WHITE)
        _cp(f"\n  Strongest argument: {Fore.GREEN}{strongest}{Style.RESET_ALL}", Fore.WHITE)
        _cp(f"  Weakest  argument: {Fore.RED}{weakest}{Style.RESET_ALL}", Fore.WHITE)

        override_note = ""
        if verdict != panel_decision:
            override_note = f" ← OVERRODE PANEL ({panel_decision})"
        _cp(f"\n  Final decision: {vc}{verdict}{Style.RESET_ALL}{Fore.YELLOW}{override_note}{Style.RESET_ALL}",
            Fore.WHITE + Style.BRIGHT)

        return verdict, reasoning, strongest, weakest, model_used values)
  3. Extracts key arguments from all 3 rounds
  4. Calls the Meta-Agent Judge for an independent verdict

The Meta-Agent Judge:
  - Reviews ALL reasoning from ALL rounds
  - Identifies strongest and weakest arguments
  - Produces a final verdict with full explanation
  - Does NOT simply follow the majority — it can override
"""

from __future__ import annotations

import json
import re
import time
import textwrap
from dataclasses import dataclass

import numpy as np
from colorama import Fore, Style
from groq import Groq

from agents import Agent
from debate_manager import MODELS, _groq_call, _hr, _cp, _spin, _unspin


# ── Final decision dataclass ──────────────────────────────────────────────────
@dataclass
class DebateResult:
    """
    Complete output of a finished debate — everything you need for display,
    saving, graphing, and track record updates.
    """
    question:          str
    final_decision:    str          # "YES" or "NO"
    confidence_score:  float        # 0.0 – 1.0
    disagreement_score: float       # 0.0 – 1.0 (high = agents strongly disagreed)

    # weighted vote breakdown
    weighted_yes:      float
    weighted_no:       float
    raw_yes_count:     int
    raw_no_count:      int

    # judge output
    judge_verdict:     str          # "YES" or "NO"
    judge_reasoning:   str
    judge_strongest:   str          # name of agent with strongest argument
    judge_weakest:     str          # name of agent with weakest argument

    # summaries
    key_arguments:     list[str]    # top arguments extracted by the engine
    agent_final_votes: dict         # {agent_name: {"vote":..,"confidence":..}}

    # metadata
    market_yes_price:  float
    model_used:        str

    def to_dict(self) -> dict:
        return self.__dict__

    @property
    def consensus_direction(self) -> str:
        """Whether AI consensus is more bullish/bearish than market."""
        ai_yes = self.confidence_score if self.final_decision == "YES" else 1 - self.confidence_score
        if ai_yes > self.market_yes_price + 0.05:
            return "▲ AI MORE BULLISH THAN MARKET"
        elif ai_yes < self.market_yes_price - 0.05:
            return "▼ AI MORE BEARISH THAN MARKET"
        return "═ AI IN LINE WITH MARKET"


# ── DecisionEngine ────────────────────────────────────────────────────────────
class DecisionEngine:
    """
    Takes the full debate log and agent list, produces a DebateResult.

    Aggregation method:
      For each agent, take their FINAL round response.
      weighted_yes = sum(confidence × weight) for YES voters
      weighted_no  = sum(confidence × weight) for NO  voters
      Winner = argmax(weighted_yes, weighted_no)
      Confidence score = winner_weight / (weighted_yes + weighted_no)

    Disagreement score:
      Variance of YES-normalised confidence values.
      YES voter confidence kept as-is, NO voter confidence negated.
      High variance → agents strongly disagreed.
    """

    def __init__(self, client: Groq, agents: list[Agent], debate_log: list[dict], market: dict):
        self.client     = client
        self.agents     = agents
        self.log        = debate_log
        self.market     = market
        self.agent_map  = {a.name: a for a in agents}

    def compute(self) -> DebateResult:
        """Run full aggregation + judge. Returns DebateResult."""
        _hr()
        _cp("  ⚙️   DECISION ENGINE COMPUTING...", Fore.CYAN + Style.BRIGHT)
        _hr()

        # ── 1. Get each agent's FINAL position (round 3 if available) ─────────
        final_by_agent: dict[str, dict] = {}
        for entry in self.log:
            # later entries overwrite earlier — so we end up with the last round
            final_by_agent[entry["agent"]] = entry

        # ── 2. Weighted aggregation ───────────────────────────────────────────
        weighted_yes = 0.0
        weighted_no  = 0.0
        raw_yes = raw_no = 0
        agent_final_votes: dict[str, dict] = {}
        signed_confidences: list[float] = []   # for disagreement score

        for name, entry in final_by_agent.items():
            ag = self.agent_map.get(name)
            if ag is None:
                continue
            resp = entry["response"]
            vote = resp["vote"]
            conf = float(resp["confidence"])
            wt   = ag.weight

            agent_final_votes[name] = {"vote": vote, "confidence": conf, "weight": wt}

            if vote == "YES":
                weighted_yes += conf * wt
                raw_yes      += 1
                signed_confidences.append(conf)
            else:
                weighted_no  += conf * wt
                raw_no       += 1
                signed_confidences.append(-conf)

        total_w = weighted_yes + weighted_no
        if total_w == 0:
            total_w = 1.0  # guard against division by zero

        final_decision = "YES" if weighted_yes >= weighted_no else "NO"
        confidence_score = round(
            (weighted_yes if final_decision == "YES" else weighted_no) / total_w, 4
        )

        # ── 3. Disagreement score (variance of signed confidences) ────────────
        if len(signed_confidences) >= 2:
            disagreement_score = round(float(np.var(signed_confidences)), 4)
        else:
            disagreement_score = 0.0
        # normalise to 0-1 range (max possible variance ≈ 1.0 when half are +1, half -1)
        disagreement_score = round(min(1.0, disagreement_score * 2), 4)

        _cp(f"  Weighted YES: {weighted_yes:.3f}  |  Weighted NO: {weighted_no:.3f}", Fore.WHITE)
        _cp(f"  Raw votes:    {raw_yes} YES  /  {raw_no} NO", Fore.WHITE)
        _cp(f"  Disagreement score: {disagreement_score:.3f} "
            f"({'HIGH — agents strongly disagreed' if disagreement_score > 0.4 else 'LOW — broad consensus'})",
            Fore.YELLOW if disagreement_score > 0.4 else Fore.GREEN)

        # ── 4. Extract key arguments ──────────────────────────────────────────
        key_arguments = self._extract_key_arguments(final_by_agent)

        # ── 5. Call the Judge ─────────────────────────────────────────────────
        judge_verdict, judge_reasoning, judge_strongest, judge_weakest, model_used = \
            self._run_judge(final_by_agent, final_decision, confidence_score)

        return DebateResult(
            question          = self.market["question"],
            final_decision    = judge_verdict,   # Judge has final say
            confidence_score  = confidence_score,
            disagreement_score= disagreement_score,
            weighted_yes      = round(weighted_yes, 4),
            weighted_no       = round(weighted_no, 4),
            raw_yes_count     = raw_yes,
            raw_no_count      = raw_no,
            judge_verdict     = judge_verdict,
            judge_reasoning   = judge_reasoning,
            judge_strongest   = judge_strongest,
            judge_weakest     = judge_weakest,
            key_arguments     = key_arguments,
            agent_final_votes = agent_final_votes,
            market_yes_price  = self.market["yes_price"],
            model_used        = model_used,
        )

    # ── extract key arguments ─────────────────────────────────────────────────
    def _extract_key_arguments(self, final_by_agent: dict) -> list[str]:
        """Pull the most informative reasoning snippets from all agents."""
        args = []
        for name, entry in final_by_agent.items():
            r = entry["response"]
            args.append(
                f"[{r['vote']} {r['confidence']:.2f}] {name}: {r['reasoning'][:180]}"
            )
        return args

    # ── Meta-Agent Judge ──────────────────────────────────────────────────────
    def _run_judge(
        self,
        final_by_agent: dict,
        panel_decision: str,
        panel_confidence: float,
    ) -> tuple[str, str, str, str, str]:
        """
        The Judge reviews all agents' reasoning and produces an independent verdict.
        Returns (verdict, reasoning, strongest_agent, weakest_agent, model_used).
        """
        _hr("─", Fore.MAGENTA)
        _cp("  ⚖️   META-AGENT JUDGE DELIBERATING...", Fore.MAGENTA + Style.BRIGHT)
        _hr("─", Fore.MAGENTA)

        # build full reasoning summary for the judge
        all_reasoning = "\n".join(
            f"{name} [{r['response']['vote']} conf={r['response']['confidence']:.2f}]:\n"
            f"  Reasoning: {r['response']['reasoning']}\n"
            f"  Critique:  {r['response']['critique']}"
            for name, r in final_by_agent.items()
        )

        agent_names = list(final_by_agent.keys())

        system = (
            "You are JUDGE-PRIME, an impartial meta-agent reviewing a multi-agent "
            "prediction market debate. Your role:\n"
            "1. Read all agents' final reasoning carefully\n"
            "2. Identify the SINGLE strongest argument (regardless of vote direction)\n"
            "3. Identify the SINGLE weakest argument\n"
            "4. Produce your OWN independent verdict — you are NOT obligated to follow "
            "the majority. Override if the minority made a better case.\n"
            "5. Explain your verdict in 3-5 sentences.\n\n"
            "Respond ONLY with valid JSON in this exact format:\n"
            '{"verdict":"YES","reasoning":"your explanation","'
            'strongest_agent":"AGENT-NAME","weakest_agent":"AGENT-NAME"}\n'
            "No markdown. No text outside JSON."
        )

        user = (
            f'Market question: "{self.market["question"]}"\n'
            f"Live market YES price: {self.market['yes_price']*100:.1f}%\n\n"
            f"Panel decision (before your review): {panel_decision} "
            f"(confidence {panel_confidence:.2f})\n\n"
            f"ALL AGENTS' FINAL REASONING:\n{all_reasoning}\n\n"
            f"Available agent names: {', '.join(agent_names)}\n\n"
            "Produce your independent JSON verdict now."
        )

        s = _spin("Judge deliberating...")
        raw, model_used = _groq_call(self.client, system, user)
        _unspin(s)

        # parse judge output
        try:
            cleaned = re.sub(r"```[a-z]*", "", raw).strip().strip("`")
            m = re.search(r"\{.*?\}", cleaned, re.DOTALL)
            if m:
                data = json.loads(m.group(0))
            else:
                data = json.loads(cleaned)

            verdict   = "YES" if str(data.get("verdict","")).upper() == "YES" else "NO"
            reasoning = str(data.get("reasoning", "No reasoning provided."))
            strongest = str(data.get("strongest_agent", agent_names[0]))
            weakest   = str(data.get("weakest_agent",   agent_names[-1]))
        except Exception:
            verdict   = panel_decision  # fall back to panel
            reasoning = "Judge parse error — deferring to panel majority."
            strongest = agent_names[0]
            weakest   = agent_names[-1]

        # print judge output
        vc = Fore.GREEN if verdict == "YES" else Fore.RED
        _cp(f"\n  JUDGE VERDICT: {vc}{verdict}{Style.RESET_ALL}", Fore.WHITE + Style.BRIGHT)
        for line in textwrap.wrap(f"  {reasoning}", W-2):
            _cp(line, Fore.WHITE)
        _cp(f"\n  Strongest argument: {Fore.GREEN}{strongest}{Style.RESET_ALL}", Fore.WHITE)
        _cp(f"  Weakest  argument: {Fore.RED}{weakest}{Style.RESET_ALL}", Fore.WHITE)

        override_note = ""
        if verdict != panel_decision:
            override_note = f" ← OVERRODE PANEL ({panel_decision})"
        _cp(f"\n  Final decision: {vc}{verdict}{Style.RESET_ALL}{Fore.YELLOW}{override_note}{Style.RESET_ALL}",
            Fore.WHITE + Style.BRIGHT)

        return verdict, reasoning, strongest, weakest, model_used
