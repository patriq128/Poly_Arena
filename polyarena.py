#!/usr/bin/env python3
"""
POLY⚡ARENA — Terminal Edition (Groq · FREE)
10-AI Polymarket Debate · Graphs · Save/Load · Post-Debate Chat

Setup:
  1. Free API key → https://console.groq.com  (no credit card)
  2. pip install groq requests matplotlib colorama numpy
  3. export GROQ_API_KEY=gsk_...
  4. python3 polyarena.py
"""

import os, re, sys, json, time, threading, textwrap
from datetime import datetime
from pathlib import Path

MISSING = []
try:    from groq import Groq
except: MISSING.append("groq")
try:    import requests
except: MISSING.append("requests")
try:
    from colorama import Fore, Style, init as _ci; _ci(autoreset=True)
except: MISSING.append("colorama")
try:
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import numpy as np
except: MISSING.append("matplotlib numpy")

if MISSING:
    print(f"\n  Missing: {', '.join(MISSING)}")
    print(f"  Run:  pip install {' '.join(MISSING)}\n")
    sys.exit(1)

# ── dirs ─────────────────────────────────────────────────────────────────────────
SAVE_DIR   = Path("polyarena_saves");  SAVE_DIR.mkdir(exist_ok=True)
GRAPHS_DIR = Path("polyarena_graphs"); GRAPHS_DIR.mkdir(exist_ok=True)

# ── Groq models (best → fallback) ────────────────────────────────────────────────
MODELS = [
    "llama-3.3-70b-versatile",
    "llama-3.1-70b-versatile",
    "mixtral-8x7b-32768",
    "llama3-70b-8192",
]

W = 80

AGENTS = [
    {"id":1,  "name":"AXIOM-1",  "color":Fore.GREEN,           "bias":0.70,
     "p":"Rational analyst. You cite base rates, historical precedents, and hard data. No vibes."},
    {"id":2,  "name":"VERA-2",   "color":Fore.RED,             "bias":0.30,
     "p":"Contrarian. You assume crowds are systematically wrong and hunt for mispricing."},
    {"id":3,  "name":"NEXUS-3",  "color":Fore.BLUE,            "bias":0.55,
     "p":"Bayesian. You think in likelihood ratios. Every argument shifts your probability estimate."},
    {"id":4,  "name":"KIRA-4",   "color":Fore.YELLOW,          "bias":0.40,
     "p":"Skeptic. You doubt official narratives, look for hidden incentives and info asymmetry."},
    {"id":5,  "name":"ORION-5",  "color":Fore.MAGENTA,         "bias":0.65,
     "p":"Momentum trader. Markets trend; crowds are often right. You follow smart money."},
    {"id":6,  "name":"ECHO-6",   "color":Fore.CYAN,            "bias":0.50,
     "p":"Balanced synthesizer. You weigh both sides carefully and acknowledge uncertainty."},
    {"id":7,  "name":"DANTE-7",  "color":Fore.LIGHTYELLOW_EX,  "bias":0.75,
     "p":"Fundamentalist. You ignore noise and focus on structural forces and long-term drivers."},
    {"id":8,  "name":"LYRA-8",   "color":Fore.LIGHTMAGENTA_EX, "bias":0.25,
     "p":"Devil's advocate. You stress-test majority positions and argue the unpopular side."},
    {"id":9,  "name":"SIGMA-9",  "color":Fore.LIGHTGREEN_EX,   "bias":0.60,
     "p":"Statistician. You only trust quantifiable evidence — anecdotes are noise."},
    {"id":10, "name":"ZETA-10",  "color":Fore.LIGHTCYAN_EX,    "bias":0.45,
     "p":"Philosopher. You question the framing of the question and expose hidden assumptions."},
]

# ── terminal helpers ──────────────────────────────────────────────────────────────
def hr(char="─", color=Fore.CYAN):
    print(color + char*W + Style.RESET_ALL)

