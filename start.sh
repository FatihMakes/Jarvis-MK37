#!/bin/bash
DIR="$(cd "$(dirname "$0")" && pwd)"
source "$HOME/.local/bin/env"
cd "$DIR"

echo "🌌 Starting A.L.I Systems..."
echo "   Say 'Hey Ali' to open the assistant."

# Launch wake word listener in background
uv run python wakeword.py &
WAKE_PID=$!

# Trap exit to kill wakeword when terminal closes
trap "kill $WAKE_PID 2>/dev/null" EXIT

# Keep running
wait $WAKE_PID
