#!/bin/bash
#
# 編集用原本(このリポジトリ)を、launchdが実際に実行する ~/.config/utage-pdca/ へ反映する。
#
# 【なぜ必要か】
# macOSのTCC制限で、launchdはDesktop配下のファイルを直接読めない。そのため実行の実体は
# ~/.config/utage-pdca/ に置いてある(このリポジトリはあくまで編集用の原本)。
# つまり `git pull` しただけでは翌朝の自動実行には反映されない。pullの後は必ずこれを実行すること。
#
# 【安全性】
# コピーするのは *.py と run_sync.sh だけ。認証情報(*.txt)・キャッシュ(*.json)・ログには一切触らない。
# 上書き前に、既存の .py を backup/ へ日時付きで退避する(戻したくなったらそこから戻せる)。
# 反映前に「変わるファイルの一覧」を出して確認を求めるので、意図しない上書きは起きない。
#
# 【★2026-09-07時点の注意★】
# ナツナさんのMacの本番(~/.config/utage-pdca/)は、まだ分割前のmonolith版で動いている。
# しかもリポジトリに入っていない修正が本番側に入っている(2026-09-04の参加率as-of修正・
# ChatWork通知の「目標比」文面)。この状態でdeployすると、その修正が巻き戻る。
# 詳細は knowledge/now.md の「参加率にas-of無し」の項を参照。
# 移植が済むまでは実行しないこと。
#
# 【使い方】
#   bash deploy.sh
#
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${AISARE_DEPLOY_DEST:-$HOME/.config/utage-pdca}"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$DEST/backup/$STAMP"

echo "=== 愛されRich3期 集計コード: 本番反映 ==="
echo "  コピー元: $SRC"
echo "  コピー先: $DEST"
echo

if [ ! -f "$SRC/sync_daily.py" ]; then
  echo "エラー: 原本が見つかりません: $SRC/sync_daily.py" >&2
  echo "このスクリプトはリポジトリのルートに置いて実行してください。" >&2
  exit 1
fi
mkdir -p "$DEST"

# 1) 何が変わるかを先に見せる(backup/ や docs/ は対象外。トップレベルのみ)
echo "[1/4] 反映すると変わるファイル:"
CHANGED=0
for f in "$SRC"/*.py "$SRC"/run_sync.sh; do
  [ -f "$f" ] || continue
  b="$(basename "$f")"
  if [ ! -f "$DEST/$b" ]; then
    echo "        + $b  (新規)"
    CHANGED=$((CHANGED + 1))
  elif ! cmp -s "$f" "$DEST/$b"; then
    echo "        ~ $b  ($(wc -c < "$DEST/$b" | tr -d ' ') → $(wc -c < "$f" | tr -d ' ') バイト)"
    CHANGED=$((CHANGED + 1))
  fi
done
if [ "$CHANGED" -eq 0 ]; then
  echo "        (差分なし。反映するものはありません)"
  exit 0
fi

# 2) 確認
echo
echo "★ 本番の集計コードを置き換えます。数値レポートの結果が変わる可能性があります。"
read -r -p "  続けますか? [y/N]: " ans || ans=""
case "$ans" in
  y|Y|yes|YES) ;;
  *) echo "  中止しました。何も変更していません。"; exit 0 ;;
esac

# 3) 既存の実行ファイルをバックアップ
echo
if compgen -G "$DEST"/*.py > /dev/null; then
  mkdir -p "$BACKUP"
  cp "$DEST"/*.py "$BACKUP"/ 2>/dev/null || true
  [ -f "$DEST/run_sync.sh" ] && cp "$DEST/run_sync.sh" "$BACKUP"/ 2>/dev/null || true
  echo "[2/4] 既存ファイルを退避しました → $BACKUP"
else
  echo "[2/4] 既存の実行ファイルがないため、退避はスキップします(初回セットアップ)"
fi

# 4) 本体をコピー
cp "$SRC"/*.py "$DEST"/
cp "$SRC"/run_sync.sh "$DEST"/
echo "[3/4] Pythonスクリプトと run_sync.sh をコピーしました"

echo "[4/4] 反映後のファイル:"
ls -1t "$DEST"/*.py "$DEST"/run_sync.sh | while read -r f; do
  printf "        %s  (%s)\n" "$(basename "$f")" "$(date -r "$f" '+%m/%d %H:%M')"
done

echo
echo "=== 完了しました ==="
echo "翌朝の自動実行から、新しいコードが使われます。"
echo
echo "※ 認証情報(*.txt)・流入元キャッシュ(*.json)・ログには触れていません。"
echo "※ このリポジトリに無い notify_kyoko_promo_check.py / sync_webinar_survey.py /"
echo "   run_cancel_cleanup.sh / setup_launchd.sh はそのまま残しています。"