def header():
    os.system("cls" if os.name=="nt" else "clear")
    print()
    g = Fore.GREEN+Style.BRIGHT
    print(g+"  ██████╗  ██████╗ ██╗  ██╗   ██╗     █████╗ ██████╗ ███████╗███╗   ██╗ █████╗ ")
    print(g+"  ██╔══██╗██╔═══██╗██║  ╚██╗ ██╔╝    ██╔══██╗██╔══██╗██╔════╝████╗  ██║██╔══██╗")
    print(g+"  ██████╔╝██║   ██║██║   ╚████╔╝     ███████║██████╔╝█████╗  ██╔██╗ ██║███████║")
    print(g+"  ██╔═══╝ ██║   ██║██║    ╚██╔╝      ██╔══██║██╔══██╗██╔══╝  ██║╚██╗██║██╔══██║")
    print(g+"  ██║     ╚██████╔╝███████╗██║        ██║  ██║██║  ██║███████╗██║ ╚████║██║  ██║")
    print(g+"  ╚═╝      ╚═════╝ ╚══════╝╚═╝        ╚═╝  ╚═╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═══╝╚═╝  ╚═╝"+Style.RESET_ALL)
    print(Fore.CYAN+"  "+"─"*76+Style.RESET_ALL)
    print(Fore.WHITE+"  ⚡  Groq · Llama 3.3 70B (FREE) · 10 AIs · Debates · Graphs · Chat  ⚡"+Style.RESET_ALL)
    print(Fore.CYAN+"  "+"─"*76+Style.RESET_ALL)
    print()

def cp(text, color=Fore.WHITE, end="\n"):
    print(color+text+Style.RESET_ALL, end=end)

def ask(text, color=Fore.CYAN):
    return input(color+text+Style.RESET_ALL)

def spin(msg):
    stop = threading.Event()
    fr   = ["⠋","⠙","⠹","⠸","⠼","⠴","⠦","⠧","⠇","⠏"]
    def _run():
        i=0
        while not stop.is_set():
            sys.stdout.write(f"\r{Fore.CYAN}{fr[i%10]} {msg}{Style.RESET_ALL}   ")
            sys.stdout.flush(); time.sleep(0.08); i+=1
        sys.stdout.write("\r"+" "*(len(msg)+12)+"\r"); sys.stdout.flush()
    threading.Thread(target=_run,daemon=True).start()
    return stop

def unspin(s): s.set(); time.sleep(0.12)

# ── Groq client ───────────────────────────────────────────────────────────────────
def get_client():
    key = os.environ.get("GROQ_API_KEY","").strip()
    if not key:
        header()
        cp("  ✗  GROQ_API_KEY not set!", Fore.RED+Style.BRIGHT)
        cp("  1.  Go to https://console.groq.com  (free, no card needed)", Fore.YELLOW)
        cp("  2.  Create an API key", Fore.YELLOW)
        cp("  3.  export GROQ_API_KEY=gsk_...   then re-run", Fore.YELLOW)
        print()
        key = ask("  Or paste your key now: ").strip()
        if not key: sys.exit(1)
        os.environ["GROQ_API_KEY"] = key
    return Groq(api_key=key)

def groq_call(client, system, user, history=None):
    msgs = [{"role":"system","content":system}]
    if history: msgs.extend(history)
    msgs.append({"role":"user","content":user})
    for model in MODELS:
        try:
            r = client.chat.completions.create(
                model=model, messages=msgs,
                max_tokens=512, temperature=0.85)
            return r.choices[0].message.content.strip(), model
        except Exception as e:
            if "rate" in str(e).lower(): time.sleep(2)
            continue
    return "Error: all models failed.", MODELS[-1]

# ── Polymarket ────────────────────────────────────────────────────────────────────
def extract_slug(url):
    url = url.strip()
    for pat in [r"polymarket\.com/event/([^/?#\s]+)",
                r"polymarket\.com/market/([^/?#\s]+)"]:
        m = re.search(pat,url)
        if m: return m.group(1)
    if url and "/" not in url and "." not in url: return url
    raise ValueError(f"Cannot parse slug from: {url!r}")

def parse_mkt(m, slug):
    y=0.5
    try: y=float(json.loads(m.get("outcomePrices","[0.5]"))[0])
    except: pass
    return {"id":str(m.get("id",slug)),"slug":slug,"question":m.get("question",slug),
            "yes_price":round(y,4),"no_price":round(1-y,4),
            "volume":float(m.get("volume") or 0),
            "url":f"https://polymarket.com/event/{slug}",
            "fetched_at":datetime.now().isoformat()}

