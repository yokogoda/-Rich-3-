#!/usr/bin/env python3
"""
愛されRich美女3期 日次PDCAトラッキング - UTAGEデータ自動同期スクリプト

デフォルトでは前日までの「抜けている日」をすべて自動でバックフィルする。
Googleスプレッドシートの該当日付列・サマリーに書き込み、
実行結果（成功/失敗/警告）をChatWorkに通知する。

累計は PROMO_START（2026-08-07）からの積み上げとして扱う。
ただしセミナーLP(ハウスリスト訴求)のみ SEM_LP_COUNT_START（2026-08-09）からのカウントとする
（広告は8/7から先行して回っているが、ハウスリストへの訴求は8/9からのため、
それより前のセミナーLP流入は意図的にノーカウント扱いにする）。

対象日が既に反映済みの場合は何もせず終了する(通知も送らない)。
これにより「6:30で成功していれば8:00は無音でスキップ、本当に抜けていた時だけ動いて通知する」という挙動になる。
エラー時は常に通知される(処理を試みた結果失敗した場合のみ通知が飛ぶため)。
"""
import argparse
import datetime
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

import gspread

# どのユーザーのMacで実行しても ~/.config/utage-pdca/ 配下を見に行くので、
# このファイル自体は誰の環境にコピーしてもパス変更なしで動く。
CONFIG_DIR = os.path.expanduser("~/.config/utage-pdca")

# --no-notify を付けた実行では ChatWork/ntfy へ送らず、内容を標準出力に出すだけにする。
# 動作確認のたびに本番ルームへ投稿してしまう事故を防ぐため(2026-08-30追加)。
NOTIFY_ENABLED = True

SPREADSHEET_ID = "1Bo6um_mJ1Eur87vUPEbEnCC5RtGaXyLKPDIHTMqHAAk"
SPREADSHEET_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
SHEET_NAME = "日次PDCAトラッキング"
SERVICE_ACCOUNT_PATH = os.path.expanduser("~/.config/mcp-google-sheets/service-account.json")
UTAGE_KEY_PATH = os.path.join(CONFIG_DIR, "utage_api_key.txt")
CHATWORK_TOKEN_PATH = os.path.join(CONFIG_DIR, "chatwork_api_token.txt")
CHATWORK_ROOM_ID_PATH = os.path.join(CONFIG_DIR, "chatwork_room_id.txt")
NTFY_TOPIC_PATH = os.path.join(CONFIG_DIR, "ntfy_topic.txt")

PROMO_START = datetime.date(2026, 8, 7)  # 2026-08-07: 広告開始・予約発生に伴い8/9→8/7に前倒し
SEM_LP_COUNT_START = datetime.date(2026, 8, 9)  # セミナーLP(ハウスリスト訴求)は8/9からカウント。広告LPとカウント基準日が異なる
DATE_COL_START = 5  # column E (1-indexed)
SHEET_DATE_ORIGIN = datetime.date(2026, 8, 7)  # E列=8/7起点（2026-08-07、広告前倒しに合わせてシート側の日付列もユーザーが8/7開始に変更済み）

LP_FUNNEL = "3FQFH1OGtggw"
# 2026-08-24〜「追加開催」の新しいLPページが作られ、アクセスがほぼ完全にそちらへ移行した。
# 旧ページIDだけを見ていたため8/24・25分のPV/UU/登録数が集計から漏れる事故が発生(2026-08-26発覚)。
# 今後も追加開催のたびに新しいpage_idが増える可能性があるので、その都度ここへ追記すること。
# 確認方法: UTAGE管理画面の対象ファネル(3FQFH1OGtggw)のページ一覧、またはfunnel_page_list。
LP_PAGE_SEMINAR_IDS = ["0Vkf2Xbh7Z51", "SzjnNkjXB0E8"]  # 旧:セレンディピティ愛されRich美女【3期】 / 新:8/24〜追加開催用
LP_PAGE_AD_IDS = ["9UFM3KgpnZuT", "r78i61GBLPz0"]  # 旧:広告用 / 新:【広告用】8/24〜

# ウェビナーLP(2026-09-12〜、セミナー終了後の切り替え先)。同じLP_FUNNEL内の別ステップ。
# セミナーLPと同様、追加開催等で新ページが増えたらここへ追記すること。
WEBINAR_LP_COUNT_START = datetime.date(2026, 9, 12)  # セミナー終了後の切り替え日。それより前は集計しない
WEBINAR_LP_PAGE_IDS = ["67GSIiohgEMV"]  # ウェビナーLP(オーガニック、ステップCovHbdSTxRzM)
WEBINAR_AD_PAGE_IDS = ["mwGnEJqUeLXb"]  # 【広告】ウェビナーLP(ステップevJGYwRi8bMK、2026-08-26作成)

SEM_FUNNEL = "pcKWfTityvBy"
SEM_STEP_SEMINAR = "aTaZ7RyW3wQg"
SEM_STEP_INDIVIDUAL = "XvO0niPi1J0U"

PAY_FUNNEL = "rLlJKRapAlIl"
PAY_STEP_APPLY = "HZa6G78keLQt"
PAY_STEP_SALE = "2qYpn8p3qjcf"

SEM_EVENT_PROJECT_ID = "C0vOokE5slKi"

# LINEアカウント(セレンディピティ愛されRich美女)。LP登録者とセミナー申込者を
# picture_url経由で突き合わせるための友だち一覧の取得先。
# もう1つのアカウント(杉本京子, cpIn7sVgBrs4)は別リストなのでここでは使わない。
LINE_ACCOUNT_ID = "tAS0YwOrTZIH"

ACTIVE_STATUSES = {"reserved", "attended", "delay"}
CANCEL_STATUSES = {"cancel_contact", "cancel_no_contact", "cancel_changed"}

# 「集計」タブに出す経路別ブロックの位置(既存のA7:C13の下。既存部分には触れない)
AGG_SHEET_NAME = "集計"
AGG_ROUTE_ROW = 15  # A15に見出し、16に列見出し、17-19に数値、20に注記
FIRST_SEMINAR_DATE = datetime.date(2026, 8, 18)
OPEN_SEMINAR_SLOTS = 5  # 現在募集中の日程数(8/18,8/22,8/28,9/5,9/11)。日程を追加したらここを変更する
SEMINAR_CAPACITY = 8
SEMINAR_SLOT_DISPLAY = [
    ("8/18", "8/18(火) 20:00〜"),
    ("8/22", "8/22(土) 10:00〜"),
    ("8/28", "8/28(金) 20:00〜"),
    ("9/5", "9/5(土) 20:00〜"),
    ("9/11", "9/11(金) 20:00〜"),
]

