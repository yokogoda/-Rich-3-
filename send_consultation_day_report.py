#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
愛されRich美女3期 UTAGE自動更新システム - 本日開催 個別相談リマインド報告スクリプト (send_consultation_day_report.py)
"""

import os, sys, datetime, json, urllib.request, urllib.parse, ssl, re

CONFIG_DIR = os.path.expanduser("~/.config/utage-pdca")
UTAGE_KEY_PATH = os.path.join(CONFIG_DIR, "utage_api_key.txt")
CHATWORK_TOKEN_PATH = os.path.join(CONFIG_DIR, "chatwork_api_token.txt")
CHATWORK_ROOM_ID_PATH = os.path.join(CONFIG_DIR, "chatwork_room_id.txt")
PRIVATE_CHATWORK_ROOM_ID_PATH = os.path.join(CONFIG_DIR, "private_chatwork_room_id.txt")
SERVICE_ACCOUNT_PATH = os.path.expanduser("~/.config/mcp-google-sheets/service-account.json")

CONSULTATION_EVENT_ID = "YyESC92nIW9c"
SHEET_ID = "1Bo6um_mJ1Eur87vUPEbEnCC5RtGaXyLKPDIHTMqHAAk"
SHEET_TAB_NAME = "【事務局管理用】個別面談予約リスト"
SHEET_TAB_GID = "1499419433"
MANUAL_FILE_URL = "https://www.chatwork.com/gateway/download_file.php?bin=1&file_id=2125470203"

def format_meeting_id(url):
    m = re.search(r'/j/(\d+)', url)
    if not m:
        return ""
    digits = m.group(1)
    if len(digits) == 11:
        return f"{digits[:3]} {digits[3:7]} {digits[7:]}"
    elif len(digits) == 10:
        return f"{digits[:3]} {digits[3:6]} {digits[6:]}"
    return digits

def clean_zoom_url(url):
    return url.split('?')[0] if '?' in url else url

def fetch_consultations_from_utage(target_date, key):
    headers = {'Authorization': f'Bearer {key}'}
    ssl_ctx = ssl._create_unverified_context()

    url_sched = f'https://api.utage-system.com/v1/events/{CONSULTATION_EVENT_ID}/schedules'
    req_sched = urllib.request.Request(url_sched, headers=headers)
    schedules = {}
    try:
        with urllib.request.urlopen(req_sched, timeout=15, context=ssl_ctx) as resp:
            data = json.load(resp)
            for item in data.get('data', []):
                schedules[item['id']] = item
    except Exception as e:
        print(f"  [warn] UTAGE日程取得エラー: {e}")

    url_app = f'https://api.utage-system.com/v1/events/{CONSULTATION_EVENT_ID}/applicants?per_page=100'
    req_app = urllib.request.Request(url_app, headers=headers)
    applicants = []
    try:
        with urllib.request.urlopen(req_app, timeout=15, context=ssl_ctx) as resp:
            data = json.load(resp)
            applicants = data.get('data', [])
    except Exception as e:
        print(f"  [warn] UTAGE予約者取得エラー: {e}")

    items = []
    for a in applicants:
        status = a.get('status_participation', '')
        if status in ('cancel', 'cancel_changed', 'canceled'):
            continue

        sched_info = a.get('schedule') or {}
        sched_id = sched_info.get('id')
        sched_detail = schedules.get(sched_id, {})

        start_str = sched_detail.get('start_datetime') or sched_info.get('start_datetime')
        if not start_str:
            continue

        try:
            dt_start = datetime.datetime.strptime(start_str, '%Y-%m-%d %H:%M:%S')
        except ValueError:
            try:
                dt_start = datetime.datetime.strptime(start_str, '%Y-%m-%d %H:%M')
            except ValueError:
                continue

        if dt_start.date() != target_date:
            continue

        end_str = sched_detail.get('end_datetime')
        if end_str:
            try:
                dt_end = datetime.datetime.strptime(end_str, '%Y-%m-%d %H:%M:%S')
                time_slot = f"{dt_start.hour:02d}:{dt_start.minute:02d}〜{dt_end.hour:02d}:{dt_end.minute:02d}"
            except ValueError:
                time_slot = f"{dt_start.hour:02d}:{dt_start.minute:02d}〜"
        else:
            time_slot = f"{dt_start.hour:02d}:{dt_start.minute:02d}〜"

        name = (a.get('name') or '').replace(' ', '').replace('　', '')
        zoom_url = sched_detail.get('url', '')

        items.append({
            'time_slot': time_slot,
            'name': name,
            'zoom_url': zoom_url,
            'start_dt': dt_start
        })

    return items

def fetch_consultations_from_sheet(target_date):
    if not os.path.exists(SERVICE_ACCOUNT_PATH):
        return []

    try:
        import gspread
        gc = gspread.service_account(filename=SERVICE_ACCOUNT_PATH)
        sh = gc.open_by_key(SHEET_ID)
        ws = sh.worksheet(SHEET_TAB_NAME)
        records = ws.get_all_records()
    except Exception as e:
        print(f"  [warn] スプレッドシート読み込み失敗: {e}")
        return []

    target_date_str = target_date.strftime('%Y/%m/%d')
    items = []

    for r in records:
        sched_text = str(r.get('日程詳細', '')).strip()
        if not sched_text or not sched_text.startswith(target_date_str):
            continue

        is_cancel = str(r.get('キャンセル', '')).upper() == 'TRUE'
        is_change = str(r.get('日程変更', '')).upper() == 'TRUE'
        if is_cancel or is_change:
            continue

        m_time = re.search(r'(\d{1,2}:\d{2}〜\d{1,2}:\d{2})', sched_text)
        time_slot = m_time.group(1) if m_time else "時間未定"

        sei = str(r.get('姓', '')).strip()
        mei = str(r.get('名', '')).strip()
        name = f"{sei}{mei}".replace(' ', '').replace('　', '')

        items.append({
            'time_slot': time_slot,
            'name': name,
            'zoom_url': '',
            'start_dt': datetime.datetime.combine(target_date, datetime.time.min)
        })

    return items

def build_message(target_date, items):
    weekday_ja = ["月", "火", "水", "木", "金", "土", "日"]
    date_str = f"{target_date.month}/{target_date.day}({weekday_ja[target_date.weekday()]})"
    mention_header = "[To:3556218]杉本京子さん\n[To:1128477]言海祥太（了戒翔太）さん\n[toall]"

    lines = [
        mention_header,
        "",
        f"【本日開催 個別相談（{len(items)}件）】",
        "本日の個別相談報告です。",
        "どうぞよろしくお願いいたします。",
        "",
        "■ 本日の個別相談スケジュール"
    ]

    if items:
        for item in items:
            lines.append(f"・{item['time_slot']} : {item['name']}様")
    else:
        lines.append("※本日の個別相談予定はありません。")

    lines.append("")
    lines.append("■ 開催概要")
    lines.append(f"・日程: {date_str}")

    sheet_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/edit?gid={SHEET_TAB_GID}#gid={SHEET_TAB_GID}"

    lines.extend([
        "",
        "■ 各種確認リスト＆マニュアル",
        "・個別相談予約リスト＆後追い▼",
        sheet_url,
        "・ステータス変更マニュアル(言海さん用)▼",
        MANUAL_FILE_URL,
        "",
        "個別相談予約2時間半後に、個別相談のThanks＋本講座案内は自動で届きます。",
        "早めにご案内を送りたい場合は手動となりますのでCWからお知らせください。"
    ])

    return "\n".join(lines)

def post_to_chatwork(body_text, target_room_id=None):
    try:
        with open(CHATWORK_TOKEN_PATH) as f:
            token = f.read().strip()
        if not target_room_id:
            with open(CHATWORK_ROOM_ID_PATH) as f:
                target_room_id = f.read().strip()
    except FileNotFoundError:
        print("  [error] ChatWork設定が見つかりません。")
        return False

    url = f"https://api.chatwork.com/v2/rooms/{target_room_id}/messages"
    data = urllib.parse.urlencode({"body": body_text}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"X-ChatWorkToken": token}, method="POST")
    ssl_ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(req, timeout=15, context=ssl_ctx) as res:
            res.read()
            print(f"  [info] 当日個別相談レポートをChatwork (ルームID: {target_room_id}) へ送信しました。")
            return True
    except Exception as e:
        print(f"  [error] Chatwork送信失敗: {e}")
        return False

def main():
    is_send_mode = "--send" in sys.argv
    is_test_mode = "--test" in sys.argv or "--test-room" in sys.argv
    force_send = "--force" in sys.argv

    target_date = datetime.date.today()
    for arg in sys.argv:
        if arg.startswith("--date="):
            target_date = datetime.datetime.strptime(arg.split("=")[1], "%Y-%m-%d").date()

    key = None
    if os.path.exists(UTAGE_KEY_PATH):
        with open(UTAGE_KEY_PATH) as f:
            key = f.read().strip()

    items = []
    if key:
        items = fetch_consultations_from_utage(target_date, key)

    if not items:
        items = fetch_consultations_from_sheet(target_date)

    items.sort(key=lambda x: x['start_dt'])

    if not items and is_send_mode and not force_send and not is_test_mode:
        print(f"  [info] 本日の日付 ({target_date}) は個別相談の予約がないため送信をスキップします。")
        return

    target_room_id = None
    if is_test_mode:
        if os.path.exists(PRIVATE_CHATWORK_ROOM_ID_PATH):
            with open(PRIVATE_CHATWORK_ROOM_ID_PATH) as f:
                target_room_id = f.read().strip()
        else:
            target_room_id = "445327814"
        print(f"  [info] テスト送信モードです (送信先ルームID: {target_room_id})")

    msg = build_message(target_date, items)

    today_str = target_date.isoformat()
    lock_file = os.path.join(CONFIG_DIR, f"logs/sent_consultation_day_{today_str}.flag")

    if os.path.exists(lock_file) and is_send_mode and not is_test_mode:
        print(f"  [info] 本日 ({today_str}) の個別相談速報報告は送信済みのためスキップします。")
        return

    if is_send_mode:
        if post_to_chatwork(msg, target_room_id=target_room_id):
            if not is_test_mode:
                os.makedirs(os.path.join(CONFIG_DIR, "logs"), exist_ok=True)
                with open(lock_file, "w") as f:
                    f.write(today_str)
    else:
        print("--- 送信プレビュー ---")
        print(msg)

if __name__ == "__main__":
    main()
