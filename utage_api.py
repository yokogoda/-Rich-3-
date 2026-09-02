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
    PAY_FUNNEL,
    PAY_STEP_APPLY,
    PAY_STEP_SALE,
    PROMO_START,
    SEM_FUNNEL,
    SEM_LP_COUNT_START,
    SEM_STEP_INDIVIDUAL,
    SEM_STEP_SEMINAR,
    WEBINAR_AD_PAGE_IDS,
    WEBINAR_LP_COUNT_START,
    WEBINAR_LP_PAGE_IDS,
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
    attended = sum(1 for a in applicants if a.get("status_participation") == "attended")

    per_slot = {}
    for a in applicants:
        if a.get("status_participation") not in ACTIVE_STATUSES:
            continue
        start = (a.get("schedule") or {}).get("start_datetime") or ""
        if start:
            per_slot[start[:10]] = per_slot.get(start[:10], 0) + 1

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
                      {"page_ids": ",".join(WEBINAR_AD_PAGE_IDS), "date_from": WEBINAR_AD_PAGE_IDS, "date_to": date_to}),
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