ROW = {
    "lp_pv_all_cum": 11, "lp_uu_all_cum": 12,
    "lp_pv_sem_cum": 13, "lp_uu_sem_cum": 14,
    "lp_pv_ad_cum": 15, "lp_uu_ad_cum": 16,
    "lp_pv_all_day": 17, "lp_uu_all_day": 18,
    "lp_pv_sem_day": 19, "lp_uu_sem_day": 20,
    "lp_pv_ad_day": 21, "lp_uu_ad_day": 22,
    "reg_all_cum": 23, "reg_sem_cum": 24, "reg_ad_cum": 25,
    "reg_all_day": 26, "reg_sem_day": 27, "reg_ad_day": 28,
    "regrate_all": 29, "regrate_sem": 30, "regrate_ad": 31,
    "sem_cum": 32, "sem_day": 33, "sem_rate": 34,
    "ind_cum": 35, "ind_day": 36,
    "apply_cum": 37, "apply_day": 38,
    "sale_cum": 39, "sale_day": 40,
    "amount_cum": 41, "amount_day": 42,
    "web_pv_all_cum": 43, "web_uu_all_cum": 44,
    "web_pv_org_cum": 45, "web_uu_org_cum": 46,
    "web_pv_ad_cum": 47, "web_uu_ad_cum": 48,
    "web_pv_all_day": 49, "web_uu_all_day": 50,
    "web_pv_org_day": 51, "web_uu_org_day": 52,
    "web_pv_ad_day": 53, "web_uu_ad_day": 54,
    "web_reg_all_cum": 55, "web_reg_org_cum": 56, "web_reg_ad_cum": 57,
    "web_reg_all_day": 58, "web_reg_org_day": 59, "web_reg_ad_day": 60,
    "web_regrate_all": 61, "web_regrate_org": 62, "web_regrate_ad": 63,
}

CUM_ROWS = [
    "lp_pv_all_cum", "lp_uu_all_cum", "lp_pv_sem_cum", "lp_uu_sem_cum",
    "lp_pv_ad_cum", "lp_uu_ad_cum", "reg_all_cum", "reg_sem_cum", "reg_ad_cum",
    "sem_cum", "ind_cum", "apply_cum", "sale_cum", "amount_cum",
    "web_pv_all_cum", "web_uu_all_cum", "web_pv_org_cum", "web_uu_org_cum",
    "web_pv_ad_cum", "web_uu_ad_cum", "web_reg_all_cum", "web_reg_org_cum", "web_reg_ad_cum",
]
DAY_ROWS = [
    "lp_pv_all_day", "lp_uu_all_day", "reg_all_day", "sem_day", "ind_day",
    "web_pv_all_day", "web_uu_all_day", "web_reg_all_day",
    "apply_day", "sale_day", "amount_day",
]


def with_retry(fn, retries=5, backoff=5):
    """失敗時に一定間隔でリトライする。Google Sheets APIのクォータ超過(429)は
    「1分待てば必ず解消する」性質のエラーのため、通常の瞬断より長く(60秒)待つ
    (2026-08-28追加: 複数ジョブが同じサービスアカウントを使っており、
    webinar-survey-merge等の高頻度ジョブと重なってクォータ超過が頻発していたため)。"""
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except Exception as e:
            last_err = e
            wait = 60 if ("429" in str(e) or "Quota exceeded" in str(e)) else backoff
            print(f"  [warn] call attempt {attempt}/{retries} failed: {e}; retrying in {wait}s")
            time.sleep(wait)
    raise last_err


def utage_get(key, path, params, retries=5, backoff=5):
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"https://api.utage-system.com/v1{path}?{qs}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {key}"})
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.load(resp)
        except (urllib.error.URLError, ConnectionError, TimeoutError) as e:
            last_err = e
            print(f"  [warn] utage_get attempt {attempt}/{retries} failed: {e}; retrying in {backoff}s")
            time.sleep(backoff)
    raise last_err


def find_step(data, step_id):
    for step in data.get("data", []):
        if step.get("step_id") == step_id:
            return step
    return None


def daily_value(page_or_step, target_date_str, field):
    for d in page_or_step.get("daily", []):
        if d.get("date") == target_date_str:
            return d.get(field, 0)
    return 0


