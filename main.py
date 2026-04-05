#!/usr/bin/env python3
"""
main.py — PolyArena v2 Terminal Entry Point

The main menu wires together all modules:
  agents.py          → Agent class + registry
  debate_manager.py  → 3-round structured debate orchestration
  decision_engine.py → Weighted aggregation + Meta-Agent Judge
  track_record.py    → Persistent agent performance tracking
  graphs.py          → Multi-panel chart generation
  polymarket.py      → Polymarket API + save/load
  post_debate_chat.py→ Post-debate interactive chat

Setup:
  pip install groq requests matplotlib colorama numpy
  export GROQ_API_KEY=gsk_...
  python3 main.py
"""

import os, sys, time, json
from pathlib import Path
from datetime import datetime

# ── dependency check ──────────────────────────────────────────────────────────
MISSING = []
try:    from groq import Groq
except: MISSING.append("groq")
try:    import requests
except: MISSING.append("requests")
try:
    from colorama import Fore, Style, init as _ci; _ci(autoreset=True)
except: MISSING.append("colorama")
try:
    import matplotlib; import numpy
except: MISSING.append("matplotlib numpy")

if MISSING:
    print(f"\n  ✗  Missing packages: {', '.join(MISSING)}")
    print(f"  Run:  pip install {' '.join(MISSING)}\n")
    sys.exit(1)

# ── local modules ─────────────────────────────────────────────────────────────
from agents          import build_agents
from debate_manager  import DebateManager, W, _hr, _cp, _spin, _unspin
from decision_engine import DecisionEngine
from track_record    import TrackRecord
from graphs          import make_graphs
from polymarket      import (extract_slug, fetch_by_slug, fetch_trending,
                              save_market, load_saved_markets,
                              save_debate_result, load_past_debates, fmt_volume)
from post_debate_chat import PostDebateChat

# ── terminal helpers ──────────────────────────────────────────────────────────
def header():
    os.system("cls" if os.name == "nt" else "clear")
    print()
    g = Fore.GREEN + Style.BRIGHT
    print(g + "  ██████╗  ██████╗ ██╗  ██╗   ██╗     █████╗ ██████╗ ███████╗███╗   ██╗ █████╗ ")
    print(g + "  ██╔══██╗██╔═══██╗██║  ╚██╗ ██╔╝    ██╔══██╗██╔══██╗██╔════╝████╗  ██║██╔══██╗")
    print(g + "  ██████╔╝██║   ██║██║   ╚████╔╝     ███████║██████╔╝█████╗  ██╔██╗ ██║███████║")
    print(g + "  ██╔═══╝ ██║   ██║██║    ╚██╔╝      ██╔══██║██╔══██╗██╔══╝  ██║╚██╗██║██╔══██║")
    print(g + "  ██║     ╚██████╔╝███████╗██║        ██║  ██║██║  ██║███████╗██║ ╚████║██║  ██║")
    print(g + "  ╚═╝      ╚═════╝ ╚══════╝╚═╝        ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═══╝╚═╝  ╚═╝" + Style.RESET_ALL)
    print(Fore.CYAN + "  " + "─"*76 + Style.RESET_ALL)
    print(Fore.WHITE + "  ⚡  v2 · Groq · Llama 3.3 70B · Structured Debate · Judge · Heatmap  ⚡" + Style.RESET_ALL)
    print(Fore.CYAN + "  " + "─"*76 + Style.RESET_ALL)
    print()

def ask(text, color=Fore.CYAN) -> str:
    return input(color + text + Style.RESET_ALL).strip()

# ── Groq client ───────────────────────────────────────────────────────────────
def get_client() -> Groq:
    key = os.environ.get("GROQ_API_KEY", "").strip()
    if not key:
        header()
        _cp("  ✗  GROQ_API_KEY not set!", Fore.RED + Style.BRIGHT)
        _cp("  1. Go to  https://console.groq.com  (free, no credit card)", Fore.YELLOW)
        _cp("  2. Create an API key", Fore.YELLOW)
        _cp("  3. Run:  export GROQ_API_KEY=gsk_...  then re-run", Fore.YELLOW)
        print()
        key = ask("  Or paste your key now: ")
        if not key:
            sys.exit(1)
        os.environ["GROQ_API_KEY"] = key
    return Groq(api_key=key)

