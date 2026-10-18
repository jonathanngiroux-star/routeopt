#!/usr/bin/env bash
# Start the RouteOpt Telegram bot in the background (polling; no server needed).
# 1) Create a free bot with @BotFather on Telegram, copy the token.
# 2) export TELEGRAM_BOT_TOKEN="123:abc"        # optional: TELEGRAM_CHANNEL=@your_channel
# 3) ./run_bot.sh
set -euo pipefail
cd "$(dirname "$0")"
[ -n "${TELEGRAM_BOT_TOKEN:-}" ] || { echo "Set TELEGRAM_BOT_TOKEN first (from @BotFather)."; exit 1; }
mkdir -p state
nohup python3 telegram_bot.py >> state/bot.log 2>&1 &
echo "Bot started (pid $!). Log: state/bot.log"
echo "Try it in Telegram: /check 1000 eth arb"