def fetch_metrics(key, target_date):
    date_from = PROMO_START.isoformat()
    date_to = target_date.isoformat()
    target_str = target_date.isoformat()

    def find_pages_any(data, page_ids):
        pages = []
        for step in data.get("data", []):
            for page in step.get("pages", []):
                if page.get("page_id") in page_ids:
                    pages.append(page)
        return pages

    def sum_cum(pages, field):
        return sum(p["totals"].get(field, 0) for p in pages)

    def sum_day(pages, field):
        return sum(daily_value(p, target_str, field) for p in pages)

    # セミナーLP(ハウスリスト訴求)は8/9からカウント開始。
    # それより前(target_dateがSEM_LP_COUNT_START未満)は問い合わせ自体を行わず、
    # 全項目0(ノーカウント)として扱う。date_from > date_toの逆転リクエストを避けるためのガードでもある。
    if target_date < SEM_LP_COUNT_START:
        lp_sem_pages = []
    else:
        lp_sem_pages = find_pages_any(
            utage_get(key, f"/funnels/{LP_FUNNEL}/stats/daily",
                      {"page_ids": ",".join(LP_PAGE_SEMINAR_IDS), "date_from": SEM_LP_COUNT_START.isoformat(), "date_to": date_to}),
            LP_PAGE_SEMINAR_IDS)
    lp_ad_pages = find_pages_any(
        utage_get(key, f"/funnels/{LP_FUNNEL}/stats/daily",
                  {"page_ids": ",".join(LP_PAGE_AD_IDS), "date_from": date_from, "date_to": date_to}),
        LP_PAGE_AD_IDS)

    # ウェビナーLPはセミナー終了後(WEBINAR_LP_COUNT_START=2026-09-12)からカウント開始。
    # それより前は問い合わせ自体を行わず、全項目0(ノーカウント)として扱う。
    if target_date < WEBINAR_LP_COUNT_START:
        web_org_pages = []
        web_ad_pages = []
    else:
        web_org_pages = find_pages_any(
            utage_get(key, f"/funnels/{LP_FUNNEL}/stats/daily",
                      {"page_ids": ",".join(WEBINAR_LP_PAGE_IDS), "date_from": WEBINAR_LP_COUNT_START.isoformat(), "date_to": date_to}),
            WEBINAR_LP_PAGE_IDS)
        web_ad_pages = find_pages_any(
            utage_get(key, f"/funnels/{LP_FUNNEL}/stats/daily",
                      {"page_ids": ",".join(WEBINAR_AD_PAGE_IDS), "date_from": WEBINAR_LP_COUNT_START.isoformat(), "date_to": date_to}),
            WEBINAR_AD_PAGE_IDS)

    sem_data = utage_get(key, f"/funnels/{SEM_FUNNEL}/stats/daily",
                         {"date_from": date_from, "date_to": date_to})
    sem_step = find_step(sem_data, SEM_STEP_SEMINAR)
    ind_step = find_step(sem_data, SEM_STEP_INDIVIDUAL)

    def step_page(step):
        return step["pages"][0] if step and step.get("pages") else None

    sem_page = step_page(sem_step)
    ind_page = step_page(ind_step)

    pay_data = utage_get(key, f"/funnels/{PAY_FUNNEL}/stats/daily",
                        {"date_from": date_from, "date_to": date_to})
    apply_step = find_step(pay_data, PAY_STEP_APPLY)
    sale_step = find_step(pay_data, PAY_STEP_SALE)
    apply_page = step_page(apply_step)
    sale_page = step_page(sale_step)

    def cum(page, field):
        return page["totals"].get(field, 0) if page else 0

    def day(page, field):
        return daily_value(page, target_str, field) if page else 0

    m = {}
    m["lp_pv_sem_cum"] = sum_cum(lp_sem_pages, "pv"); m["lp_pv_sem_day"] = sum_day(lp_sem_pages, "pv")
    m["lp_uu_sem_cum"] = sum_cum(lp_sem_pages, "uu"); m["lp_uu_sem_day"] = sum_day(lp_sem_pages, "uu")
    m["reg_sem_cum"] = sum_cum(lp_sem_pages, "registration_count"); m["reg_sem_day"] = sum_day(lp_sem_pages, "registration_count")

    m["lp_pv_ad_cum"] = sum_cum(lp_ad_pages, "pv"); m["lp_pv_ad_day"] = sum_day(lp_ad_pages, "pv")
    m["lp_uu_ad_cum"] = sum_cum(lp_ad_pages, "uu"); m["lp_uu_ad_day"] = sum_day(lp_ad_pages, "uu")
    m["reg_ad_cum"] = sum_cum(lp_ad_pages, "registration_count"); m["reg_ad_day"] = sum_day(lp_ad_pages, "registration_count")

    m["lp_pv_all_cum"] = m["lp_pv_sem_cum"] + m["lp_pv_ad_cum"]
    m["lp_pv_all_day"] = m["lp_pv_sem_day"] + m["lp_pv_ad_day"]
    m["lp_uu_all_cum"] = m["lp_uu_sem_cum"] + m["lp_uu_ad_cum"]
    m["lp_uu_all_day"] = m["lp_uu_sem_day"] + m["lp_uu_ad_day"]
    m["reg_all_cum"] = m["reg_sem_cum"] + m["reg_ad_cum"]
    m["reg_all_day"] = m["reg_sem_day"] + m["reg_ad_day"]

    m["web_pv_org_cum"] = sum_cum(web_org_pages, "pv"); m["web_pv_org_day"] = sum_day(web_org_pages, "pv")
    m["web_uu_org_cum"] = sum_cum(web_org_pages, "uu"); m["web_uu_org_day"] = sum_day(web_org_pages, "uu")
    m["web_reg_org_cum"] = sum_cum(web_org_pages, "registration_count"); m["web_reg_org_day"] = sum_day(web_org_pages, "registration_count")

    m["web_pv_ad_cum"] = sum_cum(web_ad_pages, "pv"); m["web_pv_ad_day"] = sum_day(web_ad_pages, "pv")
    m["web_uu_ad_cum"] = sum_cum(web_ad_pages, "uu"); m["web_uu_ad_day"] = sum_day(web_ad_pages, "uu")
    m["web_reg_ad_cum"] = sum_cum(web_ad_pages, "registration_count"); m["web_reg_ad_day"] = sum_day(web_ad_pages, "registration_count")

    m["web_pv_all_cum"] = m["web_pv_org_cum"] + m["web_pv_ad_cum"]
    m["web_pv_all_day"] = m["web_pv_org_day"] + m["web_pv_ad_day"]
    m["web_uu_all_cum"] = m["web_uu_org_cum"] + m["web_uu_ad_cum"]
    m["web_uu_all_day"] = m["web_uu_org_day"] + m["web_uu_ad_day"]
    m["web_reg_all_cum"] = m["web_reg_org_cum"] + m["web_reg_ad_cum"]
    m["web_reg_all_day"] = m["web_reg_org_day"] + m["web_reg_ad_day"]

    m["sem_cum"] = cum(sem_page, "registration_count"); m["sem_day"] = day(sem_page, "registration_count")
    m["ind_cum"] = cum(ind_page, "registration_count"); m["ind_day"] = day(ind_page, "registration_count")
    m["apply_cum"] = cum(apply_page, "registration_count"); m["apply_day"] = day(apply_page, "registration_count")
    m["sale_cum"] = cum(sale_page, "sale_count"); m["sale_day"] = day(sale_page, "sale_count")
    m["amount_cum"] = cum(sale_page, "sale_amount"); m["amount_day"] = day(sale_page, "sale_amount")

    def rate(n, d):
        return round(n / d, 4) if d else ""

    m["regrate_all"] = rate(m["reg_all_cum"], m["lp_uu_all_cum"])
    m["regrate_sem"] = rate(m["reg_sem_cum"], m["lp_uu_sem_cum"])
    m["regrate_ad"] = rate(m["reg_ad_cum"], m["lp_uu_ad_cum"])
    m["sem_rate"] = rate(m["sem_cum"], m["reg_all_cum"])
    m["sale_rate"] = rate(m["sale_cum"], m["apply_cum"])
    m["web_regrate_all"] = rate(m["web_reg_all_cum"], m["web_uu_all_cum"])
    m["web_regrate_org"] = rate(m["web_reg_org_cum"], m["web_uu_org_cum"])
    m["web_regrate_ad"] = rate(m["web_reg_ad_cum"], m["web_uu_ad_cum"])

    return m


