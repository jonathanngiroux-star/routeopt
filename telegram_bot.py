#!/usr/bin/env python3
"""
RouteOpt Telegram checker bot — $0 serverless-style: long polling, stdlib only.

Commands:
  /check <amount> <FROM> <TO>   live quote comparison, e.g. /check 1000 eth arb
  /routes                       today's published snapshot
  /alerts                       Alerts+ pitch (paid tier)
  /start, /help                 what this is + disclaimers

No custody. No transaction execution. The bot only reads public APIs.
Requires TELEGRAM_BOT_TOKEN env var. Run under systemd --user, tmux, or cron.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import routeopt_core as R  # noqa: E402

TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
API = f"https://api.telegram.org/bot{TOKEN}" if TOKEN else None
OFFSET_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state", "tg_offset")
SUBS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "state", "tg_subs.json")

CHAIN_ALIASES = {
    "eth": 1, "ethereum": 1, "mainnet": 1,
    "arb": 42161, "arbitrum": 42161,
    "base": 8453,
    "op": 10, "optimism": 10, "opmainnet": 10,
}


def tg(method, **params):
    if not API:
        raise RuntimeError("TELEGRAM_BOT_TOKEN not set")
    req = urllib.request.Request(
        f"{API}/{method}",
        data=json.dumps(params).encode(),
        headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=35) as r:
        return json.loads(r.read().decode())


def send(chat_id, text):
    return tg("sendMessage", chat_id=chat_id, text=text,
              parse_mode="Markdown", disable_web_page_preview=True)


def fmt_check(amount, from_c, to_c):
    """Compare one corridor using the engine (USDC corridor)."""
    from_chain = CHAIN_ALIASES[from_c]
    to_chain = CHAIN_ALIASES[to_c]
    if from_chain == to_chain:
        return "Same chain — nothing to bridge. Try e.g. `/check 1000 eth arb`."
    usdc_from = R.USDC.get(from_chain)
    usdc_to = R.USDC.get(to_chain)
    if not usdc_from or not usdc_to:
        return "Supported chains right now: eth, arb, base, op (USDC corridors)."
    raw = str(int(round(amount * 1e6)))
    pair = R.Pair(f"chk-{from_chain}-{to_chain}", from_chain, to_chain, usdc_from, raw, "USDC",
                  lifi_to_token=usdc_to)
    r = R.compare_pair(pair)
    if not r["options"]:
        return "No provider returned a quote for this corridor right now — try again shortly."
    lines = [f"*{amount:g} USDC: {R.CHAIN_NAMES[R.CHAINS[from_chain]]} → {R.CHAIN_NAMES[R.CHAINS[to_chain]]}*",
             f"_{R.CHAIN_NAMES[R.CHAINS[from_chain]]} → {R.CHAIN_NAMES[R.CHAINS[to_chain]]} — live public quotes_", ""]
    for i, o in enumerate(r["options"]):
        star = "★ " if o is r["best"] else ""
        secs = o.get("seconds")
        t = f"~{max(secs,1)}s" if secs and secs <= 150 else (f"~{secs//60} min" if secs else "varies")
        cost = f"${o['cost_usd']:.2f} ({o['cost_bps']:.1f} bps)" if o["cost_bps"] is not None else "n/a"
        lines.append(f"{star}*{o['provider_name']}* via {o['tool']}")
        lines.append(f"  receive `{o['to_amount_display']} {o['to_token']}` ≈ ${o['to_usd']:.2f} | cost {cost} | {t}")
    b = r["best"]
    lines.append("")
    lines.append(f"_Risk note: {b['risk_note']}_")
    if r["spread_bps"] is not None:
        lines.append(f"_Spread between providers: {r['spread_bps']:.1f} bps._")
    lines.append("")
    lines.append("_Estimates only. RouteOpt holds no funds and executes nothing. Verify in your wallet._")
    return "\n".join(lines)


def handle(msg):
    text = (msg.get("text") or "").strip()
    chat = msg.get("chat", {}).get("id")
    if not chat or not text:
        return
    low = text.lower()
    if low.startswith("/start") or low.startswith("/help"):
        send(chat, "RouteOpt compares cross-chain bridge quotes from public data (LI.FI, Across; prices DeFiLlama).\n\n"
                   "*Commands*\n"
                   "`/check <amount> <from> <to>` — live comparison, e.g. `/check 1000 eth arb`\n"
                   "`/routes` — today's published snapshot\n"
                   "`/alerts` — Alerts+ (paid tier) info\n\n"
                   "_No custody. No execution. Estimates only — not financial advice._")
    elif low.startswith("/check"):
        parts = low.split()
        if len(parts) != 4:
            send(chat, "Usage: `/check <amount> <from> <to>` — e.g. `/check 1000 eth arb`\n"
                       "Chains: eth, arb, base, op")
            return
        try:
            amount = float(parts[1])
        except ValueError:
            send(chat, "Amount must be a number, e.g. `/check 1000 eth arb`")
            return
        from_c, to_c = parts[2], parts[3]
        if from_c not in CHAIN_ALIASES or to_c not in CHAIN_ALIASES:
            send(chat, "Unknown chain. Supported: eth, arb, base, op")
            return
        if not (0 < amount <= 1e9):
            send(chat, "Amount must be between 0 and 1e9 USDC.")
            return
        send(chat, fmt_check(amount, from_c, to_c))
    elif low.startswith("/routes"):
        site = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "latest.json")
        try:
            with open(site) as f:
                snap = json.load(f)
            lines = ["*Today's published snapshot*", ""]
            for r in snap["comp"]["results"]:
                b = r["best"]
                secs = b.get("seconds")
                t = f"~{max(secs,1)}s" if secs and secs <= 150 else (f"~{secs//60} min" if secs else "varies")
                lines.append(f"*{r['label']}*\n★ {b['provider_name']} — {b['to_amount_display']} {b['to_token']} "
                             f"(cost ${b['cost_usd']:.2f} / {b['cost_bps']:.1f} bps, {t})")
            lines.append("")
            lines.append(f"_Generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime(snap['comp']['generated_at']))}_")
            lines.append("_Full tables: https://jonathanngiroux-star.github.io/routeopt/_")
            send(chat, "\n".join(lines))
        except FileNotFoundError:
            send(chat, "No snapshot published yet — run daily_publish.py first.")
    elif low.startswith("/alerts"):
        mon = R.MON
        p = mon.get("paid_tier", {})
        inc = "\n".join("• " + i for i in p.get("includes", []))
        link = p.get("link")
        cta = f"\n[Subscribe here]({link})" if link else "\nTo subscribe, message the operator of this bot."
        send(chat, f"*RouteOpt Alerts+* — ${p.get('price_usd')}/{p.get('per')}\n\n{inc}{cta}\n\n"
                   "_Public checks remain free forever._")
    elif low.startswith("/subscribe"):
        # lightweight paid-tier lead capture: records interest in state file
        os.makedirs(os.path.dirname(SUBS_FILE), exist_ok=True)
        subs = []
        try:
            with open(SUBS_FILE) as f:
                subs = json.load(f)
        except FileNotFoundError:
            pass
        entry = {"chat_id": chat, "username": msg.get("from", {}).get("username"),
                 "ts": int(time.time())}
        if not any(s["chat_id"] == chat for s in subs):
            subs.append(entry)
            with open(SUBS_FILE, "w") as f:
                json.dump(subs, f, indent=1)
        link = R.MON.get("paid_tier", {}).get("link")
        send(chat, "Got it — you're on the Alerts+ interest list. The operator will DM payment details."
                   + (f" Or subscribe directly: {link}" if link else ""))
    else:
        send(chat, "Try `/check 1000 eth arb` or /help")


def main(once=False):
    if not TOKEN:
        print("TELEGRAM_BOT_TOKEN not set — bot disabled.", file=sys.stderr)
        return 1
    os.makedirs(os.path.dirname(OFFSET_FILE), exist_ok=True)
    while True:
        try:
            offset = 0
            if os.path.exists(OFFSET_FILE):
                with open(OFFSET_FILE) as f:
                    offset = int(f.read().strip() or 0)
            updates = tg("getUpdates", offset=offset, timeout=25)
            for u in updates.get("result", []):
                offset = max(offset, u["update_id"] + 1)
                try:
                    handle(u["message"])
                except Exception as e:
                    print(f"handler error: {e}", file=sys.stderr)
                    try:
                        send(u["message"]["chat"]["id"], "Something went wrong reading that corridor — try again.")
                    except Exception:
                        pass
            with open(OFFSET_FILE, "w") as f:
                f.write(str(offset))
            if once:
                return 0
            time.sleep(1)
        except KeyboardInterrupt:
            return 0
        except Exception as e:
            print(f"poll error: {e}", file=sys.stderr)
            time.sleep(10)


if __name__ == "__main__":
    sys.exit(main(once="--once" in sys.argv))
