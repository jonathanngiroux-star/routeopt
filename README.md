# RouteOpt — cheaper cross-chain routes, from public data

**Live site:** https://jonathanngiroux-star.github.io/routeopt/ • Daily free examples: [`site/archive/`](site/archive/)

RouteOpt compares cross-chain transfer routes across public bridge/DEX quote APIs
and shows the cheapest option with cost, speed, and risk trade-offs.

## How it works

| Piece | What it does | Cost |
|---|---|---|
| `routeopt_core.py` | Quote engine: LI.FI (aggregated) vs Across (intent bridge), prices/TVL via DeFiLlama | $0 — public APIs, no key |
| `daily_publish.py` | Daily snapshot → `site/latest.json`, `site/archive/YYYY-MM-DD.md`, regenerates `index.html`; optional Telegram channel cross-post | $0 |
| `telegram_bot.py` | Public `/check <amount> <from> <to>` bot — live quotes in chat | $0 — long polling, stdlib only |
| `site/index.html` | Static checker + published snapshots, hosted free on GitHub Pages | $0 |

Data sources: [LI.FI public API](https://li.quest/v1) (routes/quotes),
[Across public suggested-fees API](https://app.across.to/api), [DeFiLlama](https://defillama.com)
(prices + protocol TVL). All keyless public endpoints.

## Run it

```bash
# one-off comparison digest (prints markdown)
python3 routeopt_core.py

# publish today's snapshot + archive digest
python3 daily_publish.py

# Telegram bot (needs a free bot token from @BotFather)
export TELEGRAM_BOT_TOKEN=...   # optional: TELEGRAM_CHANNEL=@YourChannel for daily cross-post
python3 telegram_bot.py
```

## Automation

A Hermes cron job runs `daily_publish.py` every morning (publishes snapshot +
archive digest; cross-posts to the Telegram channel when `TELEGRAM_BOT_TOKEN` +
`TELEGRAM_CHANNEL` are exported). GitHub Actions could do the same for a fully
GitHub-native setup.

## Monetization ($0 running cost)

- **Free tier:** the site, the `/check` bot command, and the daily archive — free forever.
- **Affiliate/referral links:** provider links on the site and in bot replies
  (`monetization.json`). They never change the user's cost.
- **Alerts+ ($9/mo):** high-frequency checks (15 min, 20+ corridors), private
  Telegram alerts when cheapest-vs-worst spread exceeds your threshold,
  corridor mispricing digest. `/subscribe` in the bot captures leads.

## Disclaimers

Estimates only, from public APIs, at a moment in time. Rates, liquidity and
route availability move constantly. RouteOpt holds no funds, executes no
transactions, and is not financial advice. Always verify the final quote in
your own wallet before signing. Affiliate links never change your cost.

## Automation credentials

`TELEGRAM_BOT_TOKEN` lives in the user's environment or a systemd unit — never in the repo.
