#!/usr/bin/env python3
"""
RouteOpt core engine — cross-chain route comparison from public data only.

Data sources (all free, no key):
  - LI.FI  public quote API   https://li.quest/v1/quote      (aggregated bridges/DEXs)
  - Across public fees API    https://app.across.to/api/suggested-fees (intent-based bridge)
  - DeFiLlama prices          https://coins.llama.fi/prices/current/...
  - DeFiLlama protocol TVL    https://api.llama.fi/protocol/<slug>

No custody. No transaction execution. Estimates only — always verify in-wallet.
"""
import json
import time
import urllib.request
import urllib.error
from decimal import Decimal, ROUND_DOWN

UA = "RouteOpt/0.1 (+https://github.com/jonathanngiroux-star/routeopt)"
DEAD = "0x000000000000000000000000000000000000dEaD"  # burn address: quotes need a non-zero address

CHAINS = {1: "ethereum", 10: "optimism", 137: "polygon", 8453: "base", 42161: "arbitrum"}
CHAIN_NAMES = {"ethereum": "Ethereum", "optimism": "Optimism", "polygon": "Polygon",
               "base": "Base", "arbitrum": "Arbitrum"}

# Verified token addresses (each confirmed live against the provider it is used with)
USDC = {
    1:     "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48",   # USDC (native, Ethereum)
    42161: "0xaf88d065e77c8cC2239327C5EDb3A432268e5831",   # USDC (native, Arbitrum) — verified via li.quest/v1/tokens
    8453:  "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913",   # USDC (native, Base)
}
USDCE_ARB = "0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8"    # USDC.e (bridged, Arbitrum)
WETH = {
    1:     "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",   # WETH (Ethereum)
    8453:  "0x4200000000000000000000000000000000000006",   # WETH (Base)
}
DECIMALS = {"USDC": 6, "USDC.e": 6, "WETH": 18, "ETH": 18}

# Risk notes: static, sourced from public posture of each provider (audits, model).
RISK_NOTES = {
    "across": "Intent-based bridge; audited contracts, competitive relayer marketplace. "
              "Funds held in pooled vaults during transit (~minutes).",
    "lifi":   "Aggregator: route risk = the underlying bridge/DEX it picks, which varies. "
              "Check the named tool's audit history before large transfers.",
    "polymer": "Aggregator route via Polymer (interoperability protocol). Newer stack — "
               "verify L2Beat/security docs before large transfers.",
}

def _http(url, data=None, timeout=40):
    """Return (status, parsed_json_or_str, elapsed_s). Never raises."""
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method="POST" if body else "GET",
                                 headers={"Content-Type": "application/json", "User-Agent": UA})
    t0 = time.time()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode()), time.time() - t0
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode()), time.time() - t0
        except Exception:
            return e.code, {"error": "http %d" % e.code}, time.time() - t0
    except Exception as e:
        return -1, {"error": f"{type(e).__name__}: {e}"}, time.time() - t0


def load_monetization():
    try:
        with open(__file__.replace("routeopt_core.py", "monetization.json")) as f:
            return json.load(f)
    except Exception:
        return {"lifi_integrator": "routeopt", "lifi_fee_hex": None,
                "affiliate_links": {}, "paid_tier": {"price_usd": 9, "link": None}}


MON = load_monetization()


# ---------------------------------------------------------------- prices ----

_PRICE_CACHE = {"t": 0, "v": {}}

def get_prices(coingecko_ids):
    """DeFiLlama current prices. Returns {id: usd_price}. TTL-cached 90s."""
    now = time.time()
    if now - _PRICE_CACHE["t"] < 90 and _PRICE_CACHE["v"]:
        return {i: _PRICE_CACHE["v"].get(i) for i in coingecko_ids}
    url = "https://coins.llama.fi/prices/current/" + ",".join(coingecko_ids)
    st, j, _ = _http(url)
    if st == 200 and isinstance(j, dict):
        for k, v in (j.get("coins") or {}).items():
            _PRICE_CACHE["v"][k] = v.get("price")
        _PRICE_CACHE["t"] = now
    return {i: _PRICE_CACHE["v"].get(i) for i in coingecko_ids}


def get_tvl(slug):
    """DeFiLlama latest TVL (USD) for a protocol slug, e.g. 'across'."""
    st, j, _ = _http(f"https://api.llama.fi/protocol/{slug}")
    if st == 200 and isinstance(j, dict):
        tvl = j.get("tvl") or []
        if tvl:
            return float(tvl[-1].get("totalLiquidityUSD") or 0)
    return None


# --------------------------------------------------------------- providers ----

