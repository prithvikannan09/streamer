#!/bin/bash
cd "$(dirname "$0")"
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
PY=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12
CH="${1:-@arunthewall}"
ID="${2:-}"
for i in $(seq 1 40); do
  [ -n "$ID" ] && break
  ID=$($PY -m yt_dlp --no-warnings --print id "https://www.youtube.com/$CH/live" 2>/dev/null | head -1)
  [ -n "$ID" ] || sleep 15
done
[ -z "$ID" ] && { echo "no live video found for $CH"; exit 1; }
pkill -f "chatwin https://www.youtube.com/live_chat" 2>/dev/null
echo "opening chat for $ID"
exec ./chatwin "https://www.youtube.com/live_chat?v=$ID"