def fetch_slug(slug):
    for url in [f"https://gamma-api.polymarket.com/markets?slug={slug}",
                f"https://gamma-api.polymarket.com/events?slug={slug}"]:
        try:
            r=requests.get(url,headers={"Accept":"application/json"},timeout=10)
            if r.status_code!=200: continue
            data=r.json(); items=data if isinstance(data,list) else [data]
            for item in items:
                if item.get("question"): return parse_mkt(item,slug)
                for sub in item.get("markets",[]): 
                    if sub.get("question"): return parse_mkt(sub,slug)
        except: continue
    raise ValueError(f"No market found for slug '{slug}'")

def fetch_trending(n=8):
    try:
        r=requests.get("https://gamma-api.polymarket.com/markets?closed=false&limit=20&order=volume&ascending=false",
                       headers={"Accept":"application/json"},timeout=10)
        if r.status_code!=200: return []
        out=[]
        for m in r.json():
            if m.get("question") and m.get("outcomePrices"):
                out.append(parse_mkt(m,m.get("slug",m.get("id",""))))
            if len(out)>=n: break
        return out
    except: return []

# ── persistence ───────────────────────────────────────────────────────────────────
def save_market(m):
    p=SAVE_DIR/f"{m['id']}.json"
    json.dump(m,open(p,"w"),indent=2)
    cp(f"  ✓ Saved → {p}", Fore.GREEN)

def save_debate(m,log,votes,chart):
    ts=datetime.now().strftime("%Y%m%d_%H%M%S")
    p=SAVE_DIR/f"debate_{m['id']}_{ts}.json"
    json.dump({"market":m,"votes":votes,"chart_data":chart,"debate_log":log,
               "saved_at":datetime.now().isoformat()},open(p,"w"),indent=2)
    cp(f"  ✓ Debate saved → {p}", Fore.GREEN)

def load_markets():
    out=[]
    for f in sorted(SAVE_DIR.glob("*.json")):
        if f.name.startswith("debate_"): continue
        try: out.append(json.load(open(f)))
        except: pass
    return out

def load_debates():
    out=[]
    for f in sorted(SAVE_DIR.glob("debate_*.json"),reverse=True):
        try: out.append((f.name,json.load(open(f))))
        except: pass
    return out