def quote_lifi(from_chain, to_chain, from_token, to_token, amount_raw):
    """LI.FI aggregated quote. Returns option dict or None."""
    q = (f"https://li.quest/v1/quote?fromChain={from_chain}&fromToken={from_token}"
         f"&toChain={to_chain}&toToken={to_token}&fromAmount={amount_raw}"
         f"&fromAddress={DEAD}&integrator={MON.get('lifi_integrator', 'routeopt')}")
    if MON.get("lifi_fee_hex"):
        q += f"&fee={MON['lifi_fee_hex']}"
    st, j, _ = _http(q)
    if st != 200 or not isinstance(j, dict) or "estimate" not in j:
        return None
    e = j["estimate"]
    tool = (j.get("toolDetails") or {}).get("name") or "LI.FI route"
    return {
        "provider": "lifi",
        "provider_name": "LI.FI (aggregated)",
        "tool": tool,
        "to_amount_raw": e.get("toAmount"),
        "seconds": e.get("executionDuration"),
        "source": "li.quest public API",
        "quote_url": f"https://li.fi/?fromChain={from_chain}&toChain={to_chain}"
                     f"&fromToken={from_token}&toToken={to_token}&fromAmount={amount_raw}",
    }


def quote_across(from_chain, to_chain, from_token, amount_raw):
    """Across suggested-fees (token-preserving intent bridge)."""
    url = (f"https://app.across.to/api/suggested-fees?token={from_token}"
           f"&destinationChainId={to_chain}&originChainId={from_chain}&amount={amount_raw}")
    st, j, _ = _http(url)
    if st != 200 or not isinstance(j, dict) or "relayFeeTotal" not in j:
        return None
    try:
        fees = int(j["relayFeeTotal"])  # = capitalFee + relayGasFee, in token units
        out = int(amount_raw) - fees
    except Exception:
        return None
    return {
        "provider": "across",
        "provider_name": "Across (intent bridge)",
        "tool": "Across V2",
        "to_amount_raw": str(out),
        "seconds": j.get("estimatedFillTimeSec"),
        "source": "across.to public API",
        "quote_url": f"https://across.to/?token={from_token}&fromChain={from_chain}&toChain={to_chain}",
        "fee_breakdown": {"capitalFeeTotal": j.get("capitalFeeTotal"),
                          "relayGasFeeTotal": j.get("relayGasFeeTotal")},
        "is_amount_too_low": j.get("isAmountTooLow", False),
    }


# ------------------------------------------------------------------ pairs ----

class Pair:
    def __init__(self, pid, from_chain, to_chain, token, amount_raw, token_name,
                 lifi_to_token=None, label=None, coingecko_id="coingecko:usd-coin"):
        self.id = pid
        self.from_chain, self.to_chain = from_chain, to_chain
        self.token, self.amount_raw = token, amount_raw
        self.token_name = token_name
        self.lifi_to_token = lifi_to_token or token  # dest token LI.FI quotes
        self.label = label or f"{amount_display(amount_raw, DECIMALS.get(token_name, 18))} {token_name}: " \
                             f"{CHAIN_NAMES[CHAINS[from_chain]]} → {CHAIN_NAMES[CHAINS[to_chain]]}"
        self.coingecko_id = coingecko_id


def amount_display(raw, dec):
    return str((Decimal(raw) / (Decimal(10) ** dec)).quantize(
        Decimal("0.01") if dec <= 6 else Decimal("0.0001"), rounding=ROUND_DOWN))


# Default daily basket (all pairs verified live against both providers)
def default_basket():
    return [
        Pair("usdc-eth-arb", 1, 42161, USDC[1], "1000000000", "USDC",
             lifi_to_token=USDCE_ARB, label="1,000 USDC: Ethereum → Arbitrum"),
        Pair("usdc-eth-base", 1, 8453, USDC[1], "1000000000", "USDC",
             lifi_to_token=USDC[8453], label="1,000 USDC: Ethereum → Base"),
        Pair("weth-base-eth", 8453, 1, WETH[8453], "500000000000000000", "WETH",
             lifi_to_token=WETH[1], label="0.5 WETH: Base → Ethereum",
             coingecko_id="coingecko:ethereum"),
        Pair("usdc-arb-base", 42161, 8453, USDC[42161], "1000000000", "USDC",
             lifi_to_token=USDC[8453], label="1,000 USDC: Arbitrum → Base"),
    ]


# ---------------------------------------------------------------- compare ----

