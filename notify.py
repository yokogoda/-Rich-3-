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
                    if status in ("attended", "participated"):
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
        f"※次回セミナー({target_seminar.month}/{target_seminar.day})まで あと{days_until}日！",
        "",
        "■ LP訪問・登録（前日/累計）",
        "・全体訪問　",
        f"UU: {fmt_num(m['lp_uu_all_day'])} / {fmt_num(m['lp_uu_all_cum'])}"
        f"　登録: {fmt_num(m['reg_all_day'])} / {fmt_num(m['reg_all_cum'])}（{fmt_rate(m['regrate_all'])}）",
        "・オーガニック(SNS/メルマガ)",
        f"UU: {fmt_num(m['lp_uu_sem_day'])} / {fmt_num(m['lp_uu_sem_cum'])}"
        f"　登録: {fmt_num(m['reg_sem_day'])} / {fmt_num(m['reg_sem_cum'])}（{fmt_rate(m['regrate_sem'])}）",
        "・広告経由(Meta広告)　　",
        f"UU: {fmt_num(m['lp_uu_ad_day'])} / {fmt_num(m['lp_uu_ad_cum'])}"
        f"　登録: {fmt_num(m['reg_ad_day'])} / {fmt_num(m['reg_ad_cum'])}（{fmt_rate(m['regrate_ad'])}）",
        "",
        "■ セミナー予約（前日/累計）※キャンセル除外・日程変更は1名1件",
    ]

    b, c, a = stats["booked"], stats["cancelled"], stats["applied"]

    def rate(n, d):
        return round(n / d, 4) if d else None

    lines.append(f"・実予約数: {fmt_num(stats['booked_day'])} / {fmt_num(b['all'])}名")
    lines.append(f"（登録者の {fmt_rate(rate(b['all'], m.get('reg_all_cum')))} が予約）")
    lines.append(f"  ├ オーガニック経由: {b['organic']}名 ")
    lines.append(f"（登録者の {fmt_rate(rate(b['organic'], m.get('reg_sem_cum')))}）")
    lines.append(f"  └ 広告経由　　　  : {b['ad']}名 ")
    lines.append(f"（登録者の {fmt_rate(rate(b['ad'], m.get('reg_ad_cum')))}）")
    lines.append("")
    lines.append(f"・キャンセル: 累計{c['all']}名"
                 f"（オーガニック{c['organic']} / 広告{c['ad']}）")
    lines.append(f"・申込ベース: 累計{a['all']}名"
                 f"（オーガニック{a['organic']} / 広告{a['ad']}）")
    if stats.get("unmatched"):
        lines.append(f"※うち流入元を特定できなかった方 {stats['unmatched']}名は内訳に含みません")
    lines.append("")

    target_total = OPEN_SEMINAR_SLOTS * SEMINAR_CAPACITY
    lines.append(f"・全体目標進捗: {fmt_num(b['all'])} / {target_total}名"
                 f"（{fmt_rate(rate(b['all'], target_total))}）")
    if stats.get("attended"):
        lines.append(f"・参加数: 累計{stats['attended']}名"
                     f"（開催済み{stats.get('booked_finished', 0)}名の "
                     f"{fmt_rate(rate(stats['attended'], stats.get('booked_finished')))}）")

    if isinstance(m.get("ind_cum"), (int, float)) and m["ind_cum"] > 0:
        lines.append("")
        lines.append("■ 個別相談（前日/累計）")
        lines.append(f"・予約数: {fmt_num(m['ind_day'])} / {fmt_num(m['ind_cum'])}名")

    if isinstance(m.get("web_uu_all_cum"), (int, float)) and m["web_uu_all_cum"] > 0:
        lines.append("")
        lines.append("■ ウェビナーLP流入・登録（前日/累計）")
        lines.append(
            f"・全体　　　UU: {fmt_num(m['web_uu_all_day'])} / {fmt_num(m['web_uu_all_cum'])}"
            f"　登録: {fmt_num(m['web_reg_all_day'])} / {fmt_num(m['web_reg_all_cum'])}（{fmt_rate(m['web_regrate_all'])}）"
        )
        lines.append(
            f"・オーガニック UU: {fmt_num(m['web_uu_org_day'])} / {fmt_num(m['web_uu_org_cum'])}"
            f"　登録: {fmt_num(m['web_reg_org_day'])} / {fmt_num(m['web_reg_org_cum'])}（{fmt_rate(m['web_regrate_org'])}）"
        )
        lines.append(
            f"・広告経由　 UU: {fmt_num(m['web_uu_ad_day'])} / {fmt_num(m['web_uu_ad_cum'])}"
            f"　登録: {fmt_num(m['web_reg_ad_day'])} / {fmt_num(m['web_reg_ad_cum'])}（{fmt_rate(m['web_regrate_ad'])}）"
        )

    lines.append("")
    lines.append("■ 📅 セミナー開催枠別の予約・参加状況")
    slots = fetch_seminar_slot_details(key, target_date) if key else []
    if slots:
        finished_booked = 0
        finished_attended = 0
        for s in slots:
            if s["is_finished"]:
                rate_str = f"（参加率 {round(s['attended'] / s['booked'] * 100, 1)}%）" if s["booked"] else ""
                lines.append(f"・{s['date_label']} 【終了】")
                lines.append(f" : 予約 {s['booked']}名 / 参加 {s['attended']}名{rate_str}")
                finished_booked += s["booked"]
                finished_attended += s["attended"]
            else:
                lines.append(f"・{s['date_label']}")
                lines.append(f" : 予約 {s['booked']}名 / 残 {s['rem']}席（限定8枠）")

        if finished_booked > 0:
            total_rate_str = f"（参加率 {round(finished_attended / finished_booked * 100, 1)}%）"
            lines.append(f"・終了枠 参加者数合計: {finished_attended}名 / 予約{finished_booked}名{total_rate_str}")
    else:
        for date_key, date_display in SEMINAR_SLOT_DISPLAY:
            count, remain = (slot_status or {}).get(date_key, ("—", "—"))
            lines.append(f"・{date_display}")
            lines.append(f" : 予約 {count}名 / 残 {remain}席（限定8枠）")

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