# ── debate engine ─────────────────────────────────────────────────────────────────
def run_debate(client, market):
    q=market["question"]; yp=market["yes_price"]
    votes={"yes":0,"no":0}; log=[]; hist=[]; model="?"
    chart=[{"step":"Start","yes_pct":0,"no_pct":0,"consensus":round(yp*100,1)}]

    cp(f"\n  🔴  DEBATE OPENED", Fore.RED+Style.BRIGHT)
    cp(f"  {q}", Fore.WHITE+Style.BRIGHT)
    cp(f"  Market  YES {yp*100:.1f}%  ·  NO {(1-yp)*100:.1f}%  ·  Vol ${market['volume']:,.0f}", Fore.CYAN)
    hr()

    for rnd in range(1,4):
        hr("·",Fore.CYAN)
        cp(f"  ── ROUND {rnd}/3  [{model}] ──", Fore.CYAN+Style.BRIGHT)
        hr("·",Fore.CYAN)

        for ag in AGENTS:
            name=ag["name"]; total=votes["yes"]+votes["no"]
            ctx="\n".join(hist[-8:]) if hist else "(You are first to speak.)"

            sys_p=(f"You are {name}, an AI prediction market analyst.\n"
                   f"Personality: {ag['p']}\n"
                   f"You debate with 9 other AIs. Be direct and concise.\n"
                   f"Respond ONLY with valid JSON — no markdown, nothing outside the JSON.")
            user_p=(f'Question: "{q}"\n'
                    f"Live YES price: {yp*100:.1f}%\n"
                    f"Votes so far: YES={votes['yes']} NO={votes['no']} ({total} total)\n\n"
                    f"Recent debate:\n{ctx}\n\n"
                    f'Reply: {{"vote":"YES","reason":"1-2 sentences"}} '
                    f'or {{"vote":"NO","reason":"1-2 sentences"}}')

            s=spin(f"{name} thinking...")
            try:
                raw,model=groq_call(client,sys_p,user_p)
                raw=re.sub(r"```[a-z]*","",raw).strip().strip("`")
                m2=re.search(r'\{.*?"vote".*?\}',raw,re.DOTALL)
                raw=m2.group(0) if m2 else raw
                p2=json.loads(raw)
                vote="YES" if str(p2.get("vote","")).upper()=="YES" else "NO"
                reason=str(p2.get("reason","No reason.")).strip()
            except:
                vote="YES" if ag["bias"]>0.5 else "NO"
                reason="Parse error — defaulting to prior."
            unspin(s)

            if vote=="YES": votes["yes"]+=1
            else:           votes["no"]+=1
            total=votes["yes"]+votes["no"]
            cons=yp*0.65+(votes["yes"]/total)*0.35

            chart.append({"step":f"R{rnd}·{name.split('-')[0]}",
                          "yes_pct":round(votes["yes"]/total*100,1),
                          "no_pct":round(votes["no"]/total*100,1),
                          "consensus":round(cons*100,1)})
            log.append({"round":rnd,"agent":name,"vote":vote,"reason":reason,
                        "running_yes":votes["yes"],"running_no":votes["no"]})
            hist.append(f"{name}: [{vote}] {reason}")

            vc=Fore.GREEN if vote=="YES" else Fore.RED
            print(f"  {ag['color']}{name:<10}{Style.RESET_ALL} [{vc}{vote:>3}{Style.RESET_ALL}]  ",end="")
            lines=textwrap.wrap(reason,56)
            print(lines[0] if lines else "")
            for l in lines[1:]: print(" "*18+l)

    hr()
    winner="YES" if votes["yes"]>votes["no"] else ("NO" if votes["no"]>votes["yes"] else "TIE")
    wc=Fore.GREEN if winner=="YES" else (Fore.RED if winner=="NO" else Fore.YELLOW)
    total=votes["yes"]+votes["no"]
    pct=round(max(votes["yes"],votes["no"])/total*100)
    cp(f"\n  ⚡  FINAL VERDICT: ",Fore.WHITE+Style.BRIGHT,end="")
    cp(f"{winner}  ({votes['yes']} YES · {votes['no']} NO · {pct}% confidence)",wc+Style.BRIGHT)
    print()
    return log,votes,chart

