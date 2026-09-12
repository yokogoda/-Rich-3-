#!/usr/bin/env python3
"""
愛されRich美女3期 UTAGE自動更新システム - 通知・レポート作成モジュール (notify.py)
"""
import datetime
import json
import urllib.parse
import urllib.request

from config import (
    CHATWORK_ROOM_ID_PATH,
    CHATWORK_TOKEN_PATH,
    FIRST_SEMINAR_DATE,
    NTFY_TOPIC_PATH,
    OPEN_SEMINAR_SLOTS,
    SEM_EVENT_PROJECT_ID,
    SEMINAR_CAPACITY,
    SPREADSHEET_URL,
    WEBINAR_LP_COUNT_START,
)

NOTIFY_ENABLED = True


def set_notify_enabled(enabled: bool):
    global NOTIFY_ENABLED
    NOTIFY_ENABLED = enabled


def fmt_num(val):
    if val is None or val == "":
        return "—"
    if isinstance(val, (int, float)):
        return f"{val:,}"
    return str(val)


def fmt_rate(val):
    if val is None or val == "":
        return "—"
    if isinstance(val, (int, float)):
        return f"{val * 100:.1f}%"
    return str(val)


SEMINAR_SLOT_DISPLAY = [
    ("2026-08-18", "8/18(火) 20:00〜"),
    ("2026-08-22", "8/22(土) 10:00〜"),
    ("2026-08-28", "8/28(金) 20:00〜"),
    ("2026-09-05", "9/5(土) 20:00〜"),
    ("2026-09-11", "9/11(金) 20:00〜"),
]


def next_seminar_date():
    dates = [datetime.date.fromisoformat(key) for key, _ in SEMINAR_SLOT_DISPLAY]
    today = datetime.date.today()
    upcoming = sorted(d for d in dates if d >= today)
    return upcoming[0] if upcoming else max(dates)


def fetch_seminar_slot_details(key, target_date=None):
    url_sched = f"https://api.utage-system.com/v1/events/{SEM_EVENT_PROJECT_ID}/schedules"
    req_sched = urllib.request.Request(url_sched, headers={"Authorization": f"Bearer {key}"})

    url_app = f"https://api.utage-system.com/v1/events/{SEM_EVENT_PROJECT_ID}/applicants?per_page=100"
    req_app = urllib.request.Request(url_app, headers={"Authorization": f"Bearer {key}"})

    try:
        with urllib.request.urlopen(req_sched, timeout=15) as resp:
            items = json.load(resp).get("data", [])

        attended_by_sched = {}
        try:
            with urllib.request.urlopen(req_app, timeout=15) as resp:
                applicants = json.load(resp).get("data", [])
                for a in applicants:
                    sched_id = (a.get("schedule") or {}).get("id")
                    status = a.get("status_participation")
                    # 参加とみなすのは attended だけ(2026-09-07ユーザー確認)。
                    # UTAGEの参加状況は reserved/attended/delay/cancel_*の6値しかなく、
                    # "participated" は存在しない値だったので外した。
                    if status == "attended":
                        attended_by_sched[sched_id] = attended_by_sched.get(sched_id, 0) + 1
        except Exception as e:
            print(f"  [warn] 参加者データの取得失敗: {e}")

        ref_date = target_date or datetime.date.today()
        slots = []
        for item in items:
            start_str = item.get("start_datetime", "")
            if not start_str or start_str < "2026-08-01":
                continue
            dt = datetime.datetime.fromisoformat(start_str)
            wday = ["月", "火", "水", "木", "金", "土", "日"][dt.weekday()]
            time_str = dt.strftime("%H:%M")
            date_label = f"{dt.month}/{dt.day}({wday}) {time_str}〜"
            booked = item.get("applicant_count", 0) - item.get("cancel_count", 0)
            max_cap = 8
            rem = max(0, max_cap - booked)
            sched_id = item.get("id")
            attended = attended_by_sched.get(sched_id, 0)
            is_finished = (dt.date() <= ref_date)

            slots.append({
                "date_label": date_label,
                "dt": dt,
                "booked": booked,
                "rem": rem,
                "is_finished": is_finished,
                "attended": attended
            })

        slots.sort(key=lambda s: s["dt"])
        return slots
    except Exception as e:
        print(f"  [warn] セミナー日程詳細の取得に失敗: {e}")
        return []


