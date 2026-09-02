#!/usr/bin/env python3
"""
愛されRich美女3期 日次PDCAトラッキング - UTAGE自動同期メインスクリプト (sync_daily.py)

【設計構造】
- config.py       : 定数・ID・パス設定
- utage_api.py    : UTAGE API通信・申込名寄せ・属性判定
- sheets_client.py: Google Sheets API通信・バッチ書き込み
- notify.py       : Chatwork / ntfy レポート作成・送信
"""
import argparse
import datetime
import os
import sys

import gspread

from config import (
    LAST_RUN_OK_PATH,
    PROMO_START,
    SEM_EVENT_PROJECT_ID,
    SERVICE_ACCOUNT_PATH,
    SHEET_NAME,
    SPREADSHEET_ID,
    UTAGE_KEY_PATH,
)
from notify import build_report, notify_chatwork, notify_ntfy, set_notify_enabled
from sheets_client import (
    date_to_col_idx0,
    write_agg_route_block,
    write_date,
    write_summary,
)
from utage_api import fetch_metrics, fetch_seminar_stats


def find_unfilled_dates(ws, start_date, target_date):
    start_col_idx0 = date_to_col_idx0(start_date)
    target_col_idx0 = date_to_col_idx0(target_date)
    num_cols = target_col_idx0 - start_col_idx0 + 1
    if num_cols <= 0:
        return []

    row11 = ws.row_values(11)

    unfilled = []
    for i in range(num_cols):
        idx0 = start_col_idx0 + i
        val = row11[idx0] if idx0 < len(row11) else ""
        if val == "" or val is None:
            col_date = start_date + datetime.timedelta(days=i)
            unfilled.append(col_date)

    return unfilled


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD (default: yesterday)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--promo-start", help="テスト用: 累計の起点日を上書き (YYYY-MM-DD)")
    ap.add_argument("--no-backfill", action="store_true", help="指定日のみ処理し、抜け日を探さない")
    ap.add_argument("--no-notify", action="store_true", help="ChatWork/ntfyへの通知を行わない(動作確認用)")
    args = ap.parse_args()

    if args.no_notify:
        set_notify_enabled(False)

    if args.date:
        target_date = datetime.date.fromisoformat(args.date)
    else:
        target_date = datetime.date.today() - datetime.timedelta(days=1)

    if target_date < PROMO_START:
        print(f"target_date({target_date}) が PROMO_START({PROMO_START}) より前のためスキップします。")
        return

    if not args.no_backfill and not args.dry_run and os.path.exists(LAST_RUN_OK_PATH):
        try:
            with open(LAST_RUN_OK_PATH) as f:
                last_ok = f.read().strip()
            if last_ok == datetime.date.today().isoformat():
                print(f"本日({last_ok})は既に正常終了済みのため、今回は何もせず終了します（通知なし）。")
                return
        except Exception as e:
            print(f"  [warn] {LAST_RUN_OK_PATH} の読み込み失敗(続行します): {e}")

    with open(UTAGE_KEY_PATH) as f:
        key = f.read().strip()

    gc = gspread.service_account(filename=SERVICE_ACCOUNT_PATH)
    sh = gc.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(SHEET_NAME)

    backfilled = []
    if not args.no_backfill:
        unfilled_dates = find_unfilled_dates(ws, PROMO_START, target_date - datetime.timedelta(days=1))
        if unfilled_dates:
            print(f"未入力の過去日を検出しました: {[d.isoformat() for d in unfilled_dates]}")
            for d in unfilled_dates:
                print(f"--- 過去日 {d} の穴埋め処理開始 ---")
                m_back = fetch_metrics(key, d)
                stats_back = fetch_seminar_stats(key, SEM_EVENT_PROJECT_ID, d)
                if not args.dry_run:
                    write_date(ws, m_back, d, stats_back)
                backfilled.append(d)

    print(f"--- 当日処理対象 {target_date} ---")
    m_target = fetch_metrics(key, target_date)
    stats_target = fetch_seminar_stats(key, SEM_EVENT_PROJECT_ID, target_date)

    target_status = "filled"
    changed_fields = []
    if not args.dry_run:
        m_written, decreased_warnings = write_date(ws, m_target, target_date, stats_target)

    failed = []
    if not args.dry_run:
        report_date = max(backfilled + [target_date]) if backfilled else target_date
        last_m = m_written if report_date == target_date else fetch_metrics(key, report_date)
        stats = stats_target if report_date == target_date else fetch_seminar_stats(key, SEM_EVENT_PROJECT_ID, report_date)

        try:
            write_agg_route_block(sh, stats, report_date)
        except Exception as e:
            print(f"  [error] 集計タブの経路別ブロックの更新に失敗: {e}")
            failed.append(("集計:経路別", str(e)))

        try:
            write_summary(ws, last_m, report_date, stats)
        except Exception as e:
            print(f"  [error] サマリー更新に失敗: {e}")
            failed.append(("summary", str(e)))

        try:
            slot_status = {}
            report_text = build_report(last_m, report_date, stats, slot_status, key=key)
            notify_chatwork(report_text)
        except Exception as e:
            print(f"  [warn] 日次レポートの送信に失敗: {e}")

    lines = [f"【愛されRich3期 UTAGE自動更新】{datetime.date.today().isoformat()} 実行結果"]

    if backfilled:
        lines.append(f"📝 過去の空欄日を反映: {', '.join(d.isoformat() for d in backfilled)}")

    if target_status == "filled":
        lines.append(f"📝 前日（{target_date.isoformat()}）分を新規反映しました")
    elif target_status == "corrected":
        lines.append(f"🔄 前日（{target_date.isoformat()}）の数値を最新値に修正しました")
        lines.append(f"　変更箇所: {', '.join(changed_fields)}")
    elif target_status == "up_to_date":
        lines.append(f"✅ データは最新です（前日 {target_date.isoformat()} まで確認済み）")

    if failed:
        lines.append("\n❌ 失敗:")
        for item, err in failed:
            lines.append(f"  - {item}: {err}")

    summary_msg = "\n".join(lines)
    print("\n" + summary_msg)

    if not args.dry_run:
        if not failed:
            with open(LAST_RUN_OK_PATH, "w") as f:
                f.write(datetime.date.today().isoformat())
            notify_ntfy("UTAGE Sync Success", summary_msg, priority="low")
        else:
            notify_ntfy("UTAGE Sync Failed", summary_msg, priority="high")
            sys.exit(1)


if __name__ == "__main__":
    main()
