#!/usr/bin/env python3
"""
愛されRich美女3期 UTAGE自動更新システム - UTAGE API通信・データ集計モジュール (utage_api.py)
"""
import datetime
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from config import (
    ACTIVE_STATUSES,
    ATTR_CACHE_PATH,
    CONFIG_DIR,
    LINE_ACCOUNT_ID,
    LP_FUNNEL,
    LP_PAGE_AD_IDS,
    LP_PAGE_SEMINAR_IDS,
    PAY_APPLY_EXCEPTIONS,
    PAY_APPLY_PAGE_ID,
    PAY_FUNNEL,
    PAY_SALE_STEP_IDS,
    PROMO_START,
    SEM_FUNNEL,
    SEM_LP_COUNT_START,
    SEM_STEP_INDIVIDUAL,
    SEM_STEP_SEMINAR,
    TEST_MAIL_LOCALPARTS,
    WEBINAR_AD_PAGE_IDS,
    WEBINAR_FUNNEL,
    WEBINAR_LABELS,
    WEBINAR_LP_COUNT_START,
    WEBINAR_LP_PAGE_IDS,
    WEBINAR_RESERVE_PAGE_ID,
)


def load_applicant_attributions_cache():
    if os.path.exists(ATTR_CACHE_PATH):
        try:
            with open(ATTR_CACHE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"  [warn] キャッシュ読み込み失敗: {e}")
    return {}


def save_applicant_attributions_cache(cache):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(ATTR_CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)


def utage_get(key, path, params=None, retries=5, backoff=5):
    params = params or {}
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    url = f"https://api.utage-system.com/v1{path}?{qs}" if qs else f"https://api.utage-system.com/v1{path}"
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


def fetch_line_friends(key, account_id):
    """LINEアカウントの友だち一覧を全件取得する。
    LP登録者(subscribers)とセミナー申込者(event applicants)はID体系が異なり直接は結合できない
    (subscriber.id と applicant.line_friend.id は1件も重ならないことを実測で確認済み)。
    友だちの picture_url を仲介にすることで
    「LP登録者 → LINE友だち → セミナー申込者」を厳密なID一致で繋げる(2026-08-30)。"""
    friends = []
    page = 1
    while True:
        data = utage_get(key, f"/accounts/{account_id}/line/friends", {"page": page, "per_page": 100})
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
    registrants = []
    for pid in page_ids:
        page = 1
        while True:
            data = utage_get(key, f"/funnels/{funnel_id}/subscribers", {"page_id": pid, "page": page, "per_page": 100})
            rows = data.get("data", [])
            for r in rows:
                r["_source_page_id"] = pid
            registrants.extend(rows)
            meta = data.get("meta", {})
            if page * meta.get("per_page", 100) >= meta.get("total", 0) or not rows:
                break
            page += 1
    return registrants


def fetch_seminar_applicants(key, event_project_id):
    applicants = []
    page = 1
    while True:
        data = utage_get(key, f"/events/{event_project_id}/applicants", {"page": page, "per_page": 100})
        rows = data.get("data", [])
        applicants.extend(rows)
        meta = data.get("meta", {})
        if page * meta.get("per_page", 100) >= meta.get("total", 0) or not rows:
            break
        page += 1
    return applicants


def build_attribution_index(key):
    """流入元判定用の対応表を作る。
    attr は "organic"(通常LP=セミナーLP) / "ad"(広告LP)。
    同一人物が両方のLPに登録していた場合は先に登録した方を採用する。
    friend_id で引けなかった場合(LINEアイコン未設定・変更後など)に備えて
    表示名の対応表も併せて返し、フォールバックに使う。"""
    org_subs = fetch_lp_registrants(key, LP_FUNNEL, LP_PAGE_SEMINAR_IDS)
    ad_subs = fetch_lp_registrants(key, LP_FUNNEL, LP_PAGE_AD_IDS)

    by_pic = {}
    for s in org_subs + ad_subs:
        pic = s.get("line_picture_url")
        if not pic:
            continue
        attr = "ad" if s["_source_page_id"] in LP_PAGE_AD_IDS else "organic"
        cdate = s.get("created_at") or ""
        prev = by_pic.get(pic)
        if prev is None or cdate < prev[1]:
            by_pic[pic] = (attr, cdate)

    friends = fetch_line_friends(key, LINE_ACCOUNT_ID)
    by_fid = {}
    for f in friends:
        fid = f.get("id")
        pic = f.get("picture_url")
        if fid and pic and pic in by_pic:
            by_fid[fid] = by_pic[pic]

    by_name = {}
    for s in org_subs + ad_subs:
        name = (s.get("line_display_name") or s.get("name") or "").strip()
        if not name:
            continue
        attr = "ad" if s["_source_page_id"] in LP_PAGE_AD_IDS else "organic"
        cdate = s.get("created_at") or ""
        prev = by_name.get(name)
        if prev is None or cdate < prev[1]:
            by_name[name] = (attr, cdate)

    return by_fid, by_name


