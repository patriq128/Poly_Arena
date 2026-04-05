# POLY ARENA 

> An advanced multi-agent AI debate system for Polymarket prediction markets — structured outputs, meta-agent judge, disagreement heatmap, track record system, and post-debate chat. Powered by Groq (free).

```
  ██████╗  ██████╗ ██╗  ██╗   ██╗     █████╗ ██████╗ ███████╗███╗   ██╗ █████╗
  ██╔══██╗██╔═══██╗██║  ╚██╗ ██╔╝    ██╔══██╗██╔══██╗██╔════╝████╗  ██║██╔══██╗
  ██████╔╝██║   ██║██║   ╚████╔╝     ███████║██████╔╝█████╗  ██╔██╗ ██║███████║
  ██╔═══╝ ██║   ██║██║    ╚██╔╝      ██╔══██║██╔══██╗██╔══╝  ██║╚██╗██║██╔══██║
  ██║     ╚██████╔╝███████╗██║        ██║  ██║██║  ██║███████╗██║ ╚████║██║  ██║
  ╚═╝      ╚═════╝ ╚══════╝╚═╝        ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═══╝╚═╝  ╚═╝
```

[![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python&logoColor=white)](https://python.org)
[![Groq](https://img.shields.io/badge/AI-Groq%20%2B%20Llama%203.3%2070B-orange)](https://console.groq.com)
[![Polymarket](https://img.shields.io/badge/Data-Polymarket%20API-purple)](https://polymarket.com)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## What is this?

PolyArena is a fully modular multi-agent debate system that pits **10 AI agents** against each other in structured, 3-round debates about [Polymarket](https://polymarket.com) prediction markets.

Each agent has a defined personality, a bias score (which mathematically influences both their initial vote and how hard they resist changing their mind), and a growing track record of past predictions. After all 3 rounds, a **Meta-Agent Judge** reviews every agent's reasoning independently and produces a final verdict — which can override the panel majority if the minority made the better case.

**Vibe coded**

---

## What's new in v2

| Feature | v1 | v2 |
|---|---|---|
| Agent output format | Plain text | Structured JSON with `vote`, `confidence`, `reasoning`, `critique` |
| Debate rounds | 3 rounds, simple | R1 independent · R2 reactive · R3 final refinement |
| Agent memory | Per-debate context only | Full round history + confidence trajectory |
| Bias mechanics | Cosmetic label | Mathematically affects vote tendency + flip resistance |
| Decision engine | Vote count | Weighted aggregation (`confidence × weight`) |
| Disagreement score | None | Variance of signed confidence values |
| Meta-Agent Judge | None | JUDGE-PRIME reviews all reasoning, can override majority |
| Track record | None | Persistent per-agent accuracy, dynamically updates weights |
| Graphs | 4 panels | 8 panels including **disagreement heatmap** + confidence trajectories |
| Human intervention | None | Inject statements mid-debate between rounds |
| Post-debate chat | Yes | + Judge Q&A, roster with confidence/weight display |
| Code architecture | Single file | 8 clean modules with documented classes |

---

## Quickstart

### 1. Get a free Groq API key

Go to **[console.groq.com](https://console.groq.com)** → sign up → API Keys → Create.  
Free tier. No credit card.

### 2. Clone and install

```bash
git clone https://github.com/patriq128/Poly_Arena.git
cd Poly_Arena
pip install -r requirements.txt
```

### 3. Set your key and run

```bash
export GROQ_API_KEY=gsk_your_key_here
python3 main.py
```

---

## Requirements

```
groq>=0.9.0
requests>=2.28.0
matplotlib>=3.5.0
colorama>=0.4.6
numpy>=1.21.0
```

```bash
pip install groq requests matplotlib colorama numpy
```

Python **3.8+** required.

---

## Project structure

```
polyarena/
├── main.py              # Terminal UI + menu system (entry point)
├── agents.py            # Agent class, AgentResponse dataclass, agent registry
├── debate_manager.py    # 3-round debate orchestration, human intervention
├── decision_engine.py   # Weighted aggregation + Meta-Agent Judge
├── track_record.py      # Persistent accuracy tracking, leaderboard
├── graphs.py            # 8-panel matplotlib chart generation
├── polymarket.py        # Polymarket API, URL parsing, save/load
├── post_debate_chat.py  # Post-debate interactive chat (agents + judge)
├── requirements.txt
├── LICENSE
├── README.md
├── polyarena_saves/     # Auto-created — markets, debates, track record
└── polyarena_graphs/    # Auto-created — generated PNG charts
```

---

## Architecture deep dive

### Agent class (`agents.py`)

```python
class Agent:
    name:        str
    personality: str
    bias:        float      # 0.0 (strong NO) → 1.0 (strong YES)
    own_history: list       # this agent's past responses this debate
    debate_context: list    # all agents' outputs (shared)
    accuracy:    float      # updated from track record
    weight:      float      # dynamic = accuracy × (0.7 + 0.3 × bias)
```

**Bias mechanics:**
- Acts as a Bayesian prior on the initial vote tendency
- High-bias agents need stronger contrary evidence to flip
- When an agent changes their vote, confidence is penalised proportionally to `abs(bias - 0.5) × 0.4`

**Structured output (`AgentResponse`):**
```json
{
  "vote":       "YES",
  "confidence": 0.74,
  "reasoning":  "Historical halving cycles strongly support a new ATH...",
  "critique":   "VERA-2 assumes market efficiency but ignores retail FOMO effects..."
}
```

Every agent must name another agent by name in their critique. In rounds 2 and 3, they explicitly respond to what others said.

---

### Debate Manager (`debate_manager.py`)

Runs the structured 3-round debate:

| Round | Name | What happens |
|---|---|---|
| 1 | Independent | Each agent gives initial opinion without seeing others |
| 2 | Reactive | Each agent sees all Round-1 outputs, updates + critiques |
| 3 | Final | Each agent sees Round-2 outputs, locks in final position |

After each round, all responses are broadcast to all agents' `debate_context`.

**Human intervention** — if enabled, a prompt appears between rounds letting you inject a statement. It's added to every agent's context as a `HUMAN` entry before the next round begins.

**Model fallback** — if Groq rate-limits or a model fails, automatically falls back:
```
llama-3.3-70b-versatile → llama-3.1-70b-versatile → mixtral-8x7b-32768 → llama3-70b-8192
```

---

### Decision Engine (`decision_engine.py`)

#### Weighted aggregation

Takes each agent's **final round** response and computes:

```python
weighted_yes = sum(confidence × weight  for YES voters)
weighted_no  = sum(confidence × weight  for NO  voters)
final        = "YES" if weighted_yes >= weighted_no else "NO"
confidence   = max(weighted_yes, weighted_no) / (weighted_yes + weighted_no)
```

Where `weight = accuracy × (0.7 + 0.3 × bias)` — agents with better track records get more say.

#### Disagreement score

```python
# +confidence for YES voters, -confidence for NO voters
signed = [+conf if vote=="YES" else -conf for each agent]
disagreement = min(1.0, np.var(signed) × 2)
```

- `0.0` = perfect consensus (everyone voted the same with equal confidence)
- `1.0` = maximum disagreement (agents strongly split, high confidence on both sides)

#### Meta-Agent Judge

JUDGE-PRIME receives the full debate transcript and the panel's preliminary decision, then produces an independent verdict:

```json
{
  "verdict":         "NO",
  "reasoning":       "While AXIOM-1 and DANTE-7 made compelling cyclical arguments...",
  "strongest_agent": "VERA-2",
  "weakest_agent":   "ORION-5"
}
```

The Judge is explicitly instructed it is **not obligated to follow the majority** and should override if the minority made a better case.

---

### Track Record (`track_record.py`)

Stores predictions in `polyarena_saves/track_record.json`:

```json
{
  "AXIOM-1": {
    "predictions": 12,
    "correct":      8,
    "accuracy":  0.667,
    "history": [
      {
        "question":   "Will BTC hit $100k?",
        "market_id":  "abc123",
        "predicted":  "YES",
        "confidence": 0.72,
        "resolved":   "YES",
        "correct":    true,
        "timestamp":  "2026-01-15T10:30:00"
      }
    ]
  }
}
```

**Workflow:**
1. After each debate: `tracker.record_predictions()` logs predictions (unresolved)
2. When a market resolves: `tracker.resolve_market(market_id, "YES"/"NO")`
3. Accuracy recalculates, agent weights update automatically
4. Use the leaderboard view (`[5]` in main menu) to see standings

---

### Graphs (`graphs.py`)

8-panel chart saved to `polyarena_graphs/` and auto-opened:

| Panel | Chart | What it shows |
|---|---|---|
| 1 | AI Consensus Trend | YES% consensus over all 30 steps vs market price |
| 2 | Vote Share | Cumulative YES vs NO as debate progressed |
| 3 | Avg Confidence per Round | Panel mean ± std dev across R1/R2/R3 |
| 4 | Agent Confidence Trajectories | One line per agent across 3 rounds |
| 5 | **Disagreement Heatmap** | Agents × rounds · green=YES · red=NO · intensity=confidence |
| 6 | Per-Agent Final Vote | Stacked bars showing each agent's final vote + confidence |
| 7 | Final Split | Donut chart with judge verdict in center |
| 8 | Weighted Breakdown | Horizontal bars: weighted YES, weighted NO, disagreement score |

The **disagreement heatmap** is the most information-dense panel — it shows at a glance which agents flipped between rounds, who was certain vs uncertain, and where the main fault lines of disagreement were.

---

### Post-Debate Chat (`post_debate_chat.py`)

After every debate, open a Q&A session:

```
  💬  POST-DEBATE CHAT
  Commands:
    1-10 / name  → private multi-turn chat with that agent
    all          → broadcast question to all 10 agents at once
    judge        → Q&A with JUDGE-PRIME
    roster       → agent votes + confidence + weights
    q            → back to menu
```

Each agent's chat uses their full debate transcript, own vote history, and the judge's verdict as context. They can change their mind if you make a compelling argument — their personality and bias shape how likely that is.

---

## The 10 agents

| Agent | Bias | Personality |
|---|---|---|
| **AXIOM-1** | 0.70 | Rational analyst — base rates, data, no vibes |
| **VERA-2** | 0.30 | Contrarian — hunts for mispricing, distrusts consensus |
| **NEXUS-3** | 0.55 | Bayesian — explicit likelihood ratios, shows working |
| **KIRA-4** | 0.40 | Skeptic — doubts narratives, looks for hidden incentives |
| **ORION-5** | 0.65 | Momentum trader — follows trends and smart money |
| **ECHO-6** | 0.50 | Balanced synthesizer — steelmans both sides |
| **DANTE-7** | 0.75 | Fundamentalist — ignores noise, structural forces only |
| **LYRA-8** | 0.25 | Devil's advocate — stress-tests majority positions |
| **SIGMA-9** | 0.60 | Statistician — quantifiable evidence only |
| **ZETA-10** | 0.45 | Philosopher — questions the question itself |

All 10 run on **Llama 3.3 70B via Groq**. Each has a different system prompt. Their dynamic weight starts at `accuracy=0.5` and shifts as they build a track record.

---

## Example output

```
  🔴  DEBATE OPENED
  Will Bitcoin exceed $120k in 2026?
  Market  YES 44.0%  ·  NO 56.0%  ·  Vol $3,800,000

  ── ROUND 1/3 · INDEPENDENT OPINIONS ──

  AXIOM-1    [YES] conf=0.71 [███████░░░]
  ↳ Historical BTC halving cycles show consistent 12-18 month post-halving ATH.
    The 2024 halving puts us squarely in the breakout window.
  ✦ VERA-2 would argue markets have priced this in — but halving scarcity is
    structurally underweighted by futures traders.

  VERA-2     [ NO] conf=0.68 [██████░░░░]
  ↳ Smart money exited Q4 2025. Retail FOMO is not a sustainable price driver
    and ETF inflows have plateaued.
  ✦ AXIOM-1's cycle thesis ignores the macro environment — rate cuts are delayed
    and credit is tighter than in previous cycles.

  ...

  ── DECISION ENGINE COMPUTING... ──
  Weighted YES: 3.241  |  Weighted NO: 4.187
  Raw votes:    13 YES  /  17 NO
  Disagreement score: 0.312 (MODERATE)

  ── META-AGENT JUDGE DELIBERATING... ──
  JUDGE VERDICT: NO
  VERA-2 and KIRA-4 presented the structurally strongest case...
  Strongest argument: VERA-2
  Weakest  argument: ORION-5

  ⚡  FINAL DECISION: NO   confidence=0.564   disagreement=0.312
  ▼ AI MORE BEARISH THAN MARKET
```

---

## Contributing

Pull requests welcome. Ideas:

- **More markets** — Kalshi, Manifold, PredictIt API integration
- **Agent evolution** — personalities that shift over time based on what worked
- **Async debates** — run all 10 agents in parallel per round (much faster)
- **Web UI** — Flask/FastAPI + React frontend
- **Discord bot** — trigger debates via slash commands
- **Export** — PDF debate transcripts, CSV track records
- **Custom agents** — CLI to define new agent personalities and add them to the panel

To contribute:
```bash
git clone https://github.com/yourusername/polyarena.git
cd polyarena
git checkout -b feature/my-feature
# make changes
git commit -m "add: description of change"
git push origin feature/my-feature
# open pull request
```

---

## Links

- 🤖 [Groq Console](https://console.groq.com) — free API key
- 📈 [Polymarket](https://polymarket.com) — prediction markets
- 🦙 [Llama 3.3 70B](https://ai.meta.com/blog/llama-3/) — powers all agents