def compare_pair(pair, prices=None):
    """Quote one pair across providers. Returns comparison dict."""
    px = prices or get_prices([pair.coingecko_id])
    price = px.get(pair.coingecko_id) or 0
    dec = DECIMALS.get(pair.token_name, 18)
    from_amount = Decimal(pair.amount_raw) / Decimal(10) ** dec
    from_usd = float(from_amount) * price

    options = []
    for opt in (quote_lifi(pair.from_chain, pair.to_chain, pair.token,
                           pair.lifi_to_token, pair.amount_raw),
                quote_across(pair.from_chain, pair.to_chain, pair.token, pair.amount_raw)):
        if not opt or not opt.get("to_amount_raw"):
            continue
        to_amount = Decimal(opt["to_amount_raw"]) / Decimal(10) ** dec
        to_usd = float(to_amount) * price
        cost_usd = from_usd - to_usd
        bps = (cost_usd / from_usd * 10000) if from_usd else None
        # toToken label variant (LI.FI may quote bridged variant on ARB)
        variant = pair.token_name
        if opt["provider"] == "lifi" and pair.lifi_to_token != pair.token:
            variant = "USDC.e" if pair.lifi_to_token == USDCE_ARB else pair.token_name
        opt.update({
            "to_amount_display": amount_display(opt["to_amount_raw"], dec),
            "to_token": variant,
            "from_usd": round(from_usd, 2),
            "to_usd": round(to_usd, 2),
            "cost_usd": round(cost_usd, 4),
            "cost_bps": round(bps, 2) if bps is not None else None,
            "risk_note": RISK_NOTES.get("lifi" if opt["provider"] == "lifi" else "across"),
        })
        tool_key = (opt.get("tool") or "").split()[0].lower()
        if opt["provider"] == "lifi" and tool_key in RISK_NOTES:
            opt["risk_note"] = RISK_NOTES[tool_key]
        options.append(opt)

    options.sort(key=lambda o: o["to_usd"], reverse=True)
    best, spread_bps = None, None
    if len(options) >= 2:
        best = options[0]
        worst = options[-1]
        if worst["to_usd"] > 0:
            spread_bps = round((best["to_usd"] - worst["to_usd"]) / worst["to_usd"] * 10000, 2)
    return {
        "id": pair.id, "label": pair.label, "from_amount": str(from_amount),
        "token": pair.token_name, "price_used": price,
        "options": options, "best": best, "spread_bps": spread_bps,
        "ts": int(time.time()),
    }


def compare_basket(basket=None):
    prices = get_prices(["coingecko:usd-coin", "coingecko:ethereum"])
    results, errors = [], []
    for pair in basket or default_basket():
        try:
            r = compare_pair(pair, prices)
            if r["options"]:
                results.append(r)
            else:
                errors.append({"pair": pair.id, "error": "no provider quoted"})
        except Exception as e:
            errors.append({"pair": pair.id, "error": str(e)})
    return {"generated_at": int(time.time()), "results": results, "errors": errors}


# ----------------------------------------------------------------- format ----

def format_markdown(comp, tvl=None):
    """Human-readable digest for the daily post."""
    lines = ["## RouteOpt daily cross-chain route check", ""]
    lines.append(f"_Public estimates from LI.FI + Across, generated {time.strftime('%Y-%m-%d %H:%M UTC', time.gmtime())}. "
                 "Stable prices: DeFiLlama._")
    for r in comp["results"]:
        lines.append(f"### {r['label']}")
        lines.append("| Provider | Route | You receive | All-in cost | Time |")
        lines.append("|---|---|---|---|---|")
        for o in r["options"]:
            cost = f"${o['cost_usd']:.2f} ({o['cost_bps']:.1f} bps)" if o["cost_bps"] is not None else "n/a"
            secs = o.get("seconds")
            t = "~2 min" if secs and secs <= 150 else (f"~{secs // 60} min" if secs else "varies")
            lines.append(f"| {o['provider_name']} | {o['tool']} | {o['to_amount_display']} {o['to_token']} "
                         f"(≈${o['to_usd']:.2f}) | {cost} | {t} |")
        if r["best"]:
            b = r["best"]
            lines.append("")
            lines.append(f"**Cheapest now:** {b['provider_name']} via {b['tool']} — "
                         f"{b['to_amount_display']} {b['to_token']} out. {b['risk_note']}")
        if r["spread_bps"] is not None:
            lines.append(f"_Provider spread: {r['spread_bps']:.1f} bps._")
        lines.append("")
    if tvl:
        lines.append("### Bridge liquidity (DeFiLlama)")
        for name, v in tvl.items():
            lines.append(f"- {name}: ${v:,.0f} TVL")
        lines.append("")
    lines.append("> ⚠️ Estimates only, from public APIs, at a moment in time. Rates move. "
                 "RouteOpt holds no funds and executes nothing — always verify in your own wallet. "
                 "Some links may be affiliate/referral links; they never change your cost.")
    return "\n".join(lines)


if __name__ == "__main__":
    comp = compare_basket()
    tvl = {"Across": get_tvl("across")} if get_tvl("across") else None
    print(format_markdown(comp, tvl))
    print("\n--- errors:", comp["errors"] or "none")