def fetch_seminar_stats(key, event_project_id, target_date):
    """セミナーの申込・キャンセル・実予約・参加を経路別に集計する。
    数え方(2026-08-30に全面見直し。広告会社へのCV実測の要請がきっかけ。★崩さないこと★):
    1. 1人1件に名寄せする。UTAGEは日程変更のたびに「旧日程=cancel_changed」と
       「新日程=reserved」の2レコードを残すため、そのまま数えると二重計上になる。
       メールアドレス単位でまとめ、申込日は最も古いレコードの created_at を採用する。
    2. 有効な予約が1件も残っていない人だけを「キャンセル」とする。
       日程変更しただけの人はキャンセルに数えない。
    3. 累計は target_date までに申し込んだ人だけを数える。これを忘れると
       過去日を再実行したとき全列が現在値で塗り潰される。"""
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
            continue
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
    attended_keys = {"all": 0, "organic": 0, "ad": 0}
    booked_finished_keys = {"all": 0, "organic": 0, "ad": 0}

    for a in applicants:
        sched_dt = ((a.get("schedule") or {}).get("start_datetime") or "")[:10] or "9999-12-31"
        status = a.get("status_participation")
        attr = cache.get(a.get("id"), {}).get("attr", "unmatched")
        if attr not in ("organic", "ad"):
            attr = None

        if status in ACTIVE_STATUSES and sched_dt <= target_str:
            booked_finished_keys["all"] += 1
            if attr:
                booked_finished_keys[attr] += 1

        if status == "attended" and sched_dt <= target_str:
            attended_keys["all"] += 1
            if attr:
                attended_keys[attr] += 1

    attended = attended_keys["all"]
    booked_finished = booked_finished_keys["all"]

    no_slot_attended = sum(
        1 for a in applicants
        if a.get("status_participation") == "attended"
        and not ((a.get("schedule") or {}).get("start_datetime") or "")
    )
    if no_slot_attended:
        print(f"  [warn] 枠日付が無い参加済みレコードを{no_slot_attended}件、参加数から除外しました")

    per_slot = {}
    for a in applicants:
        if a.get("status_participation") not in ACTIVE_STATUSES:
            continue
        start = (a.get("schedule") or {}).get("start_datetime") or ""
        if start:
            per_slot[start[:10]] = per_slot.get(start[:10], 0) + 1

    if unmatched:
        print(f"  [info] 流入元を特定できなかった予約者: {unmatched}名 {unmatched_names}")

    return {
        "booked": booked, "cancelled": cancelled, "applied": applied,
        "booked_day": booked_day, "applied_day": applied_day,
        "attended": attended, "per_slot": per_slot,
        "booked_finished": booked_finished,
        "attended_by_attr": attended_keys,
        "booked_finished_by_attr": booked_finished_keys,
        "unmatched": unmatched,
    }


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


def fetch_funnel_subscribers(key, funnel_id, page_id):
    """ファネルの1ページの登録者を全件取得する。"""
    out, page = [], 1
    while True:
        data = utage_get(key, f"/funnels/{funnel_id}/subscribers",
                         {"page_id": page_id, "per_page": 100, "page": page})
        rows = data.get("data", []) or []
        out.extend(rows)
        if len(rows) < 100:
            return out
        page += 1


def is_test_mail(mail):
    if not mail:
        return True
    return mail.split("@")[0].split("+")[0] in TEST_MAIL_LOCALPARTS