# ── full debate flow ──────────────────────────────────────────────────────────
def debate_flow(client: Groq, agents: list, market: dict, tracker: TrackRecord,
                allow_human: bool = False):
    """
    Full pipeline:
      1. Run 3-round debate
      2. Decision engine (aggregation + judge)
      3. Generate graphs
      4. Save results
      5. Update track record
      6. Post-debate chat
    """
    header()
    _cp(f"  📋  {market['question']}", Fore.WHITE + Style.BRIGHT)
    _hr()

    # ── 1. Run debate ─────────────────────────────────────────────────────────
    manager   = DebateManager(client, agents, market, allow_human=allow_human)
    log       = manager.run()
    chart     = manager.chart_data

    # ── 2. Decision engine ────────────────────────────────────────────────────
    engine    = DecisionEngine(client, agents, log, market)
    result    = engine.compute()
    result_d  = result.to_dict()

    # ── print final summary ───────────────────────────────────────────────────
    _hr("═", Fore.GREEN if result.final_decision=="YES" else Fore.RED)
    vc = Fore.GREEN if result.final_decision=="YES" else Fore.RED
    _cp(f"\n  ⚡  FINAL DECISION: {vc}{result.final_decision}{Style.RESET_ALL}  "
        f"  confidence={result.confidence_score:.3f}  "
        f"disagreement={result.disagreement_score:.3f}", Fore.WHITE + Style.BRIGHT)
    _cp(f"  {result.consensus_direction}", Fore.CYAN)
    _cp(f"  Raw: {result.raw_yes_count} YES / {result.raw_no_count} NO  "
        f"| Weighted YES {result.weighted_yes:.3f}  NO {result.weighted_no:.3f}", Fore.WHITE)
    _hr("═", Fore.GREEN if result.final_decision=="YES" else Fore.RED)

    # ── 3. Graphs ─────────────────────────────────────────────────────────────
    _cp("\n  Generating graphs...", Fore.CYAN)
    gpath = make_graphs(market, agents, log, result_d, chart)
    _cp(f"  ✓ Graph → {gpath}", Fore.GREEN)
    _open_file(gpath)

    # ── 4. Save ───────────────────────────────────────────────────────────────
    spath = save_debate_result(market, log, result_d, chart)
    _cp(f"  ✓ Debate saved → {spath}", Fore.GREEN)

    # ── 5. Track record ───────────────────────────────────────────────────────
    tracker.record_predictions(agents, result_d, market)

    # ── 6. What next? ─────────────────────────────────────────────────────────
    _hr()
    _cp("  What next?", Fore.CYAN + Style.BRIGHT)
    action = ask("  [c] Chat with AIs  [r] Re-debate  [b] Main menu: ").lower()
    if action == "c":
        PostDebateChat(client, agents, market, log, result_d).run()
    elif action == "r":
        debate_flow(client, agents, market, tracker, allow_human)

# ── open file helper ──────────────────────────────────────────────────────────
def _open_file(path: str):
    try:
        if sys.platform == "darwin":              os.system(f"open '{path}'")
        elif sys.platform.startswith("linux"):    os.system(f"xdg-open '{path}'")
        elif sys.platform == "win32":             os.startfile(path)
    except Exception:
        pass

# ── menu: paste URL ───────────────────────────────────────────────────────────
def menu_url(client, agents, tracker):
    header()
    _cp("  🔗  PASTE POLYMARKET URL", Fore.CYAN + Style.BRIGHT)
    _hr()
    _cp("  Examples:", Fore.WHITE)
    _cp("    https://polymarket.com/event/will-btc-hit-100k", Fore.YELLOW)
    _cp("    will-btc-hit-100k  ← bare slug also works", Fore.YELLOW)
    _hr()

    url = ask("  URL or slug: ")
    if not url: return

    s = _spin("Fetching market from Polymarket API...")
    try:
        slug   = extract_slug(url)
        market = fetch_by_slug(slug)
        _unspin(s)
    except Exception as e:
        _unspin(s)
        _cp(f"\n  ✗  {e}", Fore.RED)
        ask("  Press Enter to continue...")
        return

    _hr()
    _cp("  ✓  Market found!", Fore.GREEN + Style.BRIGHT)
    _cp(f"  Question : {market['question']}", Fore.WHITE)
    _cp(f"  ID       : {market['id']}", Fore.CYAN)
    _cp(f"  YES      : {market['yes_price']*100:.1f}%", Fore.GREEN)
    _cp(f"  NO       : {market['no_price']*100:.1f}%", Fore.RED)
    _cp(f"  Volume   : {fmt_volume(market['volume'])}", Fore.YELLOW)
    _hr()

    human = ask("  Allow human intervention mid-debate? [y/N]: ").lower() == "y"
    action = ask("  [s] Save  [d] Debate  [sd] Save & Debate  [b] Back: ").lower()
    if action in ("s","sd"): save_market(market); _cp("  ✓ Saved.", Fore.GREEN); time.sleep(0.4)
    if action in ("d","sd"): debate_flow(client, agents, market, tracker, human)

