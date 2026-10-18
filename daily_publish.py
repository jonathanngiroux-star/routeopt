#!/usr/bin/env python3
"""
RouteOpt daily publisher.
1. Runs the comparison basket (live public quotes).
2. Writes docs/latest.json (machine-readable snapshot).
3. Writes docs/archive/YYYY-MM-DD.md (daily digest, free public examples).
4. Regenerates docs/index.html with today's snapshot embedded (works offline,
   refreshes live client-side when the visitor interacts).
5. Optionally posts the digest to a Telegram channel if TELEGRAM_BOT_TOKEN
   and TELEGRAM_CHANNEL are set (never required).
"""
import json
import os
import sys
import time
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import routeopt_core as R  # noqa: E402

BASE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(BASE, "docs")


def publish(quiet=False):
    comp = R.compare_basket()
    if not comp["results"]:
        print("No results; aborting publish.", file=sys.stderr)
        return 1

    across_tvl = R.get_tvl("across")
    tvl = {"Across": across_tvl} if across_tvl else None
    md = R.format_markdown(comp, tvl)

    os.makedirs(SITE, exist_ok=True)
    os.makedirs(os.path.join(SITE, "archive"), exist_ok=True)

    # 1) machine-readable snapshot
    with open(os.path.join(SITE, "latest.json"), "w") as f:
        json.dump({"comp": comp, "tvl": tvl, "monetization": R.MON,
                   "generated_at": comp["generated_at"]}, f, indent=1)

    # 2) daily digest into the public archive (free examples)
    day = time.strftime("%Y-%m-%d", time.gmtime())
    with open(os.path.join(SITE, "archive", f"{day}.md"), "w") as f:
        f.write(md)

    # 3) landing page with embedded snapshot
    snapshot = json.dumps({"comp": comp, "tvl": tvl}, separators=(",", ":"))
    html = render_index(snapshot)
    with open(os.path.join(SITE, "index.html"), "w") as f:
        f.write(html)

    if not quiet:
        print(f"Published {day}: {len(comp['results'])} corridors, "
              f"errors={comp['errors'] or 'none'}")

    # 4) optional Telegram channel cross-post (free, only if configured)
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    channel = os.environ.get("TELEGRAM_CHANNEL")
    if token and channel:
        try:
            text = md.replace("## ", "").replace("### ", "* ")
            urllib.request.urlopen(urllib.request.Request(
                f"https://api.telegram.org/bot{token}/sendMessage",
                data=json.dumps({"chat_id": channel, "text": text[:4000]}).encode(),
                headers={"Content-Type": "application/json"}), timeout=30).read()
            if not quiet:
                print("Telegram channel post sent.")
        except Exception as e:
            print(f"Telegram post failed (non-fatal): {e}", file=sys.stderr)
    return 0