def count_course_applications(key, target_date):
    """本講座申込数(累計, 日別)。申込フォームの登録者＋特例の人を、メールで名寄せして初回登録日で数える。
    本番モノリス(~/.config/utage-pdca/sync_daily.py)と同じロジック。変えるときは両方を同時に直すこと。"""
    target_str = target_date.isoformat()
    sources = [(PAY_APPLY_PAGE_ID, None)] + list(PAY_APPLY_EXCEPTIONS.items())
    first = {}
    blank_today = 0
    for page_id, allowed in sources:
        for r in fetch_funnel_subscribers(key, PAY_FUNNEL, page_id):
            mail = (r.get("mail") or "").strip().lower()
            d = (r.get("created_at") or "")[:10]
            if allowed is None and not mail and d == target_str:
                blank_today += 1
            if is_test_mail(mail) or (allowed is not None and mail not in allowed):
                continue
            if not d or d < PROMO_START.isoformat() or d > target_str:
                continue
            if mail not in first or d < first[mail]:
                first[mail] = d
    warns = []
    if blank_today:
        warns.append(f"{target_str} 本講座申込フォームにメールが空の登録が{blank_today}件あり、申込数から外しました。本物の申込でないか確認してください")
    return len(first), sum(1 for d in first.values() if d == target_str), warns


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
    sale_pages = [p for step in pay_data.get("data", [])
                  if step.get("step_id") in PAY_SALE_STEP_IDS
                  for p in step.get("pages", [])]

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
    m["apply_cum"], m["apply_day"], pay_warnings = count_course_applications(key, target_date)
    m["sale_cum"] = sum_cum(sale_pages, "sale_count"); m["sale_day"] = sum_day(sale_pages, "sale_count")
    m["amount_cum"] = sum_cum(sale_pages, "sale_amount"); m["amount_day"] = sum_day(sale_pages, "sale_amount")
    # 一覧に無いステップで成約が出たら知らせる(一覧から漏れると売上が黙って0になるため)
    for step in pay_data.get("data", []):
        n = sum(p.get("totals", {}).get("sale_count", 0) for p in step.get("pages", []))
        if n and step.get("step_id") not in PAY_SALE_STEP_IDS:
            pay_warnings.append(f"PAY_SALE_STEP_IDSに無い「{step.get('step_name')}」({step.get('step_id')})で成約{n}件。成約・売上に入っていません")
    # 成約が申込を上回るのは、申込フォームを通らない決済が出たとき(9/12の松田様と同じ形)
    if m["sale_cum"] > m["apply_cum"]:
        pay_warnings.append(f"本講座の成約{m['sale_cum']}件が申込{m['apply_cum']}名を上回っています。申込フォームを通らない決済が無いか確認してください")
    for w in pay_warnings:
        print(f"  [warn] {w}")
    m["_warnings"] = pay_warnings

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


# ---------------------------------------------------------------------------
# ウェビナー予約・視聴（2026-09-15に本番モノリス ~/.config/utage-pdca/sync_daily.py から移植）
#
# 移植前は岡安のMacの本番コードにしか無く、行32〜41は片方のMacだけが書く行だった。
# ロジックは本番と1文字も変えていない。変えるときは両方を同時に直すこと。
# ---------------------------------------------------------------------------

def fetch_webinar_subscribers(key):
    """ウェビナー予約ページ①の登録者を全件取得する(1予約1レコード)。"""
    out, page = [], 1
    while True:
        data = utage_get(key, f"/funnels/{WEBINAR_FUNNEL}/subscribers",
                         {"page_id": WEBINAR_RESERVE_PAGE_ID, "per_page": 100, "page": page})
        rows = data.get("data", []) or []
        out.extend(rows)
        if len(rows) < 100:
            return out
        page += 1


def fetch_label_readers(key, account_id, label_id):
    """指定ラベルを持つ読者行を全件返す。

    ★戻り値は「読者行」であって人数ではない。同じ人が複数シナリオに行を持つため、
    meta.totalをそのまま使うと実測で3〜11倍に膨らむ。common_reader_idで名寄せすること。
    """
    conditions = json.dumps(
        [{"rules": [{"key": "label", "condition": "including", "value": [label_id]}]}],
        ensure_ascii=False)
    # utage_get はクエリをエスケープせずに連結するので、ここで encode しておく
    encoded = urllib.parse.quote(conditions, safe="")
    out, page = [], 1
    while True:
        data = utage_get(key, f"/accounts/{account_id}/readers",
                         {"conditions": encoded, "per_page": 100, "page": page})
        rows = data.get("data", []) or []
        out.extend(rows)
        if len(rows) < 100:
            return out
        page += 1


def _reader_mails(reader):
    mails = set()
    for group in ("scenario_fields", "common_fields"):
        v = (reader.get(group) or {}).get("mail")
        if v:
            mails.add(v.strip().lower())
    return mails