# ── menu: trending ────────────────────────────────────────────────────────────
def menu_trending(client, agents, tracker):
    header()
    _cp("  🔥  TRENDING MARKETS  (live from Polymarket)", Fore.CYAN + Style.BRIGHT)
    _hr()
    s = _spin("Fetching top markets by volume...")
    mkts = fetch_trending(8)
    _unspin(s)

    if not mkts:
        _cp("  Could not reach Polymarket API.", Fore.RED)
        ask("  Press Enter..."); return

    for i, m in enumerate(mkts, 1):
        _cp(f"  [{i}] YES {m['yes_price']*100:5.1f}%  {fmt_volume(m['volume']):>10}  {m['question'][:50]}", Fore.WHITE)
    _hr()

    c = ask("  Pick number (or b): ").lower()
    if c == "b": return
    try:
        market = mkts[int(c)-1]
        human  = ask("  Allow human intervention? [y/N]: ").lower() == "y"
        action = ask("  [s] Save  [d] Debate  [sd] Save & Debate  [b]: ").lower()
        if action in ("s","sd"): save_market(market); _cp("  ✓ Saved.", Fore.GREEN); time.sleep(0.4)
        if action in ("d","sd"): debate_flow(client, agents, market, tracker, human)
    except (ValueError, IndexError):
        _cp("  Invalid.", Fore.RED); time.sleep(0.8)

# ── menu: saved markets ───────────────────────────────────────────────────────
def menu_saved(client, agents, tracker):
    while True:
        header()
        _cp("  📁  SAVED MARKETS", Fore.CYAN + Style.BRIGHT)
        _hr()
        mkts = load_saved_markets()
        if not mkts:
            _cp("  No saved markets yet.", Fore.YELLOW)
            ask("  Press Enter..."); return

        for i, m in enumerate(mkts, 1):
            _cp(f"  [{i}] YES {m['yes_price']*100:5.1f}%  {fmt_volume(m['volume']):>10}  {m['question'][:50]}", Fore.WHITE)
        _cp("  [d] Delete  [b] Back", Fore.YELLOW)
        _hr()

        c = ask("  Pick to debate / action: ").lower()
        if c == "b": return
        if c == "d":
            idx = ask("  Number to delete: ")
            try:
                m   = mkts[int(idx)-1]
                p   = Path("polyarena_saves") / f"{m['id']}.json"
                p.unlink(missing_ok=True)
                _cp("  ✓ Deleted.", Fore.GREEN); time.sleep(0.8)
            except Exception:
                _cp("  Invalid.", Fore.RED); time.sleep(0.8)
            continue
        try:
            market = mkts[int(c)-1]
            human  = ask("  Allow human intervention? [y/N]: ").lower() == "y"
            debate_flow(client, agents, market, tracker, human)
            return
        except (ValueError, IndexError):
            _cp("  Invalid.", Fore.RED); time.sleep(0.8)

# ── menu: past debates ────────────────────────────────────────────────────────
def menu_past(agents):
    header()
    _cp("  📊  PAST DEBATE RESULTS", Fore.CYAN + Style.BRIGHT)
    _hr()
    results = load_past_debates()
    if not results:
        _cp("  No past debates saved yet.", Fore.YELLOW)
        ask("  Press Enter..."); return

    for i, (fname, data) in enumerate(results[:12], 1):
        m  = data.get("market", {})
        r  = data.get("result", {})
        w  = r.get("judge_verdict", "?")
        wc = Fore.GREEN if w == "YES" else Fore.RED
        ds = r.get("disagreement_score", 0)
        ts = data.get("saved_at", "")[:16]
        _cp(f"  [{i}] {ts}  {wc}{w}{Style.RESET_ALL}  ds={ds:.2f}  {m.get('question','?')[:44]}", Fore.WHITE)
    _hr()

    c = ask("  Pick to regenerate graph  /  b: ").lower()
    if c == "b": return
    try:
        _, data = results[int(c)-1]
        _cp("\n  Regenerating graph...", Fore.CYAN)
        gpath = make_graphs(
            data["market"], agents, data["debate_log"],
            data["result"], data["chart_data"]
        )
        _cp(f"  ✓ Graph → {gpath}", Fore.GREEN)
        _open_file(gpath)
    except (ValueError, IndexError):
        _cp("  Invalid.", Fore.RED)
    ask("  Press Enter to continue...")

