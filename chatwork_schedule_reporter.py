#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chatwork 毎週月曜日 配信スケジュール自動報告スクリプト (最新スプレッドシート連動版)
"""

import os, sys, csv, io, urllib.request, urllib.parse, datetime

CONFIG_DIR = os.path.expanduser("~/.config/utage-pdca")
CHATWORK_TOKEN_PATH = os.path.join(CONFIG_DIR, "chatwork_api_token.txt")
CHATWORK_ROOM_ID_PATH = os.path.join(CONFIG_DIR, "chatwork_room_id.txt")

MASTER_SHEET_URL = "https://docs.google.com/spreadsheets/d/12zT7vCUqcAZ0YexlnCt2U3BWeT0YbYMW1DPjtgT54WQ/edit#gid=1930246157"
CSV_EXPORT_URL = "https://docs.google.com/spreadsheets/d/12zT7vCUqcAZ0YexlnCt2U3BWeT0YbYMW1DPjtgT54WQ/gviz/tq?tqx=out:csv&gid=1930246157"

def build_message():
    today = datetime.date.today()
    monday = today - datetime.timedelta(days=today.weekday())
    sunday = monday + datetime.timedelta(days=6)

    monday_str = f"{monday.month}/{monday.day}"
    sunday_str = f"{sunday.month}/{sunday.day}"

    mention_header = "[To:3556218]杉本京子さん\n[To:1128477]言海祥太（了戒翔太）さん\n[toall]"
    
    msg = f"{mention_header}\n\n"
    msg += "おはようございます。\n今週もどうぞよろしくお願いいたします。\n\n"
    msg += "━━━━━━━━━━\n"
    msg += f"📱 今週の配信スケジュール（{monday_str}〜{sunday_str}）\n"
    msg += "━━━━━━━━━━\n\n"

    req = urllib.request.Request(CSV_EXPORT_URL)
    rows = []
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode('utf-8')
            reader = csv.DictReader(io.StringIO(content))
            rows = list(reader)
    except Exception as e:
        print(f"  [warn] スプレッドシートの読み込みエラー: {e}")

    weekday_ja = ["月", "火", "水", "木", "金", "土", "日"]
    schedules_by_date = {}
    for r in rows:
        pdate = r.get("配信予定日", "").strip()
        if not pdate:
            continue
        try:
            dt = datetime.datetime.strptime(pdate, "%Y-%m-%d").date()
            if monday <= dt <= sunday:
                wday_str = r.get("曜日", "").strip() or weekday_ja[dt.weekday()]
                date_key = f"{dt.month}/{dt.day}({wday_str})"
                if date_key not in schedules_by_date:
                    schedules_by_date[date_key] = []
                schedules_by_date[date_key].append((r, dt))
        except ValueError:
            pass

    if schedules_by_date:
        for date_key, items in schedules_by_date.items():
            msg += f"【{date_key}】\n"
            for idx, (item, dt) in enumerate(items):
                status_val = item.get("確認ステータス", "").strip()
                time_val = item.get("配信時間", "").strip()
                media_val = item.get("配信媒体", "").strip()
                title_val = item.get("原稿タイトル / 配信名", "").strip()
                target_user = item.get("配信対象", "").strip()
                role_val = item.get("担当役割", "").strip()
                action_val = item.get("アクション事項", "").strip()

                if media_val:
                    msg += f"・配信媒体：{media_val}\n"
                if time_val:
                    msg += f"・配信時間：{time_val}\n"
                if title_val:
                    msg += f"・件名・内容：\n　└ {title_val}\n"
                if role_val:
                    msg += f"・担当：{role_val}\n"
                if target_user:
                    msg += f"・対象者：{target_user}\n"
                if status_val:
                    msg += f"・ステータス：{status_val}\n"
                if action_val:
                    msg += f"・補足：{action_val}\n"

                if idx < len(items) - 1:
                    msg += "\n"
            msg += "\n"
    else:
        msg += "※今週予定されている配信スケジュールは登録されていません。\n\n"

    msg += "━━━━━━━━━━\n\n"
    msg += f"配信スケジュール管理マスターはこちら▼\n{MASTER_SHEET_URL}\n\n"
    msg += "どうぞよろしくお願いいたします！"

    return msg

def post_to_chatwork(body_text):
    try:
        with open(CHATWORK_TOKEN_PATH) as f:
            token = f.read().strip()
        with open(CHATWORK_ROOM_ID_PATH) as f:
            room_id = f.read().strip()
    except FileNotFoundError:
        print("  [error] ChatWork設定が見つかりません。")
        return False

    url = f"https://api.chatwork.com/v2/rooms/{room_id}/messages"
    data = urllib.parse.urlencode({"body": body_text}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"X-ChatWorkToken": token}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as res:
            res.read()
            print("  [info] 週間配信スケジュールをChatworkへ送信しました。")
            return True
    except Exception as e:
        print(f"  [error] Chatwork送信失敗: {e}")
        return False

def main():
    is_send_mode = "--send" in sys.argv
    msg = build_message()

    today_str = datetime.date.today().isoformat()
    lock_file = os.path.join(CONFIG_DIR, f"logs/sent_weekly_schedule_{today_str}.flag")

    if os.path.exists(lock_file) and is_send_mode:
        print(f"  [info] 本日 ({today_str}) の週間配信スケジュール報告は送信済みのためスキップします。")
        return

    if is_send_mode:
        if post_to_chatwork(msg):
            os.makedirs(os.path.join(CONFIG_DIR, "logs"), exist_ok=True)
            with open(lock_file, "w") as f:
                f.write(today_str)
    else:
        print("--- 送信プレビュー ---")
        print(msg)

if __name__ == "__main__":
    main()