def render_index(snapshot_json):
    return """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>RouteOpt — cross-chain route comparison</title>
<meta name="description" content="Free daily cross-chain route comparison from public data (LI.FI, Across, DeFiLlama). No custody, no execution.">
<style>
  :root { color-scheme: light; }
  * { box-sizing: border-box; }
  body { font-family: ui-sans-serif, system-ui, sans-serif; margin: 0; background: #0b1220; color: #e6edf3; }
  .wrap { max-width: 900px; margin: 0 auto; padding: 24px 16px 64px; }
  header { border-bottom: 1px solid #1f2a3a; padding-bottom: 14px; margin-bottom: 18px; }
  h1 { font-size: 1.5rem; margin: 0 0 4px; } h1 span { color: #58a6ff; }
  .tag { color: #8b949e; font-size: .85rem; }
  .card { background: #101a2b; border: 1px solid #1f2a3a; border-radius: 10px; padding: 14px 16px; margin-bottom: 14px; }
  label { font-size: .8rem; color: #8b949e; display: block; margin: 8px 0 2px; }
  select, input { background: #0b1220; border: 1px solid #2a3a52; color: #e6edf3; border-radius: 8px; padding: 8px 10px; font-size: 1rem; width: 100%; }
  .row { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 10px; }
  button { margin-top: 12px; background: #2563eb; color: #fff; border: 0; border-radius: 8px; padding: 10px 16px; font-size: 1rem; cursor: pointer; width: 100%; }
  button:disabled { opacity: .5; cursor: wait; }
  table { width: 100%; border-collapse: collapse; font-size: .9rem; margin-top: 8px; }
  th, td { text-align: left; padding: 7px 8px; border-bottom: 1px solid #1f2a3a; }
  th { color: #8b949e; font-weight: 600; font-size: .75rem; text-transform: uppercase; }
  .best { color: #3fb950; font-weight: 700; }
  .warn { font-size: .78rem; color: #d29922; margin-top: 6px; }
  .muted { color: #8b949e; font-size: .85rem; }
  .pill { display:inline-block; border:1px solid #2a3a52; border-radius:999px; padding:2px 10px; font-size:.72rem; color:#8b949e; margin-right:6px; }
  .cta { display:block; text-align:center; background:#238636; color:#fff; border-radius:8px; padding:10px; text-decoration:none; font-weight:600; margin-top:10px; }
  .cta.blue { background:#2563eb; }
  .arch a { color: #58a6ff; }
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Route<span>Opt</span> — cheaper cross-chain routes</h1>
    <div class="tag">Compares public quote APIs (LI.FI, Across) + prices/TVL (DeFiLlama). Estimates only. No custody. No execution. Not financial advice.</div>
  </header>

  <div class="card">
    <b>Live checker</b> <span class="muted">— quotes fetched in your browser, right now, from the public APIs</span>
    <div class="row">
      <div><label for="from">From chain</label>
        <select id="from">
          <option value="1">Ethereum</option><option value="8453">Base</option>
          <option value="42161">Arbitrum</option><option value="10">Optimism</option>
        </select></div>
      <div><label for="to">To chain</label>
        <select id="to"><option value="42161">Arbitrum</option><option value="1">Ethereum</option>
          <option value="8453">Base</option><option value="10">Optimism</option></select></div>
      <div><label for="amt">Amount (USDC)</label>
        <input id="amt" type="number" value="1000" min="1" step="any"></div>
    </div>
    <button id="go" onclick="check()">Compare routes now</button>
    <div id="out"></div>
  </div>

  <div class="card">
    <b>Today's published snapshot</b> <span class="muted" id="snap-ts"></span>
    <div id="snap"></div>
  </div>

  <div class="card">
    <b>Alerts+</b> — paid tier
    <div class="muted" style="margin-top:6px">High-frequency checks (every 15 min, 20+ corridors), private Telegram alerts when the cheapest-vs-worst provider spread exceeds your threshold, corridor mispricing digest. $9/mo, cancel anytime.</div>
    <a class="cta" href="#" id="ctaLink">Subscribe to RouteOpt Alerts+</a>
  </div>

  <div class="card">
    <b>Move funds</b> <span class="muted">(affiliate/referral links — never change your cost)</span>
    <div style="margin-top:8px">
      <span class="pill" id="affLifi">LI.FI</span><span class="pill" id="affAcross">Across</span>
      <div class="muted" style="margin-top:6px">RouteOpt never touches your funds. You transact on the provider's own site.</div>
    </div>
  </div>

  <div class="card arch">
    <b>Daily archive</b> — free examples published every day: <a href="archive/">archive/</a>.
    <div class="muted">Full methodology, data sources and disclaimers in the <a href="https://github.com/jonathanngiroux-star/routeopt#readme" style="color:#58a6ff">README</a>.</div>
  </div>

  <div class="warn">⚠️ Estimates from public APIs at a moment in time. Rates move. Slippage, capacity caps and route availability change. Always verify the final quote in your wallet before signing. Nothing here is financial advice.</div>
</div>

<script id="snapshot" type="application/json">__SNAPSHOT__</script>
<script>
const TOKENS = {
  "1":     {"USDC": "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48"},
  "42161": {"USDC": "0xaf88d065e77c8cC2239327C5EDb3A432268e5831", "USDC.e": "0xFF970A61A04b1cA14834A43f5dE4533eBDDB5CC8"},
  "8453":  {"USDC": "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"},
  "10":    {"USDC": "0x7f5c7646bc4c5f0e1b4a4c9e0f8d5c5b2e1a3b4c"}
};
const CHAIN = {"1":"Ethereum","10":"Optimism","42161":"Arbitrum","8453":"Base"};

function fmt(n) { return n.toLocaleString("en-US", {maximumFractionDigits: 2}); }
function bps(a, b) { return ((b - a) / b * 10000).toFixed(1); }

async function check() {
  const from = document.getElementById("from").value, to = document.getElementById("to").value;
  const amt = parseFloat(document.getElementById("amt").value);
  const out = document.getElementById("out"), btn = document.getElementById("go");
  if (from === to) { out.innerHTML = "<p class='warn'>Pick two different chains.</p>"; return; }
  if (!(amt > 0) || amt > 1e9) { out.innerHTML = "<p class='warn'>Enter an amount between 0 and 1e9 USDC.</p>"; return; }
  btn.disabled = true; out.innerHTML = "<p class='muted'>Fetching live public quotes…</p>";
  const raw = BigInt(Math.round(amt * 1e6)).toString();
  const results = [];
  const jobs = [];
  // Across
  jobs.push(fetch(`https://app.across.to/api/suggested-fees?token=${TOKENS[from].USDC}&destinationChainId=${to}&originChainId=${from}&amount=${raw}`)
    .then(r => r.json()).then(j => {
      const fee = Number(BigInt(j.relayFeeTotal)), rcv = amt - fee / 1e6;
      results.push({name: "Across (intent bridge)", rcv: rcv, sec: j.estimatedFillTimeSec, url: `https://across.to`});
    }).catch(() => {}));
  // LI.FI (to native USDC when known, else bridged variant on ARB)
  jobs.push((async () => {
    let toTok = TOKENS[to] && TOKENS[to].USDC;
    if (to === "42161") toTok = TOKENS["42161"].USDC;
    const u = `https://li.quest/v1/quote?fromChain=${from}&fromToken=${TOKENS[from].USDC}&toChain=${to}&toToken=${toTok}&fromAmount=${raw}&fromAddress=0x000000000000000000000000000000000000dEaD&integrator=routeopt`;
    const r = await fetch(u);
    if (!r.ok) return;
    const j = await r.json();
    results.push({name: "LI.FI (via " + (j.toolDetails ? j.toolDetails.name : "aggregated") + ")",
                  rcv: Number(j.estimate.toAmount) / 1e6, sec: j.estimate.executionDuration, url: "https://li.fi"});
  })().catch(() => {}));
  await Promise.allSettled(jobs);
  if (!results.length) { out.innerHTML = "<p class='warn'>No provider returned a quote for this corridor right now.</p>"; btn.disabled = false; return; }
  results.sort((a, b) => b.rcv - a.rcv);
  const best = results[0];
  let html = "<table><tr><th>Provider</th><th>You receive (USDC)</th><th>Cost vs best</th><th>Time</th></tr>";
  results.forEach(r => {
    const cost = r === best ? "" : `${fmt(best.rcv - r.rcv)} USDC (${bps(r.rcv, best.rcv)} bps worse)`;
    html += `<tr><td>${r === best ? "<span class='best'>★ " : ""}${r.name}${r === best ? "</span>" : ""}</td><td>${fmt(r.rcv)}</td><td>${cost}</td><td>${r.sec && r.sec <= 150 ? "~" + Math.max(1, r.sec) + "s" : r.sec ? "~" + Math.round(r.sec / 60) + " min" : "varies"}</td></tr>`;
  });
  html += "</table>";
  if (results.length > 1) html += `<p class='muted'>Spread between best and worst: ${bps(results[results.length-1].rcv, best.rcv)} bps. On $${fmt(amt)}, choosing the right provider saves $${fmt(best.rcv - results[results.length-1].rcv)}.</p>`;
  html += `<p class='muted'>Cheapest: <b>${best.name}</b> — open it: <a style="color:#58a6ff" href="${best.url}" target="_blank" rel="noopener">${best.url.replace("https://","")}</a> (verify the final quote there before signing).</p>`;
  out.innerHTML = html;
  btn.disabled = false;
}

// Render published snapshot
(function () {
  let snap = null;
  try { snap = JSON.parse(document.getElementById("snapshot").textContent); } catch (e) { return; }
  document.getElementById("snap-ts").textContent = "— generated " + new Date(snap.comp.generated_at * 1000).toISOString().slice(0,16).replace("T"," ") + " UTC";
  let html = "";
  snap.comp.results.forEach(r => {
    html += `<div style="margin-top:10px"><b>${r.label}</b><table><tr><th>Provider</th><th>Receive</th><th>Cost</th><th>Time</th></tr>`;
    r.options.forEach(o => {
      html += `<tr><td>${o === r.best ? "<span class='best'>★ " : ""}${o.provider_name}${o === r.best ? "</span>" : ""}</td><td>${o.to_amount_display} ${o.to_token}</td><td>$${o.cost_usd.toFixed(2)} (${o.cost_bps} bps)</td><td>${o.seconds ? (o.seconds <= 150 ? "~" + o.seconds + "s" : "~" + Math.round(o.seconds / 60) + " min") : "varies"}</td></tr>`;
    });
    html += "</table>";
    if (r.spread_bps != null) html += `<div class="muted">Provider spread: ${r.spread_bps} bps</div></div>`;
  });
  document.getElementById("snap").innerHTML = html;
  if (snap.tvl) document.getElementById("snap").innerHTML += "<div class='muted' style='margin-top:8px'>Bridge TVL (DeFiLlama): " + Object.entries(snap.tvl).map(([k, v]) => k + " $" + Math.round(v).toLocaleString()).join(", ") + "</div>";
  const mon = snap.monetization;
  if (!mon) return;
  const cta = document.getElementById("ctaLink");
  if (mon.paid_tier && mon.paid_tier.link) cta.href = mon.paid_tier.link;
  const aff = mon.affiliate_links || {};
  if (aff.lifi) document.getElementById("affLifi").outerHTML = `<a class="cta blue" style="margin-top:10px" href="${aff.lifi}" target="_blank" rel="noopener">Route via LI.FI →</a>`;
  if (aff.across) document.getElementById("affAcross").outerHTML = `<a class="cta" style="margin-top:10px" href="${aff.across}" target="_blank" rel="noopener">Route via Across →</a>`;
})();
</script>
</body>
</html>""".replace("__SNAPSHOT__", snapshot_json.replace("</", "<\\/"))


if __name__ == "__main__":
    sys.exit(publish())
