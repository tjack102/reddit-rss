#!/bin/bash
# Check if latest digest was generated within last 26 hours
# This script is designed for VPS deployment (Linux)

DIGEST="data/digests/latest.html"
HEALTH_LOG="logs/health.log"

if [ ! -f "$DIGEST" ]; then
    echo "$(date) WARN: No digest file found" >> "$HEALTH_LOG"
    exit 1
fi

AGE=$(( $(date +%s) - $(stat -c %Y "$DIGEST") ))
if [ "$AGE" -gt 93600 ]; then
    echo "$(date) WARN: Digest is $(($AGE / 3600)) hours old" >> "$HEALTH_LOG"
    exit 1
fi

echo "$(date) OK: Digest is $(($AGE / 3600)) hours old" >> "$HEALTH_LOG"
exit 0
