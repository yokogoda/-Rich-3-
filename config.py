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

# 【2026-09-11に9/12→9/11へ変更】当初は「公開日=9/12」として9/12起点にしていたが、
# 実際には9/11の夜にウェビナーLPへの切り替えと広告の出し替えが行われ、同日に実データが
# 発生していた(オーガニックLP: PV7/UU4/登録1、広告LP: PV43/UU36)。9/12起点のままだと
# この初日分が日別にも累計にも一生入らないため9/11へ前倒し。
# 9/10以前は1日1〜5PVの確認用アクセスと9/5のテスト登録1件だけなので9/11が境目として妥当。
WEBINAR_LP_COUNT_START = datetime.date(2026, 9, 11)
WEBINAR_LP_PAGE_IDS = ["67GSIiohgEMV"]
WEBINAR_AD_PAGE_IDS = ["mwGnEJqUeLXb"]

SEM_FUNNEL = "pcKWfTityvBy"
SEM_STEP_SEMINAR = "aTaZ7RyW3wQg"
SEM_STEP_INDIVIDUAL = "XvO0niPi1J0U"

PAY_FUNNEL = "rLlJKRapAlIl"
PAY_STEP_APPLY = "Xph9Dysj7atc"
PAY_STEP_SALE = "Xph9Dysj7atc"

SEM_EVENT_PROJECT_ID = "C0vOokE5slKi"
CONSULTATION_EVENT_ID = "YyESC92nIW9c"
LINE_ACCOUNT_ID = "tAS0YwOrTZIH"

FIRST_SEMINAR_DATE = datetime.date(2026, 8, 18)
OPEN_SEMINAR_SLOTS = 5
SEMINAR_CAPACITY = 8

# 【2026-09-11 22時 シートの行を並べ替えました。必ずpullしてから実行してください】
# 9/12からウェビナーが主役になるため、開いた瞬間にウェビナーが見えるように並びを変えました。
#   旧: 11-34 セミナー / 35-42 個別〜売上 / 43-73 ウェビナー
#   新: 11-41 ウェビナー / 42-49 個別〜売上 / 50-73 セミナー
#   ずれ幅は3種類 … LP系とセミナー予約 +39 / 個別〜売上 +7 / ウェビナー -32
#
# ★古いROWのまま実行すると、ズレた行に書き込まれます。
#   列見出しの日付チェックも累計の減少チェックもこの種のズレは検知できないので、静かに壊れます。
#
# 行32〜41（ウェビナー予約数・視聴状況・視聴率）は2026-09-11に新設した行です。
# 夏菜側の本番スクリプトが書き込みます。こちら側では値を作っていないので、
# ROWにキーはあっても書き込み対象になりません（cell_updatesはmにあるキーだけを拾うため）。
ROW = {
    # --- ウェビナー(11〜41) ---
    "web_pv_all_cum": 11, "web_uu_all_cum": 12,
    "web_pv_org_cum": 13, "web_uu_org_cum": 14,
    "web_pv_ad_cum": 15, "web_uu_ad_cum": 16,
    "web_pv_all_day": 17, "web_uu_all_day": 18,
    "web_pv_org_day": 19, "web_uu_org_day": 20,
    "web_pv_ad_day": 21, "web_uu_ad_day": 22,
    "web_reg_all_cum": 23, "web_reg_org_cum": 24, "web_reg_ad_cum": 25,
    "web_reg_all_day": 26, "web_reg_org_day": 27, "web_reg_ad_day": 28,
    "web_regrate_all": 29, "web_regrate_org": 30, "web_regrate_ad": 31,
    # ここから下は2026-09-11新設（夏菜側が書き込み）
    "web_book_cum": 32, "web_book_day": 33, "web_bookrate": 34,
    "web_lab_apply": 35, "web_lab_start": 36, "web_lab_done": 37,
    "web_lab_dropout": 38, "web_lab_noshow": 39,
    "web_startrate": 40, "web_donerate": 41,
    # --- 個別相談〜売上(42〜49。セミナー期・ウェビナー期の両方にまたがる) ---
    "ind_cum": 42, "ind_day": 43,
    "apply_cum": 44, "apply_day": 45,
    "sale_cum": 46, "sale_day": 47,
    "amount_cum": 48, "amount_day": 49,
    # --- セミナー(50〜73。9/11で終了。シート上は折りたたんであります) ---
    "lp_pv_all_cum": 50, "lp_uu_all_cum": 51,
    "lp_pv_sem_cum": 52, "lp_uu_sem_cum": 53,
    "lp_pv_ad_cum": 54, "lp_uu_ad_cum": 55,
    "lp_pv_all_day": 56, "lp_uu_all_day": 57,
    "lp_pv_sem_day": 58, "lp_uu_sem_day": 59,
    "lp_pv_ad_day": 60, "lp_uu_ad_day": 61,
    "reg_all_cum": 62, "reg_sem_cum": 63, "reg_ad_cum": 64,
    "reg_all_day": 65, "reg_sem_day": 66, "reg_ad_day": 67,
    "regrate_all": 68, "regrate_sem": 69, "regrate_ad": 70,
    "sem_cum": 71, "sem_day": 72, "sem_rate": 73,
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

# 「キャンセルされていない有効な予約」とみなすステータス。参加率の【分母】に使う。
# UTAGEには「欠席」ステータスが無く、来なかった人も reserved のまま残る。
# そのため分母は reserved(=結果的に欠席)も含み、分子(attended)と集合が違うのが正しい。
# ★delay(遅刻)は運用上使わない方針(2026-09-07ユーザー確認)。参加とみなすのは attended だけ。
#   ここに delay を残してあるのは、万一付いた場合に「有効な予約」から漏らさないため。
#   分子(参加数)に delay を足す変更はしないこと。
ACTIVE_STATUSES = {"reserved", "attended", "delay"}
WEEKDAYS = ["月", "火", "水", "木", "金", "土", "日"]
