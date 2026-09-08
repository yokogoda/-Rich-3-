#!/bin/bash
# 本番用launchdジョブ（毎朝6:30 1日1回）を、実行しているMacのユーザー環境に合わせて作成する。
set -e

LABEL_MAIN="com.utage-pdca.daily-630"
LABEL_RECHECK="com.utage-pdca.daily-800"
AGENTS_DIR="$HOME/Library/LaunchAgents"
SCRIPT_DIR="$HOME/.config/utage-pdca"

mkdir -p "$AGENTS_DIR" "$SCRIPT_DIR/logs"

# 古い8:00ジョブがあれば削除
launchctl unload "$AGENTS_DIR/$LABEL_RECHECK.plist" 2>/dev/null || true
rm -f "$AGENTS_DIR/$LABEL_RECHECK.plist"

cat > "$AGENTS_DIR/$LABEL_MAIN.plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>$LABEL_MAIN</string>
    <key>ProgramArguments</key>
    <array>
        <string>$SCRIPT_DIR/run_sync.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>6</integer>
        <key>Minute</key>
        <integer>0</integer>
    </dict>
    <key>StandardOutPath</key>
    <string>$SCRIPT_DIR/logs/launchd_main_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$SCRIPT_DIR/logs/launchd_main_stderr.log</string>
</dict>
</plist>
EOF

launchctl unload "$AGENTS_DIR/$LABEL_MAIN.plist" 2>/dev/null || true
launchctl load "$AGENTS_DIR/$LABEL_MAIN.plist"

echo "登録完了: 毎朝6:30（1日1回）に自動実行されます"
launchctl list | grep utage-pdca