def fmt_num(n):
    return f"{int(n):,}" if isinstance(n, (int, float)) else "—"


def fmt_rate(r):
    return f"{r * 100:.1f}%" if isinstance(r, (int, float)) else "—"


def fmt_yen(n):
    return f"¥{int(n):,}" if isinstance(n, (int, float)) else "—"


def fetch_line_friends(key, account_id):
    """LINEアカウントの友だち一覧を全件取得する。

    LP登録者(subscribers)とセミナー申込者(event applicants)はID体系が異なり直接は結合できない
    (subscriber.id と applicant.line_friend.id は1件も重ならないことを実測で確認済み)。
    友だちの picture_url を仲介にすることで
    「LP登録者 → LINE友だち → セミナー申込者」を厳密なID一致で繋げる(2026-08-30)。"""
    friends = []
    page = 1
    while True:
        data = with_retry(lambda page=page: utage_get(
            key, f"/accounts/{account_id}/line/friends", {"page": page, "per_page": 100}))
        rows = data.get("data", [])
        friends.extend(rows)
        meta = data.get("meta", {})
        if page * meta.get("per_page", 100) >= meta.get("total", 0) or not rows:
            break
        page += 1
    return friends


def fetch_lp_registrants(key, funnel_id, page_ids):
    """指定LPページ群の登録者を全件返す。subscribers APIは page_id 指定で叩くため、
    どのLPから登録したか(=広告LPか通常LPか)はページID単位で確実に分かる。
    utm_* も入っているが、広告経由かどうかの判定にUTMは使わない
    (QRコードを別端末で読む等でUTMは正常な登録でも6%程度欠落するため、
     ページIDで数えるのが正しい。2026-08-30にユーザーと合意)。"""
    rows_all = []
    for page_id in page_ids:
        page = 1
        while True:
            data = with_retry(lambda page=page, page_id=page_id: utage_get(
                key, f"/funnels/{funnel_id}/subscribers",
                {"page_id": page_id, "page": page, "per_page": 100}))
            rows = data.get("data", [])
            for r in rows:
                r["_page_id"] = page_id
            rows_all.extend(rows)
            meta = data.get("meta", {})
            if page * meta.get("per_page", 100) >= meta.get("total", 0) or not rows:
                break
            page += 1
    return rows_all


def build_attribution_index(key):
    """流入元判定用の対応表を作る。

    戻り値: (friend_id -> (attr, 最初の登録日時), LINE表示名 -> (attr, 最初の登録日時))
    attr は "organic"(通常LP=セミナーLP) / "ad"(広告LP)。
    同一人物が両方のLPに登録していた場合は先に登録した方を採用する。
    friend_id で引けなかった場合(LINEアイコン未設定・変更後など)に備えて
    表示名の対応表も併せて返し、フォールバックに使う。"""
    friends = fetch_line_friends(key, LINE_ACCOUNT_ID)
    pic_to_fid = {}
    for f in friends:
        pu = f.get("picture_url")
        if pu and pu not in pic_to_fid:
            pic_to_fid[pu] = f.get("id")

    by_fid = {}
    by_name = {}
    for attr, page_ids in (("organic", LP_PAGE_SEMINAR_IDS), ("ad", LP_PAGE_AD_IDS)):
        for r in fetch_lp_registrants(key, LP_FUNNEL, page_ids):
            created = r.get("created_at") or "9999"
            fid = pic_to_fid.get(r.get("line_picture_url"))
            if fid:
                cur = by_fid.get(fid)
                if cur is None or created < cur[1]:
                    by_fid[fid] = (attr, created)
            name = (r.get("line_display_name") or r.get("name") or "").strip()
            if name:
                cur = by_name.get(name)
                if cur is None or created < cur[1]:
                    by_name[name] = (attr, created)
    return by_fid, by_name


def fetch_seminar_applicants(key, event_project_id):
    """イベント申込者を全件取得する(キャンセル・日程変更のレコードも含む生の状態)。"""
    rows = []
    page = 1
    while True:
        data = with_retry(lambda page=page: utage_get(
            key, f"/events/{event_project_id}/applicants",
            {"page": page, "per_page": 100}))
        r = data.get("data", [])
        rows.extend(r)
        meta = data.get("meta", {})
        if page * meta.get("per_page", 100) >= meta.get("total", 0) or not r:
            break
        page += 1
    return rows


ATTR_CACHE_PATH = os.path.join(CONFIG_DIR, "seminar_applicant_attributions.json")
ATTR_CACHE_VERSION = 2  # v1はLINE表示名だけで判定していた。v2はID連鎖で判定する