# ── graphs ────────────────────────────────────────────────────────────────────────
def make_graphs(market,log,votes,chart):
    q=market["question"]
    ts=datetime.now().strftime("%Y%m%d_%H%M%S")
    path=GRAPHS_DIR/f"debate_{market['id']}_{ts}.png"
    BG,PAN="#050a0f","#040c14"

    steps=[d["step"] for d in chart]
    ypcts=[d["yes_pct"] for d in chart]
    npcts=[d["no_pct"] for d in chart]
    cons =[d["consensus"] for d in chart]
    x=list(range(len(steps)))
    ti=x[::max(1,len(x)//10)]

    fig,axes=plt.subplots(2,2,figsize=(14,9))
    fig.patch.set_facecolor(BG)
    for ax in axes.flat:
        ax.set_facecolor(PAN)
        ax.tick_params(colors="#406080",labelsize=7)
        for sp in ax.spines.values(): sp.set_edgecolor("#0a2030")
        ax.title.set_color("#c8d8e8")
    fig.suptitle(textwrap.fill(f"POLY⚡ARENA — {q}",90),
                 color="#00ff88",fontsize=10,fontweight="bold",y=0.99)

    def xt(ax):
        ax.set_xticks(ti)
        ax.set_xticklabels([steps[i] for i in ti],rotation=45,ha="right",fontsize=6)

    # 1 consensus
    ax=axes[0,0]; ax.set_title("AI Consensus YES% over Time",fontsize=9)
    ax.fill_between(x,cons,alpha=0.2,color="#00ff88")
    ax.plot(x,cons,color="#00ff88",lw=2,label="AI Consensus")
    ax.axhline(market["yes_price"]*100,color="#4488ff",ls="--",lw=1.2,
               label=f"Market {market['yes_price']*100:.1f}%")
    ax.set_ylim(0,100); ax.set_ylabel("YES %",color="#406080",fontsize=8)
    ax.legend(fontsize=7,facecolor=BG,edgecolor="#0a2030",labelcolor="#c8d8e8"); xt(ax)

    # 2 yes vs no
    ax=axes[0,1]; ax.set_title("Cumulative YES vs NO Vote Share",fontsize=9)
    ax.fill_between(x,ypcts,alpha=0.25,color="#00ff88")
    ax.fill_between(x,npcts,alpha=0.25,color="#ff4466")
    ax.plot(x,ypcts,color="#00ff88",lw=2,label="YES%")
    ax.plot(x,npcts,color="#ff4466",lw=2,label="NO%")
    ax.set_ylim(0,100); ax.set_ylabel("Vote Share %",color="#406080",fontsize=8)
    ax.legend(fontsize=7,facecolor=BG,edgecolor="#0a2030",labelcolor="#c8d8e8"); xt(ax)

    # 3 per-agent
    ax=axes[1,0]; ax.set_title("Per-Agent Vote Breakdown",fontsize=9)
    anames=[a["name"].split("-")[0] for a in AGENTS]
    yc=[sum(1 for e in log if e["agent"]==a["name"] and e["vote"]=="YES") for a in AGENTS]
    nc=[sum(1 for e in log if e["agent"]==a["name"] and e["vote"]=="NO")  for a in AGENTS]
    bx=np.arange(len(anames))
    ax.bar(bx,yc,color="#00ff88",alpha=0.85,label="YES")
    ax.bar(bx,nc,bottom=yc,color="#ff4466",alpha=0.85,label="NO")
    ax.set_xticks(bx); ax.set_xticklabels(anames,rotation=45,ha="right",fontsize=7)
    ax.set_ylabel("Votes",color="#406080",fontsize=8)
    ax.legend(fontsize=7,facecolor=BG,edgecolor="#0a2030",labelcolor="#c8d8e8")

    # 4 donut
    ax=axes[1,1]; ax.set_title("Final Split",fontsize=9)
    sizes=[max(votes["yes"],0.01),max(votes["no"],0.01)]
    wedges,texts,autos=ax.pie(sizes,
        labels=[f"YES  {votes['yes']}",f"NO  {votes['no']}"],
        colors=["#00ff88","#ff4466"],autopct="%1.1f%%",startangle=90,
        pctdistance=0.78,wedgeprops={"edgecolor":BG,"linewidth":2})
    for t in texts:  t.set_color("#c8d8e8"); t.set_fontsize(9)
    for a in autos:  a.set_color(BG); a.set_fontweight("bold"); a.set_fontsize(9)
    ax.add_patch(plt.Circle((0,0),0.55,fc=PAN))
    winner="YES" if votes["yes"]>=votes["no"] else "NO"
    ax.text(0,0,winner,ha="center",va="center",fontsize=22,fontweight="bold",
            color="#00ff88" if winner=="YES" else "#ff4466")

    plt.tight_layout(rect=[0,0,1,0.97])
    plt.savefig(path,dpi=130,bbox_inches="tight",facecolor=BG)
    plt.close()
    return str(path)

def open_file(p):
    try:
        if sys.platform=="darwin":              os.system(f"open '{p}'")
        elif sys.platform.startswith("linux"):  os.system(f"xdg-open '{p}'")
        elif sys.platform=="win32":             os.startfile(p)
    except: pass

# ── post-debate chat ──────────────────────────────────────────────────────────────
def chat(client, market, log, votes):
    q=market["question"]
    winner="YES" if votes["yes"]>votes["no"] else ("NO" if votes["no"]>votes["yes"] else "TIE")
    summary="\n".join(f"  R{e['round']} {e['agent']:10} [{e['vote']}] {e['reason']}" for e in log)
    amap={}
    for a in AGENTS:
        amap[str(a["id"])]=a; amap[a["name"].lower()]=a
        amap[a["name"].split("-")[0].lower()]=a

    header()
    cp("  💬  POST-DEBATE CHAT", Fore.CYAN+Style.BRIGHT); hr()
    cp("  Commands:", Fore.YELLOW)
    cp("    1-10 / name  → private multi-turn chat with that agent", Fore.YELLOW)
    cp("    all          → broadcast your question to all 10 agents at once", Fore.YELLOW)
    cp("    roster       → show agents and their round-by-round votes", Fore.YELLOW)
    cp("    q            → back to menu", Fore.YELLOW)
    hr()

    while True:
        print()
        c=ask("  Talk to (number/name/all/q): ").strip().lower()
        if c in ("q","quit","b","back"): break

        if c=="roster":
            hr()
            for a in AGENTS:
                ev=[e for e in log if e["agent"]==a["name"]]
                vs="  ".join((Fore.GREEN if e["vote"]=="YES" else Fore.RED)+e["vote"]+Style.RESET_ALL for e in ev)
                print(f"  {a['color']}{a['name']:<12}{Style.RESET_ALL}  {vs or '—'}")
            hr(); continue

        if c=="all":
            q2=ask("  Your question to all agents: ").strip()
            if not q2: continue
            cp("\n  ── ALL-AGENT PANEL ──", Fore.CYAN+Style.BRIGHT)
            for ag in AGENTS:
                sysp=(f"You are {ag['name']}. Personality: {ag['p']}\n"
                      f'You debated: "{q}"\n'
                      f"Result: {winner} ({votes['yes']} YES vs {votes['no']} NO)\n"
                      f"Your votes: {[e for e in log if e['agent']==ag['name']]}\n"
                      f"Full debate:\n{summary}\n"
                      f"Answer in 2-3 sentences. Stay in character.")
                s=spin(f"{ag['name']} responding...")
                try: reply,_=groq_call(client,sysp,q2)
                except Exception as e: reply=f"[Error: {e}]"
                unspin(s)
                pad="  "+" "*(len(ag["name"])+4)
                print(f"\n  {ag['color']}{ag['name']}{Style.RESET_ALL} → ",end="")
                lines=textwrap.wrap(reply,62)
                print(lines[0] if lines else "")
                for l in lines[1:]: print(pad+l)
            print(); continue

        ag=amap.get(c)
        if not ag:
            cp(f"  Unknown: '{c}'. Try 1-10, a name, 'all', or 'q'.", Fore.RED); continue

        aentries=[e for e in log if e["agent"]==ag["name"]]
        sysp=(f"You are {ag['name']}, an AI prediction market analyst.\n"
              f"Personality: {ag['p']}\n\n"
              f'You just debated: "{q}"\n'
              f"Final verdict: {winner} ({votes['yes']} YES vs {votes['no']} NO)\n"
              f"Your votes this debate:\n"
              +"\n".join(f"  Round {e['round']}: {e['vote']} — {e['reason']}" for e in aentries)
              +f"\n\nFull transcript:\n{summary}\n\n"
              f"You are in a post-debate Q&A. Be direct and stay in character. "
              f"Max 3-4 sentences. You can change your mind if the human makes a good point.")
        hist=[]
        cp(f"\n  ── Chatting with {ag['name']} ── ('switch' to change agent)",ag["color"])
        vs_str="  ".join((Fore.GREEN if e["vote"]=="YES" else Fore.RED)+e["vote"]+Style.RESET_ALL for e in aentries)
        cp(f"  Their votes: {vs_str}",Fore.WHITE); print()

        while True:
            um=ask(f"  You → {ag['name']}: ").strip()
            if not um or um.lower() in ("switch","back","b"): break
            hist.append({"role":"user","content":um})
            s=spin(f"{ag['name']} thinking...")
            try:
                resp=client.chat.completions.create(
                    model=MODELS[0],
                    messages=[{"role":"system","content":sysp}]+hist,
                    max_tokens=400,temperature=0.85)
                reply=resp.choices[0].message.content.strip()
            except Exception as e: reply=f"[Error: {e}]"
            unspin(s)
            hist.append({"role":"assistant","content":reply})
            pad="  "+" "*(len(ag["name"])+4)
            print(f"\n  {ag['color']}{ag['name']}{Style.RESET_ALL} → ",end="")
            lines=textwrap.wrap(reply,62)
            print(lines[0] if lines else "")
            for l in lines[1:]: print(pad+l)
            print()

# ── debate flow ───────────────────────────────────────────────────────────────────
def debate_flow(client,market):
    header()
    cp(f"  📋  {market['question']}",Fore.WHITE+Style.BRIGHT); hr()
    log,votes,chart=run_debate(client,market)
    cp("  Generating graphs...",Fore.CYAN)
    gp=make_graphs(market,log,votes,chart)
    cp(f"  ✓ Graph → {gp}",Fore.GREEN); open_file(gp)
    save_debate(market,log,votes,chart)
    hr()
    cp("  What next?",Fore.CYAN+Style.BRIGHT)
    a=ask("  [c] Chat with AIs  [r] Re-debate  [b] Main menu: ").strip().lower()
    if a=="c": chat(client,market,log,votes)
    elif a=="r": debate_flow(client,market)

# ── menus ─────────────────────────────────────────────────────────────────────────
def menu_url(client):
    header()
    cp("  🔗  PASTE POLYMARKET URL",Fore.CYAN+Style.BRIGHT); hr()
    cp("  Paste a full URL or just the slug:",Fore.WHITE)
    cp("    https://polymarket.com/event/will-bitcoin-hit-100k",Fore.YELLOW)
    cp("    will-bitcoin-hit-100k  ← slug only also works",Fore.YELLOW); hr()
    url=ask("  URL or slug: ").strip()
    if not url: return
    s=spin("Fetching market from Polymarket API...")
    try:
        slug=extract_slug(url); market=fetch_slug(slug); unspin(s)
    except Exception as e:
        unspin(s); cp(f"\n  ✗  {e}",Fore.RED); ask("  Enter to continue..."); return
    hr()
    cp("  ✓  Market found!",Fore.GREEN+Style.BRIGHT)
    cp(f"  Question : {market['question']}",Fore.WHITE)
    cp(f"  ID       : {market['id']}",Fore.CYAN)
    cp(f"  Slug     : {market['slug']}",Fore.CYAN)
    cp(f"  YES      : {market['yes_price']*100:.1f}%",Fore.GREEN)
    cp(f"  NO       : {market['no_price']*100:.1f}%",Fore.RED)
    cp(f"  Volume   : ${market['volume']:,.0f}",Fore.YELLOW)
    cp(f"  URL      : {market['url']}",Fore.CYAN); hr()
    a=ask("  [s] Save  [d] Debate  [sd] Save & Debate  [b] Back: ").strip().lower()
    if a in ("s","sd"): save_market(market); time.sleep(0.5)
    if a in ("d","sd"): debate_flow(client,market)

def menu_trending(client):
    header()
    cp("  🔥  TRENDING MARKETS  (live from Polymarket)",Fore.CYAN+Style.BRIGHT); hr()
    s=spin("Fetching top markets by volume...")
    mkts=fetch_trending(8); unspin(s)
    if not mkts:
        cp("  Could not reach Polymarket API.",Fore.RED); ask("  Enter..."); return
    for i,m in enumerate(mkts,1):
        cp(f"  [{i}] YES {m['yes_price']*100:5.1f}%  ${m['volume']:>12,.0f}  {m['question'][:48]}",Fore.WHITE)
    hr()
    c=ask("  Pick number (or b): ").strip().lower()
    if c=="b": return
    try:
        market=mkts[int(c)-1]
        a=ask("  [s] Save  [d] Debate  [sd] Save & Debate  [b]: ").strip().lower()
        if a in ("s","sd"): save_market(market); time.sleep(0.5)
        if a in ("d","sd"): debate_flow(client,market)
    except (ValueError,IndexError): cp("  Invalid.",Fore.RED); time.sleep(0.8)

def menu_saved(client):
    while True:
        header()
        cp("  📁  SAVED MARKETS",Fore.CYAN+Style.BRIGHT); hr()
        mkts=load_markets()
        if not mkts:
            cp("  No saved markets yet.",Fore.YELLOW); ask("  Enter..."); return
        for i,m in enumerate(mkts,1):
            cp(f"  [{i}] YES {m['yes_price']*100:5.1f}%  ${m['volume']:>10,.0f}  {m['question'][:50]}",Fore.WHITE)
        cp("  [d] Delete  [b] Back",Fore.YELLOW); hr()
        c=ask("  Pick to debate / action: ").strip().lower()
        if c=="b": return
        if c=="d":
            idx=ask("  Number to delete: ").strip()
            try:
                m=mkts[int(idx)-1]; (SAVE_DIR/f"{m['id']}.json").unlink(missing_ok=True)
                cp("  ✓ Deleted.",Fore.GREEN); time.sleep(0.8)
            except: cp("  Invalid.",Fore.RED); time.sleep(0.8)
            continue
        try: debate_flow(client,mkts[int(c)-1]); return
        except (ValueError,IndexError): cp("  Invalid.",Fore.RED); time.sleep(0.8)

def menu_past():
    header()
    cp("  📊  PAST DEBATE RESULTS",Fore.CYAN+Style.BRIGHT); hr()
    results=load_debates()
    if not results:
        cp("  No past debates saved yet.",Fore.YELLOW); ask("  Enter..."); return
    for i,(fname,data) in enumerate(results[:12],1):
        m=data.get("market",{}); v=data.get("votes",{})
        w="YES" if v.get("yes",0)>v.get("no",0) else "NO"
        wc=Fore.GREEN if w=="YES" else Fore.RED
        ts=data.get("saved_at","")[:16]
        cp(f"  [{i}] {ts}  {wc}{w}{Style.RESET_ALL}  {m.get('question','?')[:46]}",Fore.WHITE)
    hr()
    c=ask("  Pick to view graph  /  b: ").strip().lower()
    if c=="b": return
    try:
        _,data=results[int(c)-1]
        cp("\n  Regenerating graph...",Fore.CYAN)
        gp=make_graphs(data["market"],data["debate_log"],data["votes"],data["chart_data"])
        cp(f"  ✓ Graph → {gp}",Fore.GREEN); open_file(gp)
    except (ValueError,IndexError): cp("  Invalid.",Fore.RED)
    ask("  Enter to continue...")

def menu_roster():
    header()
    cp("  🤖  AI AGENT ROSTER",Fore.CYAN+Style.BRIGHT); hr()
    for a in AGENTS:
        print(f"  {a['color']}{a['name']:<12}{Style.RESET_ALL}  bias={a['bias']:.0%}  {a['p'][:58]}")
    hr()
    cp("  All 10 agents run on llama-3.3-70b-versatile via Groq's FREE tier.",Fore.YELLOW)
    cp("  Each has a unique system prompt shaping its reasoning style.",Fore.YELLOW)
    cp("  They read each other's arguments before voting each round.",Fore.YELLOW)
    cp("  Get your free key at:  https://console.groq.com",Fore.YELLOW)
    hr(); ask("  Enter to continue...")

# ── main ──────────────────────────────────────────────────────────────────────────
def main():
    client=get_client()
    while True:
        header()
        cp("  MAIN MENU",Fore.CYAN+Style.BRIGHT); hr()
        cp("  [1]  🔗  Paste Polymarket URL  →  auto-fetch ID, data & save",Fore.WHITE)
        cp("  [2]  🔥  Browse live trending markets",Fore.WHITE)
        cp("  [3]  📁  My saved markets  →  start a debate",Fore.WHITE)
        cp("  [4]  📊  Past debate results  →  view graphs",Fore.WHITE)
        cp("  [5]  🤖  Agent roster",Fore.WHITE)
        cp("  [q]  Exit",Fore.WHITE); hr()
        cp(f"  AI: {MODELS[0]}  ·  Provider: Groq (free)  ·  https://console.groq.com",Fore.CYAN)
        hr()
        c=ask("  Choice: ").strip().lower()
        if   c=="1": menu_url(client)
        elif c=="2": menu_trending(client)
        elif c=="3": menu_saved(client)
        elif c=="4": menu_past()
        elif c=="5": menu_roster()
        elif c in ("q","quit","exit"):
            cp("\n  👋  Goodbye!\n",Fore.GREEN+Style.BRIGHT); sys.exit(0)
        else: cp("  Unknown option.",Fore.RED); time.sleep(0.6)

if __name__=="__main__":
    main()
