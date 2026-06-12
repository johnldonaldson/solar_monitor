#!/usr/bin/env bash
# deploy.sh — sync code to Ubuntu server without overwriting data/config files
#
# Usage:  ./deploy.sh [--rebuild]
#   --rebuild  also runs docker compose up --build on the server

set -euo pipefail

SERVER="admin1@10.0.0.37"
REMOTE_DIR="/opt/solar_monitor"
LOCAL_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "🚀 Deploying solar_monitor to $SERVER:$REMOTE_DIR ..."

rsync -av \
  --exclude='.git/' \
  --exclude='__pycache__/' \
  --exclude='secrets/' \
  --exclude='.env' \
  --exclude='alert_config.json' \
  --exclude='alert_state.json' \
  --exclude='email_config.json' \
  --exclude='imessage_config.json' \
  --exclude='inverter_config.json' \
  --exclude='inverter_config-SAVE.json' \
  --exclude='inverter_production_history.json' \
  --exclude='inverter_timing_intelligence.json' \
  --exclude='power_history_cache.json' \
  --exclude='simple_weather_cache.json' \
  "$LOCAL_DIR/" "$SERVER:$REMOTE_DIR/"

echo "✅ Code synced."

if [[ "${1:-}" == "--rebuild" ]]; then
  echo "🔨 Rebuilding Docker image on server..."
  ssh "$SERVER" "cd $REMOTE_DIR && docker compose up --build -d"
  echo "✅ Rebuild complete."
else
  echo "ℹ️  Run with --rebuild to also rebuild the Docker image on the server."
  echo "   Or just restart:  ssh $SERVER 'cd $REMOTE_DIR && docker compose restart solar-monitor'"
fi
