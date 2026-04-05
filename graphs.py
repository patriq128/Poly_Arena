"""
graphs.py — All chart generation for PolyArena v2

Charts produced after each debate:
  1. AI Consensus trend (+ market price reference line)
  2. YES vs NO cumulative vote share
  3. Per-agent confidence over rounds (multi-line, one line per agent)
  4. Disagreement heatmap (agents × rounds, colour = confidence direction)
  5. Per-agent final vote stacked bar
  6. Final split donut

All saved as a single multi-panel PNG.
"""

from __future__ import annotations

import textwrap
from datetime import datetime
from pathlib import Path
from typing import Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import numpy as np

from agents import Agent

GRAPHS_DIR = Path("polyarena_graphs")
GRAPHS_DIR.mkdir(exist_ok=True)

# colour palette (hex, for matplotlib — colorama colors not usable here)
AGENT_HEX = [
    "#00ff88", "#ff4466", "#4488ff", "#ffaa00", "#aa44ff",
    "#00ccff", "#ffdd44", "#ff44aa", "#88ff00", "#44ddff",
]
BG  = "#050a0f"
PAN = "#040c14"
FG  = "#c8d8e8"
DIM = "#304050"


def make_graphs(
    market:     dict,
    agents:     list[Agent],
    log:        list[dict],       # full debate log
    result:     dict,             # DebateResult.to_dict()
    chart_data: list[dict],       # from DebateManager.chart_data
) -> str:
    """
    Generate all panels, save to polyarena_graphs/, return file path.
    """
    q   = market["question"]
    ts  = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = GRAPHS_DIR / f"debate_{market.get('id','x')}_{ts}.png"

    fig = plt.figure(figsize=(18, 12))
    fig.patch.set_facecolor(BG)

    # 3×2 grid
    gs = fig.add_gridspec(3, 3, hspace=0.45, wspace=0.35,
                          left=0.06, right=0.97, top=0.93, bottom=0.06)

    ax1 = fig.add_subplot(gs[0, 0])   # consensus trend
    ax2 = fig.add_subplot(gs[0, 1])   # yes vs no share
    ax3 = fig.add_subplot(gs[0, 2])   # avg confidence per round
    ax4 = fig.add_subplot(gs[1, :2])  # agent confidence lines (multi-line)
    ax5 = fig.add_subplot(gs[1, 2])   # disagreement heatmap
    ax6 = fig.add_subplot(gs[2, 0])   # per-agent final vote bars
    ax7 = fig.add_subplot(gs[2, 1])   # final split donut
    ax8 = fig.add_subplot(gs[2, 2])   # weighted vote breakdown

    axes = [ax1, ax2, ax3, ax4, ax5, ax6, ax7, ax8]
    for ax in axes:
        ax.set_facecolor(PAN)
        ax.tick_params(colors=DIM, labelsize=7)
        for sp in ax.spines.values():
            sp.set_edgecolor("#0a2030")
        ax.title.set_color(FG)
        ax.title.set_fontsize(9)

    title = textwrap.fill(f"POLY⚡ARENA v2 — {q}", 100)
    fig.suptitle(title, color="#00ff88", fontsize=10, fontweight="bold")

    # ── helpers ───────────────────────────────────────────────────────────────
    agent_names = [a.name for a in agents]

    def xtl(ax, labels, n=8):
        step = max(1, len(labels)//n)
        ax.set_xticks(range(0, len(labels), step))
        ax.set_xticklabels([labels[i] for i in range(0, len(labels), step)],
                           rotation=40, ha="right", fontsize=6)

    # ── 1. Consensus trend ────────────────────────────────────────────────────
    steps     = [d["step"]      for d in chart_data]
    consensus = [d["consensus"] for d in chart_data]
    x = list(range(len(steps)))

    ax1.set_title("AI Consensus YES% over Time")
    ax1.fill_between(x, consensus, alpha=0.2, color="#00ff88")
    ax1.plot(x, consensus, color="#00ff88", lw=2, label="AI Consensus")
    ax1.axhline(market["yes_price"]*100, color="#4488ff", ls="--", lw=1.2,
                label=f"Market {market['yes_price']*100:.1f}%")
    ax1.set_ylim(0, 100)
    ax1.set_ylabel("YES %", color=DIM, fontsize=7)
    ax1.legend(fontsize=6, facecolor=BG, edgecolor="#0a2030", labelcolor=FG)
    xtl(ax1, steps)

    # ── 2. YES vs NO share ────────────────────────────────────────────────────
    yes_pcts = [d["yes_pct"] for d in chart_data]
    no_pcts  = [d["no_pct"]  for d in chart_data]

    ax2.set_title("Cumulative YES vs NO Vote Share")
    ax2.fill_between(x, yes_pcts, alpha=0.25, color="#00ff88")
    ax2.fill_between(x, no_pcts,  alpha=0.25, color="#ff4466")
    ax2.plot(x, yes_pcts, color="#00ff88", lw=2, label="YES%")
    ax2.plot(x, no_pcts,  color="#ff4466", lw=2, label="NO%")
    ax2.set_ylim(0, 100)
    ax2.set_ylabel("Vote Share %", color=DIM, fontsize=7)
    ax2.legend(fontsize=6, facecolor=BG, edgecolor="#0a2030", labelcolor=FG)
    xtl(ax2, steps)

    # ── 3. Avg confidence per round ───────────────────────────────────────────
    round_avgs = {}
    for entry in log:
        r = entry["round"]
        c = entry["response"]["confidence"]
        round_avgs.setdefault(r, []).append(c)
    rnd_labels  = sorted(round_avgs.keys())
    rnd_means   = [np.mean(round_avgs[r]) for r in rnd_labels]
    rnd_stds    = [np.std( round_avgs[r]) for r in rnd_labels]

    ax3.set_title("Panel Avg Confidence per Round")
    ax3.bar(rnd_labels, rnd_means, color="#4488ff", alpha=0.8, width=0.5)
    ax3.errorbar(rnd_labels, rnd_means, yerr=rnd_stds, fmt="none",
                 ecolor="#ffdd44", elinewidth=1.5, capsize=4)
    ax3.set_ylim(0, 1)
    ax3.set_xticks(rnd_labels)
    ax3.set_xticklabels([f"Round {r}" for r in rnd_labels], fontsize=7)
    ax3.set_ylabel("Confidence", color=DIM, fontsize=7)
    ax3.axhline(0.5, color=DIM, ls=":", lw=1)

    # ── 4. Per-agent confidence over rounds (multi-line) ──────────────────────
    ax4.set_title("Agent Confidence Trajectory Across Rounds")
    ax4.set_ylabel("Confidence", color=DIM, fontsize=7)
    ax4.set_ylim(0, 1)
    ax4.axhline(0.5, color=DIM, ls=":", lw=0.8)

    for i, agent in enumerate(agents):
        conf_by_round: dict[int, float] = {}
        for entry in log:
            if entry["agent"] == agent.name:
                conf_by_round[entry["round"]] = entry["response"]["confidence"]
        if not conf_by_round: continue
        rnds  = sorted(conf_by_round.keys())
        confs = [conf_by_round[r] for r in rnds]
        col   = AGENT_HEX[i % len(AGENT_HEX)]
        ax4.plot(rnds, confs, marker="o", color=col, lw=1.5, ms=4,
                 label=agent.name.split("-")[0])

    ax4.set_xticks([1, 2, 3])
    ax4.set_xticklabels(["Round 1", "Round 2", "Round 3"], fontsize=7)
    ax4.legend(fontsize=6, facecolor=BG, edgecolor="#0a2030", labelcolor=FG,
               ncol=5, loc="lower right")

    # ── 5. Disagreement heatmap (agents × rounds) ─────────────────────────────
    # Cell value: +confidence if YES, -confidence if NO → colour shows position
    ax5.set_title("Disagreement Heatmap\n(green=YES, red=NO, intensity=confidence)")

    heat = np.zeros((len(agents), 3))   # 3 rounds
    for entry in log:
        try:
            ai = agent_names.index(entry["agent"])
            ri = entry["round"] - 1
            c  = entry["response"]["confidence"]
            v  = 1 if entry["response"]["vote"] == "YES" else -1
            heat[ai, ri] = v * c
        except ValueError:
            pass

    # diverging colormap: red=NO, green=YES
    cmap = mcolors.LinearSegmentedColormap.from_list(
        "polyarena", ["#ff4466", "#050a0f", "#00ff88"]
    )
    im = ax5.imshow(heat, cmap=cmap, vmin=-1, vmax=1, aspect="auto")
    ax5.set_yticks(range(len(agents)))
    ax5.set_yticklabels([a.name.split("-")[0] for a in agents], fontsize=6, color=FG)
    ax5.set_xticks([0, 1, 2])
    ax5.set_xticklabels(["R1", "R2", "R3"], fontsize=7, color=FG)
    ax5.tick_params(colors=FG)

    # annotate cells
    for i in range(len(agents)):
        for j in range(3):
            val  = heat[i, j]
            txt  = f"{abs(val):.2f}" if val != 0 else "—"
            tcol = "white" if abs(val) > 0.5 else FG
            ax5.text(j, i, txt, ha="center", va="center", fontsize=5.5, color=tcol)

    plt.colorbar(im, ax=ax5, fraction=0.04, pad=0.02).ax.tick_params(labelsize=6, colors=FG)

    # ── 6. Per-agent final vote stacked bars ──────────────────────────────────
    ax6.set_title("Per-Agent Final Vote + Confidence")
    final_votes = result.get("agent_final_votes", {})
    bar_names   = [a.name.split("-")[0] for a in agents]
    yes_confs   = []
    no_confs    = []
    for ag in agents:
        fv = final_votes.get(ag.name, {})
        c  = fv.get("confidence", 0.0)
        if fv.get("vote") == "YES":
            yes_confs.append(c); no_confs.append(0)
        else:
            yes_confs.append(0); no_confs.append(c)

    bx = np.arange(len(bar_names))
    ax6.bar(bx, yes_confs, color="#00ff88", alpha=0.85, label="YES")
    ax6.bar(bx, no_confs,  color="#ff4466", alpha=0.85, label="NO")
    ax6.set_xticks(bx)
    ax6.set_xticklabels(bar_names, rotation=45, ha="right", fontsize=6)
    ax6.set_ylabel("Confidence", color=DIM, fontsize=7)
    ax6.set_ylim(0, 1)
    ax6.legend(fontsize=6, facecolor=BG, edgecolor="#0a2030", labelcolor=FG)

    # ── 7. Final split donut ──────────────────────────────────────────────────
    ax7.set_title("Final Split")
    raw_yes = result.get("raw_yes_count", 0)
    raw_no  = result.get("raw_no_count",  0)
    sizes   = [max(raw_yes, 0.01), max(raw_no, 0.01)]

    wedges, texts, autos = ax7.pie(
        sizes,
        labels=[f"YES  {raw_yes}", f"NO  {raw_no}"],
        colors=["#00ff88", "#ff4466"],
        autopct="%1.1f%%",
        startangle=90,
        pctdistance=0.78,
        wedgeprops={"edgecolor": BG, "linewidth": 2},
    )
    for t in texts:  t.set_color(FG);  t.set_fontsize(8)
    for a in autos:  a.set_color(BG);  a.set_fontweight("bold"); a.set_fontsize(8)
    ax7.add_patch(plt.Circle((0, 0), 0.55, fc=PAN))
    winner = result.get("judge_verdict", "NO")
    ax7.text(0, 0.12, winner,      ha="center", va="center", fontsize=16, fontweight="bold",
             color="#00ff88" if winner=="YES" else "#ff4466")
    ax7.text(0,-0.15, f"conf {result.get('confidence_score',0):.2f}",
             ha="center", va="center", fontsize=7, color=DIM)

    # ── 8. Weighted vote breakdown ────────────────────────────────────────────
    ax8.set_title("Weighted Decision Breakdown")
    wy = result.get("weighted_yes", 0)
    wn = result.get("weighted_no",  0)
    ds = result.get("disagreement_score", 0)
    bars = ax8.barh(["Weighted YES", "Weighted NO", "Disagreement"],
                    [wy, wn, ds],
                    color=["#00ff88", "#ff4466", "#ffdd44"],
                    alpha=0.85, height=0.5)
    for bar, val in zip(bars, [wy, wn, ds]):
        ax8.text(bar.get_width() + 0.01, bar.get_y() + bar.get_height()/2,
                 f"{val:.3f}", va="center", fontsize=8, color=FG)
    ax8.set_xlim(0, max(wy, wn, ds, 0.1) * 1.3)
    ax8.set_facecolor(PAN)
    ax8.tick_params(colors=FG, labelsize=8)

    plt.savefig(path, dpi=130, bbox_inches="tight", facecolor=BG)
    plt.close()
    return str(path)
