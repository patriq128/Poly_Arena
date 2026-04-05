# POLY⚡ARENA

> **Vibe coded with Claude.** 10 AIs debate Polymarket prediction markets in your terminal — live graphs, save/load, and post-debate chat included.

```
  ██████╗  ██████╗ ██╗  ██╗   ██╗     █████╗ ██████╗ ███████╗███╗   ██╗ █████╗
  ██╔══██╗██╔═══██╗██║  ╚██╗ ██╔╝    ██╔══██╗██╔══██╗██╔════╝████╗  ██║██╔══██╗
  ██████╔╝██║   ██║██║   ╚████╔╝     ███████║██████╔╝█████╗  ██╔██╗ ██║███████║
  ██╔═══╝ ██║   ██║██║    ╚██╔╝      ██╔══██║██╔══██╗██╔══╝  ██║╚██╗██║██╔══██║
  ██║     ╚██████╔╝███████╗██║        ██║  ██║██║  ██║███████╗██║ ╚████║██║  ██║
  ╚═╝      ╚═════╝ ╚══════╝╚═╝        ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═══╝╚═╝  ╚═╝
```

[![Python](https://img.shields.io/badge/Python-3.8+-blue?logo=python&logoColor=white)](https://python.org)
[![Groq](https://img.shields.io/badge/AI-Groq%20%2B%20Llama%203.3%2070B-orange?logo=meta)](https://console.groq.com)
[![Polymarket](https://img.shields.io/badge/Data-Polymarket%20API-purple)](https://polymarket.com)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![Vibe Coded](https://img.shields.io/badge/vibe%20coded-with%20Claude-00ff88)](https://claude.ai)

---

## What is this?

PolyArena is a terminal app that pits **10 AI agents** against each other in structured debates about [Polymarket](https://polymarket.com) prediction markets. You pick a market — paste a URL, browse trending, or load a saved one — and watch 10 differently-opinionated AIs argue YES or NO across 3 rounds, reading each other's arguments before each vote.

After the debate you get:
- 📊 **Live graphs** — consensus trend, YES/NO split, per-agent breakdown, donut chart
- 💾 **Auto-save** — markets and full debate logs saved as JSON
- 💬 **Post-debate chat** — interrogate any of the 10 AIs about why they voted the way they did

All powered by **Groq's free API** running **Llama 3.3 70B**. No credit card. No paid subscription.

---

## Demo

```
  🔴  DEBATE OPENED
  Will Bitcoin exceed $120k in 2026?
  Market  YES 44.0%  ·  NO 56.0%  ·  Vol $3,800,000

  ── ROUND 1/3  [llama-3.3-70b-versatile] ──

  AXIOM-1    [YES]  Historical BTC cycles suggest a new ATH is overdue; the 4-year
                    halving pattern strongly supports a push past $120k.
  VERA-2     [ NO]  The market has already priced in the halving — smart money
                    exited months ago. This rally is retail FOMO, not fundamentals.
  NEXUS-3    [YES]  Updating on AXIOM's cycle data: prior probability shifts to ~60%.
                    Insufficient evidence to override the base rate here.
  KIRA-4     [ NO]  Institutional custody narratives are manufactured hype. Actual
                    on-chain accumulation data doesn't support the bull case.
  ...

  ── ROUND 2/3 ──
  ...

  ⚡  FINAL VERDICT: NO  (13 YES · 17 NO · 57% confidence)
```

---

## Features

| Feature | Details |
|---|---|
| 🤖 **10 AI agents** | Each has a unique personality — contrarian, Bayesian, statistician, philosopher, etc. |
| 🔗 **URL paste** | Paste any `polymarket.com/event/...` URL — auto-extracts the slug, fetches live data |
| 🔥 **Trending markets** | Live fetch of top markets by volume directly from Polymarket's API |
| 💾 **Save / Load** | Markets saved as JSON in `polyarena_saves/`. Debates saved with full logs. |
| 📊 **Graphs** | 4-panel matplotlib chart: consensus trend, YES/NO share, per-agent bars, donut pie |
| 💬 **Post-debate chat** | Multi-turn chat with any agent. Broadcast questions to all 10 at once. |
| 🔄 **Model fallback** | Auto-falls back across 4 Groq models if you hit a rate limit |
| 🎨 **Colorful terminal** | Full ANSI colors, animated spinner, ASCII banner |

---

## Quickstart

### 1. Get a free Groq API key

Go to **[console.groq.com](https://console.groq.com)** → sign up → API Keys → Create key.

No credit card required. Free tier gives you plenty of requests for dozens of debates per day.

### 2. Clone and install

```bash
git clone https://github.com/yourusername/polyarena.git
cd polyarena
pip install -r requirements.txt
```

### 3. Set your API key

```bash
export GROQ_API_KEY=gsk_your_key_here
```

To make it permanent, add that line to your `~/.bashrc` or `~/.zshrc`.

### 4. Run it

```bash
python3 polyarena.py
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

Install all at once:

```bash
pip install groq requests matplotlib colorama numpy
```

Python **3.8+** required.

---

## How it works

### The debate engine

Each debate runs **3 rounds × 10 agents = 30 AI calls** total.

Before each vote, an agent receives:
- The market question and live Polymarket YES/NO price
- The current running vote tally
- The last 8 messages from the debate transcript

This means agents genuinely **read and respond to each other** — VERA-2 will push back on AXIOM-1's argument, LYRA-8 will stress-test whatever position is winning.

Each agent responds with structured JSON:
```json
{"vote": "YES", "reason": "1-2 sentence reasoning citing previous arguments"}
```

### The AI agents

All 10 agents run on **Llama 3.3 70B via Groq** but with different system prompts shaping their reasoning style:

| Agent | Personality |
|---|---|
| **AXIOM-1** | Rational analyst — base rates, historical data, hard statistics |
| **VERA-2** | Contrarian — assumes crowds are systematically wrong |
| **NEXUS-3** | Bayesian — thinks in likelihood ratios, updates incrementally |
| **KIRA-4** | Skeptic — doubts narratives, looks for hidden incentives |
| **ORION-5** | Momentum trader — follows trends and smart money |
| **ECHO-6** | Balanced synthesizer — weighs both sides carefully |
| **DANTE-7** | Fundamentalist — ignores noise, focuses on structural forces |
| **LYRA-8** | Devil's advocate — argues the unpopular side |
| **SIGMA-9** | Statistician — only trusts quantifiable evidence |
| **ZETA-10** | Philosopher — questions the framing of the question itself |

### The consensus signal

After each vote, PolyArena computes a **blended consensus price**:

```
consensus = market_price × 0.65 + (ai_yes_votes / total_votes) × 0.35
```

This shows you whether the AI collective is more bullish or bearish than the live Polymarket price — tracked in real time on the graph.

### Polymarket integration

PolyArena uses Polymarket's public **Gamma API** (no auth required):

```
https://gamma-api.polymarket.com/markets?slug={slug}
https://gamma-api.polymarket.com/markets?closed=false&limit=20&order=volume
```

It auto-extracts the slug from any Polymarket URL format:
- `https://polymarket.com/event/will-bitcoin-hit-100k`
- `https://polymarket.com/market/will-bitcoin-hit-100k`
- `will-bitcoin-hit-100k` (bare slug also works)

---

## File structure

```
polyarena/
├── polyarena.py          # Main script — everything in one file
├── requirements.txt      # Python dependencies
├── README.md             # This file
├── LICENSE               # MIT
├── polyarena_saves/      # Auto-created — saved markets & debates
│   ├── {market_id}.json          # Saved market data
│   └── debate_{id}_{ts}.json     # Full debate logs
└── polyarena_graphs/     # Auto-created — generated PNG charts
    └── debate_{id}_{ts}.png
```

---

## Saved data format

### Market JSON (`polyarena_saves/{id}.json`)
```json
{
  "id": "507583",
  "slug": "will-bitcoin-exceed-120k-in-2026",
  "question": "Will Bitcoin exceed $120k in 2026?",
  "yes_price": 0.44,
  "no_price": 0.56,
  "volume": 3800000.0,
  "url": "https://polymarket.com/event/will-bitcoin-exceed-120k-in-2026",
  "fetched_at": "2026-04-05T14:23:11.042"
}
```

### Debate JSON (`polyarena_saves/debate_{id}_{ts}.json`)
```json
{
  "market": { ... },
  "votes": { "yes": 13, "no": 17 },
  "chart_data": [
    { "step": "Start", "yes_pct": 0, "no_pct": 0, "consensus": 44.0 },
    { "step": "R1·AXIOM", "yes_pct": 100, "no_pct": 0, "consensus": 63.6 },
    ...
  ],
  "debate_log": [
    {
      "round": 1,
      "agent": "AXIOM-1",
      "vote": "YES",
      "reason": "Historical BTC cycles suggest...",
      "running_yes": 1,
      "running_no": 0
    },
    ...
  ],
  "saved_at": "2026-04-05T14:31:44.812"
}
```

---

## Menu walkthrough

```
MAIN MENU
─────────────────────────────────────────────────────────────────────────────────
  [1]  🔗  Paste Polymarket URL  →  auto-fetch ID, data & save
  [2]  🔥  Browse live trending markets
  [3]  📁  My saved markets  →  start a debate
  [4]  📊  Past debate results  →  view graphs
  [5]  🤖  Agent roster
  [q]  Exit
```

**Option 1 — URL paste:** Paste any Polymarket URL. The app extracts the slug, hits the API, shows you the market data (question, ID, slug, YES/NO prices, volume), and lets you save it and/or debate it immediately.

**Option 2 — Trending:** Fetches the top 8 markets by volume live from Polymarket. Pick one to save or debate.

**Option 3 — Saved markets:** Browse your saved markets, pick one to debate, or delete ones you no longer need.

**Option 4 — Past debates:** View a list of all past debate results with their verdicts and timestamps. Pick one to regenerate its graph.

**Option 5 — Roster:** See all 10 agents and their personalities.

---

## Post-debate chat

After every debate you can open a chat session with the AIs:

```
  💬  POST-DEBATE CHAT
  Commands:
    1-10 / name  → private multi-turn chat with that agent
    all          → broadcast your question to all 10 agents at once
    roster       → show agents and their round-by-round votes
    q            → back to menu
```

**Private chat** — full multi-turn conversation with one agent. They remember the entire debate and their own votes. You can challenge their reasoning and they'll push back (or change their mind if you make a good argument).

**Panel mode** (`all`) — ask one question and get a response from all 10 agents in sequence. Great for seeing how differently they interpret the same follow-up question.

---

## Graphs

After every debate, a PNG is saved to `polyarena_graphs/` and auto-opened. The 4-panel chart includes:

1. **AI Consensus YES% over Time** — area chart tracking how the AI signal moved across all 30 votes, with a dashed line showing the live market price
2. **Cumulative YES vs NO Vote Share** — dual area chart showing the running vote split as the debate progressed
3. **Per-Agent Vote Breakdown** — stacked bar chart showing how many YES/NO votes each agent cast across all 3 rounds
4. **Final Split** — donut chart with the final YES/NO percentages and the winning verdict in the center

---

## Groq model fallback

If you hit a rate limit, PolyArena automatically tries the next model:

```
llama-3.3-70b-versatile   ← primary (best)
llama-3.1-70b-versatile   ← fallback 1
mixtral-8x7b-32768        ← fallback 2
llama3-70b-8192           ← fallback 3
```

---

## Contributing

Pull requests welcome. Some ideas if you want to contribute:

- **More agents** — add agents with different personas (macro trader, political analyst, sports bettor)
- **More markets** — support Kalshi, Manifold, or other prediction market APIs
- **Web UI** — a Flask/FastAPI version with a proper frontend
- **Persistent agent memory** — agents remember past debates on the same market
- **Multi-market correlation** — debate whether two related markets are mispriced relative to each other
- **Export** — export debate transcripts to PDF or markdown
- **Discord bot** — run debates triggered by Discord commands

To contribute:
1. Fork the repo
2. Create a branch (`git checkout -b feature/my-feature`)
3. Commit your changes
4. Open a pull request

---

## About

This project was **vibe coded**

The result is a fully working terminal app with a Groq AI backend, live Polymarket API integration, matplotlib graphs, JSON persistence, and a multi-turn post-debate chat system — all in a single Python file.

---


## Links

- 🤖 [Groq Console](https://console.groq.com) — free API key
- 📈 [Polymarket](https://polymarket.com) — prediction markets
- 🦙 [Llama 3.3 70B](https://ai.meta.com/blog/llama-3/) — the model powering all 10 agents