def fetch_webinar_stats(key, target_date, include_labels):
    """ウェビナーの予約数(subscriber)と視聴状況(ラベル)を集計する。

    ■ 予約数
    予約ページ①のsubscriberを created_at で絞る。起点は WEBINAR_LP_COUNT_START。
    同じ人が複数回予約することがあるのでメールで名寄せし、「初回予約日」でその人を数える。
    こうすると日別を足し上げた数が累計とぴったり一致する。

    ■ 視聴状況
    ラベルは「今の状態」しか持たず日付で絞れない。そのまま数えると、掃除し忘れた
    テスト読者が混ざる(2026-09-11に実際に「視聴済1人」が全部テストだった)。
    そこで「対象期間に予約した人」に限定して数える。視聴できるのは予約した人だけなので
    定義としても正しく、テストの取りこぼしも自動で落ちる。

    include_labels が False のとき、視聴状況は集計しない(キー自体を返さない)。
    """
    subs = fetch_webinar_subscribers(key)

    first_booked = {}   # mail -> 初回予約日
    for s in subs:
        mail = (s.get("mail") or "").strip().lower()
        created = (s.get("created_at") or "")[:10]
        if not mail or not created:
            continue
        try:
            d = datetime.datetime.strptime(created, "%Y-%m-%d").date()
        except ValueError:
            continue
        if d < WEBINAR_LP_COUNT_START or d > target_date:
            continue
        if mail not in first_booked or d < first_booked[mail]:
            first_booked[mail] = d

    out = {
        "book_cum": len(first_booked),
        "book_day": sum(1 for d in first_booked.values() if d == target_date),
    }
    if not include_labels:
        return out

    booked_mails = set(first_booked)
    cid_mails = {}      # common_reader_id -> メール集合
    label_cids = {}     # ラベル種別 -> common_reader_id集合
    for name, label_id in WEBINAR_LABELS.items():
        cids = set()
        for r in fetch_label_readers(key, LINE_ACCOUNT_ID, label_id):
            cid = r.get("common_reader_id") or r.get("id")
            if not cid:
                continue
            cids.add(cid)
            mails = _reader_mails(r)
            if mails:
                cid_mails.setdefault(cid, set()).update(mails)
        label_cids[name] = cids

    booked_cids = {cid for cid, mails in cid_mails.items() if mails & booked_mails}
    for name, cids in label_cids.items():
        out[f"lab_{name}"] = len(cids & booked_cids)
    return out


def apply_webinar_metrics(m, key, target_date, force_labels=False):
    """ウェビナーの予約数・視聴状況を m に足す。書き込み系とdry-runの両方から呼ぶ。

    ★ラベル由来(視聴開始/視聴完了/途中離脱/未視聴)は「今の状態」しか取れないため、
      対象日が前日のときだけ書く。バックフィルで過去の列に書くと、例えば9/20に9/12の列を
      埋め直したときに「9/20時点の視聴完了数」が9/12の列に入る(参加率のas-of漏れと同種の事故)。
      subscriber由来の予約数は created_at で絞れるのでこの問題がなく、常に書いてよい。
      force_labels はdry-run専用(シートに書かないので、翌朝出る値を先に見るために使う)。

    ラベル由来のキーを m に入れなかった日は、sheets_client.write_date() が
    その行の今の値を書き戻すので、前日に書いた視聴状況が空欄で消えることはない。
    """
    if target_date < WEBINAR_LP_COUNT_START:
        return
    is_yesterday = target_date == datetime.date.today() - datetime.timedelta(days=1)
    include_labels = is_yesterday or force_labels
    try:
        w = fetch_webinar_stats(key, target_date, include_labels=include_labels)
    except Exception as e:
        print(f"  [warn] ウェビナー予約・視聴の集計に失敗。該当行は書きません: {e}")
        return

    m["web_book_cum"] = w["book_cum"]
    m["web_book_day"] = w["book_day"]
    m["web_bookrate"] = (round(w["book_cum"] / m["web_reg_all_cum"], 4)
                         if m.get("web_reg_all_cum") else "")
    if not include_labels:
        print("  [info] 対象日が前日ではないため、ウェビナー視聴状況(ラベル由来)は書きません")
        return

    m["web_lab_apply"] = w["lab_apply"]
    m["web_lab_start"] = w["lab_start"]
    m["web_lab_done"] = w["lab_done"]
    m["web_lab_dropout"] = w["lab_dropout"]
    m["web_lab_noshow"] = w["lab_noshow"]
    # 視聴率の分母は subscriber由来の予約実人数(行32)。ラベル「申込」(行35)ではない。
    # 行35は「ラベルが取りこぼしていないか」を目視で検算するために並べてある。
    denom = w["book_cum"]
    m["web_startrate"] = round(w["lab_start"] / denom, 4) if denom else ""
    m["web_donerate"] = round(w["lab_done"] / denom, 4) if denom else ""
