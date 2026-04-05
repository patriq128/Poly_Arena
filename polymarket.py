"""
polymarket.py — Polymarket API integration

Handles:
  - URL slug extraction (any polymarket.com URL format)
  - Market fetch by slug from Gamma API
  - Trending market fetch
  - Market save/load to JSON
"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import requests

SAVE_DIR = Path("polyarena_saves")
SAVE_DIR.mkdir(exist_ok=True)


# ── URL parsing ───────────────────────────────────────────────────────────────
def extract_slug(url: str) -> str:
    """
    Extract market slug from any Polymarket URL.
    Also accepts a bare slug as input.
    """
    url = url.strip()
    for pat in [
        r"polymarket\.com/event/([^/?#\s]+)",
        r"polymarket\.com/market/([^/?#\s]+)",
    ]:
        m = re.search(pat, url)
        if m:
            return m.group(1)
    # bare slug (no dots, no slashes)
    if url and "/" not in url and "." not in url:
        return url
    raise ValueError(
        f"Cannot parse a Polymarket slug from: {url!r}\n"
        f"Expected format: https://polymarket.com/event/some-slug-here"
    )


# ── market data parsing ───────────────────────────────────────────────────────
def _parse_market(raw: dict, slug: str) -> dict:
    """Normalise raw API response into our standard market dict."""
    yes = 0.5
    try:
        prices = json.loads(raw.get("outcomePrices", "[0.5,0.5]"))
        yes    = float(prices[0])
    except Exception:
        pass

    return {
        "id":         str(raw.get("id", slug)),
        "slug":       slug,
        "question":   raw.get("question", slug),
        "yes_price":  round(yes, 4),
        "no_price":   round(1 - yes, 4),
        "volume":     float(raw.get("volume") or 0),
        "url":        f"https://polymarket.com/event/{slug}",
        "fetched_at": datetime.now().isoformat(),
    }


# ── fetch single market by slug ───────────────────────────────────────────────
def fetch_by_slug(slug: str) -> dict:
    """
    Try gamma-api markets then events endpoint.
    Returns normalised market dict or raises ValueError.
    """
    endpoints = [
        f"https://gamma-api.polymarket.com/markets?slug={slug}",
        f"https://gamma-api.polymarket.com/events?slug={slug}",
    ]
    for url in endpoints:
        try:
            r = requests.get(url, headers={"Accept": "application/json"}, timeout=10)
            if r.status_code != 200:
                continue
            data  = r.json()
            items = data if isinstance(data, list) else [data]
            for item in items:
                if item.get("question"):
                    return _parse_market(item, slug)
                # events API nests markets inside
                for sub in item.get("markets", []):
                    if sub.get("question"):
                        return _parse_market(sub, slug)
        except requests.RequestException:
            continue

    raise ValueError(f"No market found for slug '{slug}'. Check the URL and try again.")


# ── fetch trending markets ────────────────────────────────────────────────────
def fetch_trending(n: int = 8) -> list[dict]:
    """Return top-n open markets sorted by volume."""
    try:
        r = requests.get(
            "https://gamma-api.polymarket.com/markets"
            "?closed=false&limit=30&order=volume&ascending=false",
            headers={"Accept": "application/json"},
            timeout=10,
        )
        if r.status_code != 200:
            return []
        results = []
        for item in r.json():
            if item.get("question") and item.get("outcomePrices"):
                results.append(_parse_market(item, item.get("slug", item.get("id", ""))))
            if len(results) >= n:
                break
        return results
    except Exception:
        return []


# ── save / load ───────────────────────────────────────────────────────────────
def save_market(market: dict):
    path = SAVE_DIR / f"{market['id']}.json"
    path.write_text(json.dumps(market, indent=2))

def load_saved_markets() -> list[dict]:
    out = []
    for f in sorted(SAVE_DIR.glob("*.json")):
        if f.name.startswith("debate_") or f.name == "track_record.json":
            continue
        try:
            out.append(json.loads(f.read_text()))
        except Exception:
            pass
    return out

def save_debate_result(market: dict, log: list, result: dict, chart_data: list) -> Path:
    ts   = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = SAVE_DIR / f"debate_{market['id']}_{ts}.json"
    path.write_text(json.dumps({
        "market":     market,
        "result":     result,
        "chart_data": chart_data,
        "debate_log": log,
        "saved_at":   datetime.now().isoformat(),
    }, indent=2))
    return path

def load_past_debates() -> list[tuple[str, dict]]:
    out = []
    for f in sorted(SAVE_DIR.glob("debate_*.json"), reverse=True):
        try:
            out.append((f.name, json.loads(f.read_text())))
        except Exception:
            pass
    return out

def fmt_volume(v: float) -> str:
    if v >= 1e6: return f"${v/1e6:.1f}M"
    if v >= 1e3: return f"${v/1e3:.0f}K"
    return f"${v:.0f}" if v else "$—"