def build_report(m, target_date, stats, slot_status=None, key=None):
    weekday_ja = ["月", "火", "水", "木", "金", "土", "日"]
    date_label = f"{target_date.month}/{target_date.day}({weekday_ja[target_date.weekday()]})"

    target_seminar = next_seminar_date()
    days_until = (target_seminar - datetime.date.today()).days

    lines = [
        f"【愛されRich3期 日次レポート】{date_label}",
    ]

    if datetime.date.today() <= target_seminar and days_until >= 0:
        lines.append(f"※次回セミナー({target_seminar.month}/{target_seminar.day})まで あと{days_until}日！")

    lines.append("")

    # 1. ウェビナーLP流入・登録
    if target_date >= WEBINAR_LP_COUNT_START or (isinstance(m.get("web_uu_all_cum"), (int, float)) and m["web_uu_all_cum"] > 0):
        lines.append("■ ウェビナーLP流入・登録（前日/累計）")
        lines.append(
            f"・全体　　　UU: {fmt_num(m.get('web_uu_all_day'))} / {fmt_num(m.get('web_uu_all_cum'))}"
            f"　登録: {fmt_num(m.get('web_reg_all_day'))} / {fmt_num(m.get('web_reg_all_cum'))}（{fmt_rate(m.get('web_regrate_all'))}）"
        )
        lines.append(
            f"・オーガニック UU: {fmt_num(m.get('web_uu_org_day'))} / {fmt_num(m.get('web_uu_org_cum'))}"
            f"　登録: {fmt_num(m.get('web_reg_org_day'))} / {fmt_num(m.get('web_reg_org_cum'))}（{fmt_rate(m.get('web_regrate_org'))}）"
        )
        lines.append(
            f"・広告経由　 UU: {fmt_num(m.get('web_uu_ad_day'))} / {fmt_num(m.get('web_uu_ad_cum'))}"
            f"　登録: {fmt_num(m.get('web_reg_ad_day'))} / {fmt_num(m.get('web_reg_ad_cum'))}（{fmt_rate(m.get('web_regrate_ad'))}）"
        )
        lines.append("")

    # 2. セミナーLP訪問・登録
    lines.append("■ セミナーLP訪問・登録（前日/累計）")
    lines.append(
        "・全体訪問　"
        f"UU: {fmt_num(m['lp_uu_all_day'])} / {fmt_num(m['lp_uu_all_cum'])}"
        f"　登録: {fmt_num(m['reg_all_day'])} / {fmt_num(m['reg_all_cum'])}（{fmt_rate(m['regrate_all'])}）"
    )
    lines.append(
        "・オーガニック(SNS/メルマガ) "
        f"UU: {fmt_num(m['lp_uu_sem_day'])} / {fmt_num(m['lp_uu_sem_cum'])}"
        f"　登録: {fmt_num(m['reg_sem_day'])} / {fmt_num(m['reg_sem_cum'])}（{fmt_rate(m['regrate_sem'])}）"
    )
    lines.append(
        "・広告経由(Meta広告)　　"
        f"UU: {fmt_num(m['lp_uu_ad_day'])} / {fmt_num(m['lp_uu_ad_cum'])}"
        f"　登録: {fmt_num(m['reg_ad_day'])} / {fmt_num(m['reg_ad_cum'])}（{fmt_rate(m['regrate_ad'])}）"
    )
    lines.append("")

    # 3. ウェビナー予約
    if target_date >= WEBINAR_LP_COUNT_START or (isinstance(m.get("web_reg_all_cum"), (int, float)) and m["web_reg_all_cum"] > 0):
        lines.append("■ ウェビナー予約（前日/累計）")
        lines.append(f"・実予約数: {fmt_num(m.get('web_reg_all_day'))} / {fmt_num(m.get('web_reg_all_cum'))}名")
        lines.append(f"  ├ オーガニック経由: {fmt_num(m.get('web_reg_org_cum'))}名")
        lines.append(f"  └ 広告経由　　　  : {fmt_num(m.get('web_reg_ad_cum'))}名")
        lines.append("")

    # 4. セミナー予約
    lines.append("■ セミナー予約（前日/累計）※キャンセル除外・日程変更は1名1件")

    b, c, a = stats["booked"], stats["cancelled"], stats["applied"]
    att_by_attr = stats.get("attended_by_attr") or {"organic": 0, "ad": 0}
    fin_by_attr = stats.get("booked_finished_by_attr") or {"organic": 0, "ad": 0}

    def rate(n, d):
        return round(n / d, 4) if d else None

    lines.append(f"・実予約数: {fmt_num(stats['booked_day'])} / {fmt_num(b['all'])}名（登録者の {fmt_rate(rate(b['all'], m.get('reg_all_cum')))} が予約）")
    lines.append(f"  ├ オーガニック経由: {b['organic']}名（参加 {att_by_attr.get('organic', 0)}名・参加率 {fmt_rate(rate(att_by_attr.get('organic', 0), fin_by_attr.get('organic', 0)))})")
    lines.append(f"  └ 広告経由　　　  : {b['ad']}名（参加 {att_by_attr.get('ad', 0)}名・参加率 {fmt_rate(rate(att_by_attr.get('ad', 0), fin_by_attr.get('ad', 0)))})")
    lines.append("")
    lines.append(f"・キャンセル: 累計{c['all']}名（オーガニック{c['organic']} / 広告{c['ad']}）")
    lines.append(f"・申込ベース: 累計{a['all']}名（オーガニック{a['organic']} / 広告{a['ad']}）")
    if stats.get("unmatched"):
        lines.append(f"※うち流入元を特定できなかった方 {stats['unmatched']}名は内訳に含みません")
    lines.append("")

    target_total = OPEN_SEMINAR_SLOTS * SEMINAR_CAPACITY
    lines.append(f"・全体目標進捗: {fmt_num(b['all'])} / {target_total}名（{fmt_rate(rate(b['all'], target_total))}）")
    if stats.get("attended"):
        lines.append(f"・参加数: 累計{stats['attended']}名（開催済み{stats.get('booked_finished', 0)}名の {fmt_rate(rate(stats['attended'], stats.get('booked_finished')))}）")

    # 5. 個別相談
    lines.append("")
    lines.append("■ 個別相談（前日/累計）")
    lines.append(f"・予約数: {fmt_num(m.get('ind_day'))} / {fmt_num(m.get('ind_cum'))}名")

    # 4. 本講座
    lines.append("")
    lines.append("■ 本講座（前日/累計）")
    lines.append(f"・申込数: {fmt_num(m.get('apply_day'))} / {fmt_num(m.get('apply_cum'))}名")
    lines.append(f"・成約数: {fmt_num(m.get('sale_day'))} / {fmt_num(m.get('sale_cum'))}件（{fmt_rate(m.get('sale_rate'))}）")
    lines.append(f"・売上金額: {fmt_num(m.get('amount_day'))}円 / {fmt_num(m.get('amount_cum'))}円")

    lines.append("")
    lines.append("数値レポートはこちら▼")
    lines.append(SPREADSHEET_URL)

    return "\n".join(lines)


