#!/bin/bash
export PATH="/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin:$HOME/.local/bin:$PATH"
export LANG="ja_JP.UTF-8"
export LC_ALL="ja_JP.UTF-8"
mkdir -p "$HOME/.config/utage-pdca/logs"

# 昨日の日付 (YYYY-MM-DD)
YESTERDAY=$(date -v-1d +%Y-%m-%d 2>/dev/null || date -d "yesterday" +%Y-%m-%d)
FLAG_FILE="$HOME/.config/utage-pdca/logs/sent_${YESTERDAY}.flag"

LOG="$HOME/.config/utage-pdca/logs/sync_$(date +%Y%m%d_%H%M%S).log"
caffeinate -i bash -c '
  sleep 45
  # セミナー当日であれば速報レポートを自動送信
  python3 "$HOME/.config/utage-pdca/send_seminar_day_report.py" || true

  # 毎週月曜日であれば週間配信スケジュール報告を自動送信
  if [ "$(date +%u)" -eq 1 ]; then
      python3 "$HOME/.config/utage-pdca/chatwork_schedule_reporter.py" --send || true
  fi

  # 本日の日次レポートが送信済みなら日次処理のみスキップ
  if [ $# -eq 0 ] && [ -f "'"$FLAG_FILE"'" ]; then
      echo "本日分 ('"$YESTERDAY"') の日次ChatWork報告は送信済みのためスキップします。"
      exit 0
  fi

  MAX_RETRIES=5
  RETRY_COUNT=0
  until python3 "$HOME/.config/utage-pdca/sync_daily.py" "$@"; do
    RETRY_COUNT=$((RETRY_COUNT + 1))
    if [ $RETRY_COUNT -ge $MAX_RETRIES ]; then
      echo "[ERROR] 自動実行が上限リトライ回数 (${MAX_RETRIES}回) に達したため終了します。"
      exit 1
    fi
    echo "[WARN] ネットワークまたはAPI接続タイムアウトを検知。30秒後に自動再接続・再実行します (${RETRY_COUNT}/${MAX_RETRIES})..."
    sleep 30
  done
' _ "$@" > "$LOG" 2>&1