# ── menu: track record ────────────────────────────────────────────────────────
def menu_track_record(tracker: TrackRecord, agents: list):
    header()
    _cp("  🏆  AGENT TRACK RECORD", Fore.CYAN + Style.BRIGHT)
    _hr()
    tracker.print_leaderboard()

    pending = tracker.pending_resolutions()
    if pending:
        _cp(f"  {len(pending)} market(s) awaiting resolution:", Fore.YELLOW)
        for i, p in enumerate(pending, 1):
            _cp(f"  [{i}] {p['market_id'][:12]}  {p['question'][:55]}", Fore.WHITE)
        _hr()
        c = ask("  Resolve a market? Enter number (or b): ").lower()
        if c != "b":
            try:
                p = pending[int(c)-1]
                outcome = ask(f"  Outcome for '{p['question'][:40]}' [YES/NO]: ").upper()
                if outcome in ("YES", "NO"):
                    n = tracker.resolve_market(p["market_id"], outcome)
                    tracker.apply_to_agents(agents)
                    _cp(f"  ✓ Updated {n} agent predictions.", Fore.GREEN)
                    time.sleep(0.8)
                    tracker.print_leaderboard()
            except (ValueError, IndexError):
                _cp("  Invalid.", Fore.RED)

    ask("  Press Enter to continue...")

# ── menu: roster ──────────────────────────────────────────────────────────────
def menu_roster(agents, tracker):
    header()
    _cp("  🤖  AGENT ROSTER", Fore.CYAN + Style.BRIGHT)
    _hr()
    _cp(f"  {'Name':<12}  {'Bias':>5}  {'Weight':>7}  {'Acc':>5}  Personality", Fore.CYAN)
    _hr("─", Fore.CYAN)
    for ag in agents:
        print(
            f"  {ag.color}{ag.name:<12}{Style.RESET_ALL}  "
            f"{ag.bias:.2f}   {ag.weight:.4f}  "
            f"{ag.accuracy:.1%}  "
            f"{ag.personality[:52]}"
        )
    _hr()
    _cp("  All agents run on llama-3.3-70b-versatile via Groq (free).", Fore.YELLOW)
    _cp("  Bias affects initial vote tendency AND resistance to opinion change.", Fore.YELLOW)
    _cp("  Weight = accuracy × (0.7 + 0.3 × bias) — updates after each resolution.", Fore.YELLOW)
    _cp("  JUDGE-PRIME reviews all reasoning and can override the panel majority.", Fore.YELLOW)
    _hr()
    ask("  Press Enter to continue...")

# ── main ──────────────────────────────────────────────────────────────────────
def main():
    client  = get_client()
    agents  = build_agents()
    tracker = TrackRecord()
    tracker.apply_to_agents(agents)   # load saved accuracy into agents

    while True:
        header()
        _cp("  MAIN MENU", Fore.CYAN + Style.BRIGHT)
        _hr()
        _cp("  [1]  🔗  Paste Polymarket URL  →  fetch, save, debate", Fore.WHITE)
        _cp("  [2]  🔥  Browse live trending markets", Fore.WHITE)
        _cp("  [3]  📁  My saved markets", Fore.WHITE)
        _cp("  [4]  📊  Past debate results + graphs", Fore.WHITE)
        _cp("  [5]  🏆  Agent track record + resolve markets", Fore.WHITE)
        _cp("  [6]  🤖  Agent roster + weights", Fore.WHITE)
        _cp("  [q]  Exit", Fore.WHITE)
        _hr()
        _cp("  Model: llama-3.3-70b-versatile  ·  Groq (free)  ·  console.groq.com", Fore.CYAN)
        _hr()

        c = ask("  Choice: ").lower()
        if   c == "1": menu_url(client, agents, tracker)
        elif c == "2": menu_trending(client, agents, tracker)
        elif c == "3": menu_saved(client, agents, tracker)
        elif c == "4": menu_past(agents)
        elif c == "5": menu_track_record(tracker, agents)
        elif c == "6": menu_roster(agents, tracker)
        elif c in ("q","quit","exit"):
            _cp("\n  👋  Goodbye!\n", Fore.GREEN + Style.BRIGHT)
            sys.exit(0)
        else:
            _cp("  Unknown option.", Fore.RED)
            time.sleep(0.6)


if __name__ == "__main__":
    main()
