"""
post_debate_chat.py — Post-debate interactive chat with individual agents or panel

After a debate concludes, the user can:
  - Chat privately with any individual agent (full multi-turn memory)
  - Broadcast a question to all 10 agents simultaneously
  - Ask the Judge to reconsider given new information
  - View a roster of all agents and their final votes
"""

from __future__ import annotations

import textwrap
import time
from colorama import Fore, Style
from groq import Groq

from agents import Agent
from debate_manager import MODELS, _groq_call, _hr, _cp, _spin, _unspin


# ── PostDebateChat ────────────────────────────────────────────────────────────
class PostDebateChat:
    """
    Manages post-debate conversation sessions.

    Each agent remembers:
      - The full debate transcript
      - Their own votes and reasoning
      - The final judge verdict
    """

    def __init__(
        self,
        client:  Groq,
        agents:  list[Agent],
        market:  dict,
        log:     list[dict],
        result:  dict,    # DebateResult.to_dict()
    ):
        self.client  = client
        self.agents  = agents
        self.market  = market
        self.log     = log
        self.result  = result

        self.agent_map = {}
        for a in agents:
            self.agent_map[str(a.id)]                    = a
            self.agent_map[a.name.lower()]               = a
            self.agent_map[a.name.split("-")[0].lower()] = a

        # pre-build debate summary once (used in every agent's system prompt)
        self._summary = self._build_summary()

    def _build_summary(self) -> str:
        lines = []
        for e in self.log:
            r = e["response"]
            lines.append(
                f"  R{e['round']} {e['agent']:10} [{r['vote']} conf={r['confidence']:.2f}]  "
                f"{r['reasoning'][:120]}"
            )
        return "\n".join(lines)

    def _agent_system_prompt(self, agent: Agent) -> str:
        entries = [e for e in self.log if e["agent"] == agent.name]
        own = "\n".join(
            f"  Round {e['round']}: {e['response']['vote']} "
            f"(conf {e['response']['confidence']:.2f}) — {e['response']['reasoning']}"
            for e in entries
        )
        final = self.result.get("judge_verdict", "?")
        return (
            f"You are {agent.name}. Personality: {agent.personality}\n\n"
            f'The debate question was: "{self.market["question"]}"\n'
            f"Judge final verdict: {final}\n\n"
            f"Your own votes this debate:\n{own}\n\n"
            f"Full debate transcript:\n{self._summary}\n\n"
            f"You are now in a post-debate Q&A with a human. "
            f"Be direct, stay in character, and keep responses to 3-4 sentences. "
            f"You CAN change your mind if the human makes a compelling argument — "
            f"but only if it's genuinely persuasive. Otherwise, defend your position."
        )

    # ── main entry point ──────────────────────────────────────────────────────
    def run(self):
        _hr()
        _cp("  💬  POST-DEBATE CHAT", Fore.CYAN + Style.BRIGHT)
        _hr()
        _cp("  Commands:", Fore.YELLOW)
        _cp("    1-10 / name  → private multi-turn chat with that agent", Fore.YELLOW)
        _cp("    all          → broadcast question to all 10 agents", Fore.YELLOW)
        _cp("    judge        → ask the Judge to reconsider", Fore.YELLOW)
        _cp("    roster       → show agent votes + confidence", Fore.YELLOW)
        _cp("    q            → back to main menu", Fore.YELLOW)
        _hr()

        while True:
            print()
            choice = input(f"{Fore.CYAN}  Talk to (number/name/all/judge/q): {Style.RESET_ALL}").strip().lower()

            if choice in ("q", "quit", "exit", "b", "back"):
                break

            if choice == "roster":
                self._show_roster()
                continue

            if choice == "all":
                self._panel_question()
                continue

            if choice == "judge":
                self._chat_judge()
                continue

            agent = self.agent_map.get(choice)
            if not agent:
                _cp(f"  Unknown: '{choice}'. Try 1-10, a name, 'all', 'judge', or 'q'.", Fore.RED)
                continue

            self._private_chat(agent)

    # ── roster ────────────────────────────────────────────────────────────────
    def _show_roster(self):
        _hr()
        _cp("  FINAL VOTES + CONFIDENCE", Fore.CYAN + Style.BRIGHT)
        final = self.result.get("agent_final_votes", {})
        for ag in self.agents:
            fv  = final.get(ag.name, {})
            v   = fv.get("vote",       "?")
            c   = fv.get("confidence", 0.0)
            w   = fv.get("weight",     ag.weight)
            vc  = Fore.GREEN if v == "YES" else Fore.RED
            bar = "█" * int(c*10) + "░" * (10-int(c*10))
            print(
                f"  {ag.color}{ag.name:<12}{Style.RESET_ALL}  "
                f"[{vc}{v:>3}{Style.RESET_ALL}]  "
                f"conf={c:.2f} [{Fore.CYAN}{bar}{Style.RESET_ALL}]  "
                f"weight={w:.3f}"
            )
        ds = self.result.get("disagreement_score", 0)
        _cp(f"\n  Disagreement score: {ds:.3f} "
            f"({'HIGH' if ds > 0.4 else 'MODERATE' if ds > 0.2 else 'LOW'})", Fore.YELLOW)
        _hr()

    # ── panel broadcast ───────────────────────────────────────────────────────
    def _panel_question(self):
        question = input(f"{Fore.CYAN}  Your question to all agents: {Style.RESET_ALL}").strip()
        if not question:
            return
        _cp("\n  ── ALL-AGENT PANEL ──", Fore.CYAN + Style.BRIGHT)

        for ag in self.agents:
            sys_p = self._agent_system_prompt(ag)
            s     = _spin(f"{ag.name} responding...")
            try:
                reply, _ = _groq_call(self.client, sys_p, question)
            except Exception as e:
                reply = f"[Error: {e}]"
            _unspin(s)

            pad   = "  " + " " * (len(ag.name) + 4)
            print(f"\n  {ag.color}{ag.name}{Style.RESET_ALL} → ", end="")
            lines = textwrap.wrap(reply, 64)
            print(lines[0] if lines else "")
            for l in lines[1:]:
                print(pad + l)
        print()

    # ── private multi-turn chat with one agent ────────────────────────────────
    def _private_chat(self, agent: Agent):
        sys_p = self._agent_system_prompt(agent)
        hist  = []   # multi-turn conversation history

        final = self.result.get("agent_final_votes", {}).get(agent.name, {})
        vc    = Fore.GREEN if final.get("vote") == "YES" else Fore.RED

        _cp(f"\n  ── Chatting with {agent.name} ── (type 'switch' to change agent)", agent.color)
        _cp(
            f"  Final vote: {vc}{final.get('vote','?')}{Style.RESET_ALL}  "
            f"conf={final.get('confidence',0):.2f}  "
            f"weight={final.get('weight', agent.weight):.3f}",
            Fore.WHITE,
        )
        print()

        while True:
            user_msg = input(
                f"{Fore.CYAN}  You → {agent.name}: {Style.RESET_ALL}"
            ).strip()

            if not user_msg or user_msg.lower() in ("switch", "back", "b"):
                break

            hist.append({"role": "user", "content": user_msg})

            s = _spin(f"{agent.name} thinking...")
            try:
                resp = self.client.chat.completions.create(
                    model=MODELS[0],
                    messages=[{"role": "system", "content": sys_p}] + hist,
                    max_tokens=400,
                    temperature=0.85,
                )
                reply = resp.choices[0].message.content.strip()
            except Exception as e:
                reply = f"[Error: {e}]"
            _unspin(s)

            hist.append({"role": "assistant", "content": reply})

            pad   = "  " + " " * (len(agent.name) + 4)
            print(f"\n  {agent.color}{agent.name}{Style.RESET_ALL} → ", end="")
            lines = textwrap.wrap(reply, 64)
            print(lines[0] if lines else "")
            for l in lines[1:]:
                print(pad + l)
            print()

    # ── chat with judge ───────────────────────────────────────────────────────
    def _chat_judge(self):
        _cp("\n  ── JUDGE-PRIME Q&A ──", Fore.MAGENTA + Style.BRIGHT)
        final    = self.result.get("judge_verdict", "?")
        reasoning = self.result.get("judge_reasoning", "")
        _cp(f"  Verdict: {final}  |  {reasoning[:120]}", Fore.WHITE)
        print()

        sys_p = (
            "You are JUDGE-PRIME, the impartial meta-agent who reviewed this debate.\n"
            f'The question was: "{self.market["question"]}"\n'
            f"Your verdict was: {final}\n"
            f"Your reasoning: {reasoning}\n\n"
            f"Full debate transcript:\n{self._summary}\n\n"
            "Answer the human's questions about your verdict. You can reconsider if "
            "presented with genuinely new evidence, but defend your reasoning otherwise. "
            "Keep responses to 3-5 sentences."
        )
        hist = []

        while True:
            user_msg = input(f"{Fore.MAGENTA}  You → JUDGE-PRIME: {Style.RESET_ALL}").strip()
            if not user_msg or user_msg.lower() in ("back", "b", "q"):
                break

            hist.append({"role": "user", "content": user_msg})
            s = _spin("Judge deliberating...")
            try:
                resp = self.client.chat.completions.create(
                    model=MODELS[0],
                    messages=[{"role": "system", "content": sys_p}] + hist,
                    max_tokens=400,
                    temperature=0.8,
                )
                reply = resp.choices[0].message.content.strip()
            except Exception as e:
                reply = f"[Error: {e}]"
            _unspin(s)

            hist.append({"role": "assistant", "content": reply})
            pad = "  " + " " * 14
            print(f"\n  {Fore.MAGENTA}JUDGE-PRIME{Style.RESET_ALL} → ", end="")
            lines = textwrap.wrap(reply, 64)
            print(lines[0] if lines else "")
            for l in lines[1:]:
                print(pad + l)
            print()
