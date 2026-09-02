#!/usr/bin/env python3
import urllib.request, urllib.parse, os, sys, datetime, json

CONFIG_DIR = os.path.expanduser("~/.config/utage-pdca")
UTAGE_KEY_PATH = os.path.join(CONFIG_DIR, "utage_api_key.txt")
CHATWORK_TOKEN_PATH = os.path.join(CONFIG_DIR, "chatwork_api_token.txt")
CHATWORK_ROOM_ID_PATH = os.path.join(CONFIG_DIR, "chatwork_room_id.txt")
EVENT_ID = "C0vOokE5slKi"

def main():
    try:
        with open(UTAGE_KEY_PATH) as f:
            key = f.read().strip()
        with open(CHATWORK_TOKEN_PATH) as f:
            token = f.read().strip()
        with open(CHATWORK_ROOM_ID_PATH) as f:
            room_id = f.read().strip()
    except FileNotFoundError as e:
        print(f"設定ファイルが見つかりません: {e}")
        return

    headers = {'Authorization': f'Bearer {key}'}
    url_sched = f'https://api.utage-system.com/v1/events/{EVENT_ID}/schedules'
    req = urllib.request.Request(url_sched, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            schedules = json.load(resp).get('data', [])
    except Exception as e:
        print(f"セミナー日程取得エラー: {e}")
        return

    today = datetime.date.today()
    today_slot = None
    for s in schedules:
        dt = datetime.datetime.strptime(s['start_datetime'], '%Y-%m-%d %H:%M:%S')
        if dt.date() == today:
            today_slot = s
            break

    if not today_slot:
        print(f"本日の日付 ({today}) はセミナー開催日ではありません。")
        return

    # 重複送信フラグチェック
    flag_file = os.path.join(CONFIG_DIR, f"logs/sent_seminar_flash_{today.isoformat()}.flag")
    if os.path.exists(flag_file):
        print(f"本日のセミナー速報レポート ({today.isoformat()}) はすでに送信済みです。")
        return

    booked = today_slot['applicant_count'] - today_slot['cancel_count']
    zoom_url = today_slot.get('url', 'https://love.kyoko-happy.com/l/6xu35ZUyoSL9')
    dt = datetime.datetime.strptime(today_slot['start_datetime'], '%Y-%m-%d %H:%M:%S')
    weekday_ja = ["月", "火", "水", "木", "金", "土", "日"]
    date_str = f"{dt.month}/{dt.day}({weekday_ja[dt.weekday()]})"
    time_str = f"{dt.hour:02d}:{dt.minute:02d}〜"

    date_messages = {
        datetime.date(2026, 8, 18): f"いよいよ本日 {time_str} セミナー開催日です！\n\n本日画面オフ、事務局として参加させていただきます。何かお困りごとがございましたら、チャットワークからお知らせくださいませ。",
        datetime.date(2026, 8, 22): f"本日 {time_str} 本日第二回セミナーになります。本日もどうぞよろしくおねがいいたします。",
        datetime.date(2026, 8, 28): f"本日 {time_str} 本日第3回セミナーになります。何かお困りごとがございましたら、チャットワークからお知らせくださいませ。\n明日9:00より追加開催告知となります。どうぞよろしくお願いいたします。",
    }

    intro_msg = date_messages.get(today, f"本日 {time_str} セミナー開催日です！\n\n本日もどうぞよろしくお願いいたします。")

    lines = [
        "[To:3556218]杉本京子さん",
        "[To:1128477]言海祥太（了戒翔太）さん",
        "[toall]",
        "",
        f"【愛されRich3期 セミナー当日速報】{date_str}",
        intro_msg,
        "",
        "■ 本日の予約状況",
        f"・本日予約者数: {booked}名（キャンセル除外）",
        "",
        "■ セミナーZoomリンク",
        f"{zoom_url}",
        "",
        "■ 予約者リスト▼",
        "https://docs.google.com/spreadsheets/d/1Bo6um_mJ1Eur87vUPEbEnCC5RtGaXyLKPDIHTMqHAAk/edit?gid=753597932#gid=753597932",
        "",
        "┈┈┈┈┈┈┈┈┈┈┈┈୨୧",
        "",
        "【個別相談予約】",
        "https://love.kyoko-happy.com/p/consultation-sr3",
        "",
        "【本講座お申し込み】",
        "https://love.kyoko-happy.com/p/registration-sr3",
        "┈┈┈┈┈┈┈┈┈┈┈┈୨୧",
        "",
        "数値レポートはこちら▼",
        "https://docs.google.com/spreadsheets/d/1Bo6um_mJ1Eur87vUPEbEnCC5RtGaXyLKPDIHTMqHAAk/edit"
    ]

    msg = "\n".join(lines)
    url_cw = f'https://api.chatwork.com/v2/rooms/{room_id}/messages'
    data = f'body={urllib.parse.quote(msg)}'.encode()
    req_cw = urllib.request.Request(url_cw, data=data, method='POST', headers={'X-ChatWorkToken': token})
    try:
        with urllib.request.urlopen(req_cw, timeout=15) as resp:
            resp.read()
        print("  [info] セミナー当日速報レポートを送信しました")
        with open(flag_file, "w") as f:
            f.write("sent")
    except Exception as e:
        print(f"  [warn] 送信失敗: {e}")

if __name__ == "__main__":
    main()
