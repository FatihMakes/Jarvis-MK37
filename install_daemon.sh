#!/bin/bash
# Installs Ali's wakeword listener as a macOS LaunchAgent.
# After running this once, wakeword.py will start automatically at login
# and restart itself if it ever crashes — no terminal needed.

set -e

PLIST_NAME="com.ali.wakeword"
PLIST_PATH="$HOME/Library/LaunchAgents/$PLIST_NAME.plist"
DIR="$(cd "$(dirname "$0")" && pwd)"
UV="$HOME/.local/bin/uv"

echo "🔧 Installing Ali wake-word daemon..."

# Unload existing agent if present
launchctl unload "$PLIST_PATH" 2>/dev/null || true

cat > "$PLIST_PATH" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
  "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$PLIST_NAME</string>

    <key>ProgramArguments</key>
    <array>
        <string>$UV</string>
        <string>run</string>
        <string>python</string>
        <string>$DIR/wakeword.py</string>
    </array>

    <key>WorkingDirectory</key>
    <string>$DIR</string>

    <key>RunAtLoad</key>
    <true/>

    <key>KeepAlive</key>
    <true/>

    <key>ThrottleInterval</key>
    <integer>5</integer>

    <key>StandardOutPath</key>
    <string>/tmp/ali_wakeword.log</string>

    <key>StandardErrorPath</key>
    <string>/tmp/ali_wakeword_err.log</string>
</dict>
</plist>
EOF

launchctl load "$PLIST_PATH"
echo "✅ Daemon installed and started."
echo "   Say 'Hey Ali' at any time — even after reboot."
echo ""
echo "   Logs:  tail -f /tmp/ali_wakeword.log"
echo "   Stop:  launchctl unload $PLIST_PATH"
echo "   Start: launchctl load $PLIST_PATH"