def notify_chatwork(message):
    if not NOTIFY_ENABLED:
        print("  [--no-notify] ChatWorkへは送信しません。本文:\n" + message)
        return
    try:
        with open(CHATWORK_TOKEN_PATH) as f:
            token = f.read().strip()
        with open(CHATWORK_ROOM_ID_PATH) as f:
            room_id = f.read().strip()
    except FileNotFoundError:
        print("  [info] ChatWork通知先が未設定のため通知をスキップします")
        return
    url = f"https://api.chatwork.com/v2/rooms/{room_id}/messages"
    mention = "[To:3556218]杉本京子さん\n[To:1128477]言海祥太（了戒翔太）さん\n[toall]\n"
    data = f"body={urllib.parse.quote(mention + message)}".encode()
    req = urllib.request.Request(url, data=data, method="POST",
                                  headers={"X-ChatWorkToken": token})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        print("  [info] ChatWork通知を送信しました")
    except Exception as e:
        print(f"  [warn] ChatWork通知の送信に失敗: {e}")


def notify_ntfy(title, message, priority="default"):
    if not NOTIFY_ENABLED:
        print(f"  [--no-notify] ntfyへは送信しません。({title})")
        return
    try:
        with open(NTFY_TOPIC_PATH) as f:
            topic = f.read().strip()
    except FileNotFoundError:
        print("  [info] ntfyトピックが未設定のため通知をスキップします")
        return
    url = f"https://ntfy.sh/{topic}"
    req = urllib.request.Request(
        url,
        data=message.encode("utf-8"),
        method="POST",
        headers={"Title": title.encode("utf-8"), "Priority": priority},
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            resp.read()
        print("  [info] ntfy通知を送信しました")
    except Exception as e:
        print(f"  [warn] ntfy通知の送信に失敗: {e}")
