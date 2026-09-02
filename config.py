#!/usr/bin/env python3
"""
愛されRich美女3期 UTAGE自動更新システム - 設定・定数モジュール (config.py)
"""
import datetime
import os

CONFIG_DIR = os.path.expanduser("~/.config/utage-pdca")
ATTR_CACHE_PATH = os.path.join(CONFIG_DIR, "seminar_applicant_attributions.json")
LAST_RUN_OK_PATH = os.path.join(CONFIG_DIR, "last_run_ok_date.txt")

SPREADSHEET_ID = "1Bo6um_mJ1Eur87vUPEbEnCC5RtGaXyLKPDIHTMqHAAk"
SPREADSHEET_URL = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/edit"
SHEET_NAME = "日次PDCAトラッキング"

SERVICE_ACCOUNT_PATH = os.path.expanduser("~/.config/mcp-google-sheets/service-account.json")
UTAGE_KEY_PATH = os.path.join(CONFIG_DIR, "utage_api_key.txt")
CHATWORK_TOKEN_PATH = os.path.join(CONFIG_DIR, "chatwork_api_token.txt")
CHATWORK_ROOM_ID_PATH = os.path.join(CONFIG_DIR, "chatwork_room_id.txt")
NTFY_TOPIC_PATH = os.path.join(CONFIG_DIR, "ntfy_topic.txt")

PROMO_START = datetime.date(2026, 8, 7)
SEM_LP_COUNT_START = datetime.date(2026, 8, 9)
DATE_COL_START = 5  # column E (1-indexed)
SHEET_DATE_ORIGIN = datetime.date(2026, 8, 7)

LP_FUNNEL = "3FQFH1OGtggw"
LP_PAGE_SEMINAR_IDS = ["0Vkf2Xbh7Z51", "SzjnNkjXB0E8"]
LP_PAGE_AD_IDS = ["9UFM3KgpnZuT", "r78i61GBLPz0"]

WEBINAR_LP_COUNT_START = datetime.date(2026, 9, 12)
WEBINAR_LP_PAGE_IDS = ["67GSIiohgEMV"]
WEBINAR_AD_PAGE_IDS = ["mwGnEJqUeLXb"]

SEM_FUNNEL = "pcKWfTityvBy"
SEM_STEP_SEMINAR = "aTaZ7RyW3wQg"
SEM_STEP_INDIVIDUAL = "XvO0niPi1J0U"

PAY_FUNNEL = "rLlJKRapAlIl"
PAY_STEP_APPLY = "HZa6G78keLQt"
PAY_STEP_SALE = "2qYpn8p3qjcf"

SEM_EVENT_PROJECT_ID = "C0vOokE5slKi"
CONSULTATION_EVENT_ID = "YyESC92nIW9c"
LINE_ACCOUNT_ID = "tAS0YwOrTZIH"

FIRST_SEMINAR_DATE = datetime.date(2026, 8, 18)
OPEN_SEMINAR_SLOTS = 5
SEMINAR_CAPACITY = 8

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

ACTIVE_STATUSES = {"reserved", "attended", "delay"}
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]