def load_applicant_attributions_cache():
    if os.path.exists(ATTR_CACHE_PATH):
        try:
            with open(ATTR_CACHE_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            if data.get("_v") == ATTR_CACHE_VERSION:
                return data
            print("  [info] 流入元キャッシュが旧方式(表示名判定)のため作り直します")
        except Exception as e:
            print(f"  [warn] 流入元キャッシュの読み込みに失敗: {e}")
    return {"_v": ATTR_CACHE_VERSION}


def save_applicant_attributions_cache(cache):
    try:
        os.makedirs(CONFIG_DIR, exist_ok=True)
        with open(ATTR_CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"  [warn] 流入元キャッシュの保存に失敗: {e}")


def fetch_seminar_stats(key, event_project_id, target_date):
    """セミナーの申込・キャンセル・実予約・参加を経路別に集計する。

    数え方(2026-08-30に全面見直し。広告会社へのCV実測の要請がきっかけ):

    1. 1人1件に名寄せする。UTAGEは日程変更のたびに「旧日程=cancel_changed」と
       「新日程=reserved」の2レコードを残すため、そのまま数えると二重計上になる。
       メールアドレス単位でまとめ、申込日は最も古いレコードの created_at を採用する。
    2. 有効な予約(ACTIVE_STATUSES)が1件も残っていない人だけを「キャンセル」とする。
       日程変更しただけの人はキャンセルに数えない。
    3. 累計は target_date までに申し込んだ人だけを数える。
       以前は対象日に関係なく「実行時点の全レコード数」を返していたため、
       過去日を再実行すると全ての列が現在値で塗り潰されていた。
    4. 流入元は build_attribution_index() のID連鎖(picture_url→friend_id)で判定する。
       表示名だけの判定は「ゆか」「min」のような短いニックネームで衝突する危険があった。

    注意: キャンセル日時はUTAGE APIから取得できない。このためキャンセルは申込日に遡って
    反映される(一度カウントされた予約が後日キャンセルされると過去の累計も下がる)。
    申込数の方は遡って変化しないので、シートには申込数とキャンセル数の両方を残している。
    """
    applicants = fetch_seminar_applicants(key, event_project_id)

    cache = load_applicant_attributions_cache()
    uncached = [a for a in applicants if a.get("id") and a["id"] not in cache]
    if uncached:
        by_fid, by_name = build_attribution_index(key)
        for a in uncached:
            lf = a.get("line_friend") or {}
            fid = lf.get("id")
            hit = by_fid.get(fid) if fid else None
            how = "id"
            if hit is None:
                name = (lf.get("display_name") or a.get("name") or "").strip()
                hit = by_name.get(name) if name else None
                how = "name" if hit else "none"
            cache[a["id"]] = {
                "attr": hit[0] if hit else "unmatched",
                "how": how,
                "name": a.get("name"),
                "created_at": a.get("created_at", ""),
            }
        save_applicant_attributions_cache(cache)

    # メールアドレス単位で名寄せ
    by_mail = {}
    for a in applicants:
        mail = (a.get("mail") or "").strip().lower()
        if not mail:
            mail = "id:" + str(a.get("id"))
        by_mail.setdefault(mail, []).append(a)

    target_str = target_date.isoformat()
    keys = ("all", "organic", "ad")
    booked = {k: 0 for k in keys}
    cancelled = {k: 0 for k in keys}
    booked_day = applied_day = 0
    unmatched = 0
    unmatched_names = []

    for mail, recs in by_mail.items():
        first = min(recs, key=lambda x: x.get("created_at") or "")
        applied_at = (first.get("created_at") or "")[:10]
        if applied_at > target_str:
            continue  # 対象日より後の申込は数えない
        statuses = {r.get("status_participation") for r in recs}
        is_active = bool(statuses & ACTIVE_STATUSES)
        attr = cache.get(first.get("id"), {}).get("attr", "unmatched")
        if attr not in ("organic", "ad"):
            unmatched += 1
            unmatched_names.append(first.get("name"))
            attr = None
        bucket = cancelled if not is_active else booked
        bucket["all"] += 1
        if attr:
            bucket[attr] += 1
        if applied_at == target_str:
            applied_day += 1
            if is_active:
                booked_day += 1

    applied = {k: booked[k] + cancelled[k] for k in keys}

    # 参加数: status_participation が attended のレコード数。
    # UTAGEに「欠席」ステータスは無く、参加しなかった人は reserved のまま残る。
    # よって欠席数は「終了枠の有効予約 - attended」で算出する。
    attended = sum(1 for a in applicants
                   if a.get("status_participation") == "attended")

    # 日程別の実予約数(キャンセル・日程変更の旧レコードを除く)
    per_slot = {}
    for a in applicants:
        if a.get("status_participation") not in ACTIVE_STATUSES:
            continue
        start = (a.get("schedule") or {}).get("start_datetime") or ""
        if start:
            per_slot[start[:10]] = per_slot.get(start[:10], 0) + 1

    # 参加率の分母は「開催済みの枠の実予約数」。全予約数で割ると、まだ開催前の
    # 枠の予約が分母に入って参加率が不当に低く出る(2026-08-30にユーザー承認して変更)。
    booked_finished = sum(n for d, n in per_slot.items() if d <= target_str)

    if unmatched:
        print(f"  [info] 流入元を特定できなかった予約者: {unmatched}名 {unmatched_names}")

    return {
        "booked": booked, "cancelled": cancelled, "applied": applied,
        "booked_day": booked_day, "applied_day": applied_day,
        "attended": attended, "per_slot": per_slot,
        "booked_finished": booked_finished,
        "unmatched": unmatched,
    }


    """「集計」タブの日程別 件数・残席を {日程ラベル: (件数, 残席)} で返す"""
    ws = with_retry(lambda: sh.worksheet("集計"))
    rows = with_retry(lambda: ws.get("A9:C13"))
    status = {}
    for row in rows:
        if len(row) >= 3 and row[0]:
            status[row[0]] = (row[1], row[2])
    return status


def next_seminar_date():
    """開催予定日(SEMINAR_SLOT_DISPLAY)のうち、今日以降で一番近いものを返す。
    全て過ぎていれば最後の開催日を返す(表示上の保険)。"""
    dates = [
        datetime.date(FIRST_SEMINAR_DATE.year, *(int(x) for x in key.split("/")))
        for key, _ in SEMINAR_SLOT_DISPLAY
    ]
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


def build_report(m, target_date, stats, slot_status, key=None):
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
            count, remain = slot_status.get(date_key, ("—", "—"))
            lines.append(f"・{date_display}")
            lines.append(f" : 予約 {count}名 / 残 {remain}席（限定8枠）")

    lines.append("")
    lines.append("数値レポートはこちら▼")
    lines.append(SPREADSHEET_URL)

    return "\n".join(lines)


def col_letter(idx0):
    letters = ""
    n = idx0 + 1
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def date_to_col_idx0(d):
    return DATE_COL_START - 1 + (d - SHEET_DATE_ORIGIN).days


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
    # ntfyのヘッダーは非ASCIIを扱いにくいため、タイトルは英語ASCIIのみにし、
    # 日本語の本文はリクエストボディ(UTF-8)側に入れる
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
        headers={"Title": title, "Priority": priority},
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp.read()
        print("  [info] ntfy通知(iPhone)を送信しました")
    except Exception as e:
        print(f"  [warn] ntfy通知の送信に失敗: {e}")


def find_missing_dates(ws, start_date, end_date):
    """PROMO_START〜end_dateの範囲でrow11(LP_PV合計累計)が空欄の日付を全て返す"""
    if start_date > end_date:
        # PROMO_START(起点)がまだ来ていない場合(本番前のテスト期間など)は何もしない
        return []
    start_idx0 = date_to_col_idx0(start_date)
    end_idx0 = date_to_col_idx0(end_date)
    start_col = col_letter(start_idx0)
    end_col = col_letter(end_idx0)
    row_num = ROW["lp_pv_all_cum"]
    values = with_retry(lambda: ws.get(f"{start_col}{row_num}:{end_col}{row_num}"))
    flat = values[0] if values else []
    missing = []
    for i, offset in enumerate(range((end_date - start_date).days + 1)):
        d = start_date + datetime.timedelta(days=offset)
        val = flat[i] if i < len(flat) else ""
        if str(val).strip() == "":
            missing.append(d)
    return missing


def normalize_value(v):
    """シート上の表示形式差(カンマ・円マーク・%等)を無視して数値比較するための正規化"""
    s = str(v).replace(",", "").replace("¥", "").replace("%", "").strip()
    try:
        return float(s)
    except (ValueError, TypeError):
        return s


def read_current_row_values(ws, target_date):
    """target_dateの列について、書き込み前時点でのROW各項目の現在値を返す(比較用)"""
    col = col_letter(date_to_col_idx0(target_date))
    row_first = min(ROW.values())
    row_last = max(ROW.values())
    values = with_retry(lambda: ws.get(f"{col}{row_first}:{col}{row_last}"))
    flat = [(v[0] if v else "") for v in values] if values else []
    return {
        name: (flat[row_num - row_first] if row_num - row_first < len(flat) else "")
        for name, row_num in ROW.items()
    }


def write_date(ws, key, target_date):
    """1日分のデータを取得してシートに書き込む。結果と警告を返す。"""
    m = fetch_metrics(key, target_date)

    # セミナー予約数はイベント申込者APIを正とする。
    # ファネル統計側の registration_count は予約ページのフォーム登録数であり、
    # キャンセルも日程変更も反映されないため実態と食い違っていた(2026-08-30変更)。
    try:
        stats = fetch_seminar_stats(key, SEM_EVENT_PROJECT_ID, target_date)
        m["sem_cum"] = stats["booked"]["all"]
        m["sem_day"] = stats["booked_day"]
        m["sem_rate"] = (round(stats["booked"]["all"] / m["reg_all_cum"], 4)
                         if m.get("reg_all_cum") else "")
        m["_sem_stats"] = stats
    except Exception as e:
        print(f"  [warn] セミナー予約集計に失敗。ファネル統計の値のまま書き込みます: {e}")

    col_idx0 = date_to_col_idx0(target_date)
    col = col_letter(col_idx0)

    cell_updates = {ROW[k]: m[k] for k in list(ROW.keys()) if k in m}

    print(f"target_date={target_date} column={col}")

    # 安全確認①: 列の見出しが本当にその日付か検証する
    expected_label = f"{target_date.month}/{target_date.day}"
    actual_label = with_retry(lambda: ws.acell(f"{col}9").value)
    if (actual_label or "").strip() != expected_label:
        raise RuntimeError(
            f"列の見出しが想定と違います。書き込み中止。"
            f"想定列={col} 期待={expected_label} 実際={actual_label!r}"
        )

    warnings = []

    # 前日列の値は1回のリクエストでまとめて読む。
    # 以前は項目ごとに acell() を呼んでおり1実行で30回以上の読み取りが発生し、
    # Google Sheets APIの分あたりクォータに引っかかっていた(2026-08-30改善)。
    row_first, row_last = min(ROW.values()), max(ROW.values())
    prev_col = col_letter(col_idx0 - 1)
    prev_raw_rows = with_retry(lambda: ws.get(f"{prev_col}{row_first}:{prev_col}{row_last}"))
    prev_flat = [(r[0] if r else "") for r in prev_raw_rows] if prev_raw_rows else []

    def prev_of(row_num):
        i = row_num - row_first
        return prev_flat[i] if 0 <= i < len(prev_flat) else ""

    # 安全確認②: 累計が前日より減っていないか
    # 1〜2件の減少はUTAGE側のデータ修正等でも起こり得るため警告のみ。
    # 半数以上が同時に減少している場合は取得側の不具合(範囲指定ミス等)の可能性が高いため書き込み自体を中止する。
    decreased = []
    for key_name in CUM_ROWS:
        row_num = ROW[key_name]
        prev_raw = prev_of(row_num)
        try:
            prev_val = float(str(prev_raw).replace(",", "").replace("¥", "")) if prev_raw not in (None, "") else 0
        except ValueError:
            prev_val = None
        new_val = cell_updates.get(row_num)
        if prev_val is not None and isinstance(new_val, (int, float)) and new_val < prev_val:
            decreased.append(f"{target_date} {key_name}: 前日({prev_val})→今日({new_val})に減少")

    if len(decreased) > len(CUM_ROWS) / 2:
        raise RuntimeError(
            f"累計の{len(decreased)}/{len(CUM_ROWS)}項目が同時に前日より減少しています。"
            f"取得データがおかしい可能性が高いため書き込みを中止します: {decreased}"
        )
    warnings.extend(decreased)

    # 安全確認③: 日別の値が前日比で極端に跳ねていないか(目安: 8倍以上かつ絶対値もそこそこ大きい)
    for key_name in DAY_ROWS:
        row_num = ROW[key_name]
        prev_raw = prev_of(row_num)
        try:
            prev_val = float(str(prev_raw).replace(",", "").replace("¥", "")) if prev_raw not in (None, "") else 0
        except ValueError:
            prev_val = 0
        new_val = m.get(key_name, 0)
        if isinstance(new_val, (int, float)) and new_val > 20 and prev_val > 0 and new_val > prev_val * 8:
            warnings.append(f"{target_date} {key_name}: 前日({prev_val})の8倍以上に急増({new_val}) 要確認")

    # ROWは11〜63の連番なので、列まるごと1回のリクエストで書ける。
    # 以前はセルごとに update_acell() を呼んでおり53回の書き込みになっていた。
    # 列一括書き込みは「値が用意できなかった行」を空にしてしまうため、
    # 取得できなかった項目がある場合だけ現在値を読んで温存する。
    missing_rows = [r for r in range(row_first, row_last + 1) if r not in cell_updates]
    keep = {}
    if missing_rows:
        print(f"  [warn] 値を取得できなかった行があります(現在値を残します): {missing_rows}")
        cur = with_retry(lambda: ws.get(f"{col}{row_first}:{col}{row_last}"))
        for idx, r in enumerate(range(row_first, row_last + 1)):
            row_vals = cur[idx] if idx < len(cur) else []
            keep[r] = row_vals[0] if row_vals else ""
    column_values = [[cell_updates.get(r, keep.get(r, ""))]
                     for r in range(row_first, row_last + 1)]
    with_retry(lambda: ws.update(values=column_values,
                                 range_name=f"{col}{row_first}:{col}{row_last}",
                                 value_input_option="USER_ENTERED"))

    print(f"  書き込み完了: {col}列（{target_date}）")
    return m, warnings


def write_summary(ws, m, target_date, stats):
    """期間累計サマリー(行5〜7)を更新する。列は行5のグループ名+行6の指標名で探すため、
    列を挿入せず空き列にラベルを足すだけで新しい指標を追加できる。
    (この行はデータ行と列を共有しているので、列の挿入は絶対にしないこと。
     挿入すると行9以降の日付列が全部ずれる。
     またI5:W7には結合セルがあり、結合の先頭以外のセルは書き込みが無視される。
     指標を足すときは結合の外側=X列以降に「行5=グループ名 / 行6=指標名」を置くこと)"""
    row5 = with_retry(lambda: ws.row_values(5))
    row6 = with_retry(lambda: ws.row_values(6))
    summary_col = {}
    current_group = None
    max_len = max(len(row5), len(row6))
    for i in range(6, max_len):
        group = row5[i].strip() if i < len(row5) and row5[i].strip() else current_group
        current_group = group
        metric = row6[i].strip() if i < len(row6) else ""
        if not metric:
            continue
        summary_col[f"{group}:{metric}"] = col_letter(i)

    booked = stats["booked"]["all"]
    cancelled = stats["cancelled"]["all"]
    attended = stats["attended"]

    def rate(n, d):
        return round(n / d, 4) if d else ""

    summary_by_label = {
        "LP:PV": m["lp_pv_all_cum"], "LP:UU": m["lp_uu_all_cum"],
        "LP:LP登録数": m["reg_all_cum"], "LP:LP登録率": m["regrate_all"],
        "セミナー:予約数": booked,
        "セミナー:予約率": rate(booked, m.get("reg_all_cum")),
        "セミナー:キャンセル数": cancelled,
        "セミナー:参加数": attended,
        # 参加率 = 参加数 ÷ 開催済み枠の実予約数(開催前の枠は分母に入れない)
        "セミナー:参加率": rate(attended, stats.get("booked_finished")),
        "個別相談会:予約数": m["ind_cum"],
        "個別相談会:予約率": rate(m["ind_cum"], attended),
        "本講座:申込数": m["apply_cum"], "本講座:成約数": m["sale_cum"],
        "本講座:成約率": m["sale_rate"], "本講座:売上金額": m["amount_cum"],
    }

    missing = []
    batch = [{"range": "I4",
              "values": [[f"期間累計サマリー（{target_date.month}/{target_date.day}時点）"]]}]
    for label, value in summary_by_label.items():
        cell_col = summary_col.get(label)
        if not cell_col:
            missing.append(label)
            continue
        batch.append({"range": f"{cell_col}7", "values": [[value]]})
    with_retry(lambda: ws.batch_update(batch, value_input_option="USER_ENTERED"))
    if missing:
        print(f"  [warn] サマリー列が見つからず書き込めなかった項目: {missing}")


def write_agg_route_block(sh, stats, target_date):
    """「集計」タブに経路別の 予約数 / キャンセル数 / 申込数 を書く。
    既存のA1:C13(LPオプト・日程別)には触らず、A15から下に独立したブロックを作る。"""
    ws = with_retry(lambda: sh.worksheet(AGG_SHEET_NAME))
    r = AGG_ROUTE_ROW
    b, c, a = stats["booked"], stats["cancelled"], stats["applied"]
    note = (f"※{target_date.month}/{target_date.day}時点／日程変更は1名1件に名寄せ済み"
            f"／キャンセルは申込日に遡って反映されます")
    if stats.get("unmatched"):
        note += f"／流入元不明 {stats['unmatched']}名は「すべて」のみ計上"
    values = [
        ["■ セミナー予約 経路別（UTAGE自動更新・手入力しないでください）", "", "", ""],
        ["", "すべて", "セミナーLP", "広告LP"],
        ["予約数(累計)", b["all"], b["organic"], b["ad"]],
        ["キャンセル数", c["all"], c["organic"], c["ad"]],
        ["申込数(合計)", a["all"], a["organic"], a["ad"]],
        [note, "", "", ""],
    ]
    with_retry(lambda: ws.update(values=values, range_name=f"A{r}:D{r + 5}",
                                 value_input_option="USER_ENTERED"))
    print(f"  集計タブ A{r}:D{r + 5} を更新しました "
          f"(予約{b['all']} / キャンセル{c['all']} / 申込{a['all']})")


def write_agg_slot_counts(sh, stats):
    """「集計」タブの日程別 件数(B9:B13)を、UTAGEの実予約数で更新する。

    従来はCOUNTIFで生データ「セミナー予約リスト」の行を数えていたが、
    日程変更した人の旧日程の行が残るため水増しされていた(8/28が実測7名に対し11行)。
    実際にB11は数式が消され「8」が直接入力されていた。UTAGE側を正として書き直す。"""
    ws = with_retry(lambda: sh.worksheet(AGG_SHEET_NAME))
    labels = with_retry(lambda: ws.get("A9:A13", value_render_option="UNFORMATTED_VALUE"))
    per_slot = stats.get("per_slot") or {}
    epoch = datetime.date(1899, 12, 30)
    written, unknown, slot_batch = [], [], []
    for i, row in enumerate(labels):
        raw = row[0] if row else ""
        if isinstance(raw, (int, float)) and raw:
            d = (epoch + datetime.timedelta(days=int(raw))).isoformat()
        else:
            unknown.append(raw)
            continue
        if d not in per_slot:
            unknown.append(d)
            continue
        slot_batch.append({"range": f"B{9 + i}", "values": [[per_slot[d]]]})
        written.append(f"{d}={per_slot[d]}")
    if slot_batch:
        with_retry(lambda: ws.batch_update(slot_batch, value_input_option="USER_ENTERED"))
    print(f"  集計タブ 日程別件数を更新: {', '.join(written)}")
    if unknown:
        print(f"  [warn] 集計タブの日程行と突き合わなかったもの: {unknown}")
    extra = [d for d in per_slot if d not in [w.split("=")[0] for w in written]]
    if extra:
        print(f"  [warn] シートに行が無い開催日があります(A9:A13に追加してください): {extra}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD (default: yesterday)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--promo-start", help="テスト用: 累計の起点日を上書き (YYYY-MM-DD)")
    ap.add_argument("--no-backfill", action="store_true", help="指定日のみ処理し、抜け日を探さない")
    ap.add_argument("--no-notify", action="store_true", help="ChatWork/ntfyへ送信せず内容を表示するだけ")
    args = ap.parse_args()

    if args.date:
        target_date = datetime.date.fromisoformat(args.date)
    else:
        target_date = datetime.date.today() - datetime.timedelta(days=1)

    global PROMO_START, NOTIFY_ENABLED
    if args.no_notify:
        NOTIFY_ENABLED = False
    if args.promo_start:
        PROMO_START = datetime.date.fromisoformat(args.promo_start)

    if target_date < PROMO_START:
        print(f"target_date({target_date}) が PROMO_START({PROMO_START}) より前なので、"
              f"まだプロモ期間に入っていません。何もせず終了します。"
              f"（テスト目的なら --promo-start で起点を上書きしてください）")
        return

    with open(UTAGE_KEY_PATH) as f:
        key = f.read().strip()

    if args.dry_run:
        m = fetch_metrics(key, target_date)
        stats = fetch_seminar_stats(key, SEM_EVENT_PROJECT_ID, target_date)
        m["sem_cum"] = stats["booked"]["all"]
        m["sem_day"] = stats["booked_day"]
        m["sem_rate"] = (round(stats["booked"]["all"] / m["reg_all_cum"], 4)
                         if m.get("reg_all_cum") else "")
        print(f"target_date={target_date}")
        for name, row in sorted(ROW.items(), key=lambda kv: kv[1]):
            print(f"  row{row:>2} {name:<16} = {m.get(name)}")
        b, c, a = stats["booked"], stats["cancelled"], stats["applied"]
        print("\n  [集計タブ 経路別ブロック]")
        print(f"    {'':<14}{'すべて':>8}{'セミナーLP':>12}{'広告LP':>10}")
        print(f"    {'予約数(累計)':<14}{b['all']:>8}{b['organic']:>12}{b['ad']:>10}")
        print(f"    {'キャンセル数':<14}{c['all']:>8}{c['organic']:>12}{c['ad']:>10}")
        print(f"    {'申込数(合計)':<14}{a['all']:>8}{a['organic']:>12}{a['ad']:>10}")
        print(f"    参加数={stats['attended']} 流入元不明={stats['unmatched']}")
        print(f"    日程別実予約={stats['per_slot']}")
        print("\n[dry-run] シートへの書き込みは行いません")
        return

    gc = with_retry(lambda: gspread.service_account(filename=SERVICE_ACCOUNT_PATH))
    sh = with_retry(lambda: gc.open_by_key(SPREADSHEET_ID))
    ws = with_retry(lambda: sh.worksheet(SHEET_NAME))

    # 本日すでに正常終了済みなら(=6:30が成功していれば)、8:00は無音でスキップする
    run_marker_path = os.path.join(CONFIG_DIR, "last_run_ok_date.txt")
    today_str = datetime.date.today().isoformat()
    if not args.dry_run and not args.no_backfill:
        try:
            with open(run_marker_path) as f:
                last_ok = f.read().strip()
        except FileNotFoundError:
            last_ok = None
        if last_ok == today_str:
            print(f"本日({today_str})は既に正常終了済みのため、今回は何もせず終了します（通知なし）。")
            return

    # 前日より前の空欄日(取りこぼし)は従来通りバックフィル
    if args.no_backfill:
        older_missing = []
    else:
        older_missing = [d for d in find_missing_dates(ws, PROMO_START, target_date) if d < target_date]
        older_missing.sort()

    succeeded = []
    failed = []
    all_warnings = []
    last_m = None
    backfilled = []

    for d in older_missing:
        try:
            m, warnings = write_date(ws, key, d)
            succeeded.append(d)
            all_warnings.extend(warnings)
            last_m = m
            backfilled.append(d)
        except Exception as e:
            print(f"  [error] {d} の処理に失敗: {e}")
            failed.append((d, str(e)))

    # 前日は毎回「最新値になっているか」を確認し、必要なら上書きする
    prev_values = read_current_row_values(ws, target_date)
    was_blank = all(str(v).strip() == "" for v in prev_values.values())
    target_status = None
    changed_fields = []
    try:
        m, warnings = write_date(ws, key, target_date)
        succeeded.append(target_date)
        all_warnings.extend(warnings)
        last_m = m
        if was_blank:
            target_status = "filled"
        else:
            compare_keys = CUM_ROWS + DAY_ROWS
            changed_fields = [
                name for name in compare_keys
                if normalize_value(prev_values.get(name, "")) != normalize_value(m.get(name, ""))
            ]
            target_status = "corrected" if changed_fields else "up_to_date"
    except Exception as e:
        print(f"  [error] {target_date} の処理に失敗: {e}")
        failed.append((target_date, str(e)))
        target_status = "error"

    if last_m is not None:
        report_date = max(succeeded)
        # write_date が対象日の集計を既に取っていればそれを使い、無ければ取り直す
        stats = last_m.get("_sem_stats")
        if stats is None:
            try:
                stats = fetch_seminar_stats(key, SEM_EVENT_PROJECT_ID, report_date)
            except Exception as e:
                print(f"  [warn] セミナー予約集計の取得に失敗: {e}")

        if stats is not None:
            try:
                write_agg_slot_counts(sh, stats)
            except Exception as e:
                print(f"  [error] 集計タブの日程別件数の更新に失敗: {e}")
                failed.append(("集計:日程別件数", str(e)))
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
        lines.append("❌ 失敗:")
        for d, err in failed:
            lines.append(f"  - {d}: {err}")
    if all_warnings:
        lines.append("⚠️ 要確認:")
        for w in all_warnings:
            lines.append(f"  - {w}")

    message = "\n".join(lines)
    print("\n" + message)
    notify_chatwork(message)

    if failed:
        notify_ntfy("UTAGE sync FAILED", message, priority="urgent")
    elif all_warnings:
        notify_ntfy("UTAGE sync - warning", message, priority="high")
    elif target_status == "corrected":
        notify_ntfy("UTAGE sync - corrected", message, priority="high")
    else:
        notify_ntfy("UTAGE sync OK", message, priority="default")

    if not failed:
        try:
            with open(run_marker_path, "w") as f:
                f.write(today_str)
        except Exception as e:
            print(f"  [warn] 実行マーカーの書き込みに失敗: {e}")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
