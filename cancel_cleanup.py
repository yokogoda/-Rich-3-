#!/usr/bin/env python3
"""
愛されRich美女3期 キャンセル整理スクリプト

UTAGE側でキャンセル扱い(status_participation = cancel_contact / cancel_no_contact /
cancel_changed)になった人を検知し、対象ごとに以下の2モードで処理する。

判定はメールアドレス単位の集約で行う(compute_cancelled_mails参照)。同じメールに
reserved/attended/delay(ACTIVE_STATUSES)の記録が1件でも残っていれば、他に古い
cancel_changed(日程変更)の記録があってもキャンセル扱いにしない。全記録がキャンセル系
だけの場合(=有効な予約が1つも残っていない)のみ本当の「もう来ない人」と判定する
(2026-08-23、日程変更した人の新しい予約行まで巻き込まれる事故が発覚し、この方式に変更)。

- delete モード(セミナー予約リスト): メールアドレス突合で該当行を削除する。
  UTAGE側は新規登録を追記するだけでキャンセルは自動反映しないため、この整理をしないと
  予約人数の集計(【事務局管理用】セミナー予約リスト、行数を数式で参照)が実態より
  多く出てしまう。
- flag モード(個別面談予約リスト): 生データの行は消さず、【事務局管理用】個別面談予約リスト
  側の「キャンセル」チェックボックスをTRUEにする(該当行はグレーアウト+取り消し線になる
  条件付き書式を設定済み)。個別面談は本講座と違って直前キャンセルの経緯を残しておきたい
  ため削除ではなくフラグにしている(2026-08-16、ユーザー判断)。

講座お申込みリストは対象外。UTAGE側は決済ファネル扱いでstatus_participationのような
キャンセルステータスを持たないため、API経由での自動検知ができない
(【事務局管理用】講座お申込みリストのT列に手動チェック用の「キャンセル」列のみ用意済み)。

認証情報は sync_daily.py(日次PDCAトラッキング用の自動化)と共有:
- UTAGE APIキー: ~/.config/utage-pdca/utage_api_key.txt
- Google Sheets書き込み用サービスアカウント: ~/.config/mcp-google-sheets/service-account.json
- ChatWork通知: ~/.config/utage-pdca/chatwork_api_token.txt / chatwork_room_id.txt
"""
import argparse
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

import gspread

CONFIG_DIR = os.path.expanduser("~/.config/utage-pdca")
UTAGE_KEY_PATH = os.path.join(CONFIG_DIR, "utage_api_key.txt")
SERVICE_ACCOUNT_PATH = os.path.expanduser("~/.config/mcp-google-sheets/service-account.json")
CHATWORK_TOKEN_PATH = os.path.join(CONFIG_DIR, "chatwork_api_token.txt")
CHATWORK_ROOM_ID_PATH = os.path.join(CONFIG_DIR, "chatwork_room_id.txt")

SPREADSHEET_ID = "1Bo6um_mJ1Eur87vUPEbEnCC5RtGaXyLKPDIHTMqHAAk"

CANCEL_STATUSES = {"cancel_contact", "cancel_no_contact", "cancel_changed"}
ACTIVE_STATUSES = {"reserved", "attended", "delay"}
# 判定はメールアドレス単位で行う: 同じメールに1件でもACTIVE_STATUSESの記録があれば、
# そのメールは(他にcancel_changed等の古い記録があっても)キャンセル扱いにしない。
# 日程変更(cancel_changed)は「振り替えただけで実際には来る予定」のため、旧日程の
# レコード単体ではキャンセルに見えるが、同じメールの新日程がreservedになっているはず、
# という前提(2026-08-23、緑川様のケースで発覚・ユーザー提案の方式)。
# 逆に、全レコードがCANCEL_STATUSESだけ(=有効な予約が1つも残っていない)場合のみ、
# 本当に「もう来ない人」と判定してキャンセル扱いにする。

# 対応対象のリスト。mail_col / name_cols は各生データシートの列(1-indexed)。
CANCEL_TARGETS = [
    {
        "mode": "delete",
        "event_project_id": "C0vOokE5slKi",
        "sheet_name": "セミナー予約リスト",
        "mail_col": 6,        # F列: メールアドレス
        "name_cols": (3, 4),  # C列: 姓, D列: 名
        "line_name_col": 15,  # O列: LINE名(生データ自身に追記。個別面談予約リストからVLOOKUPで即時参照される)
        "link_col": 16,       # P列: 1to1トークURL(同上)
    },
    {
        "mode": "flag",
        "event_project_id": "YyESC92nIW9c",  # セレンディピティ 愛されRich美女【3期】個別相談会
        "sheet_name": "個別面談予約リスト",       # 生データ(突合・行番号特定用)
        "mail_col": 6,        # F列: メールアドレス
        "name_cols": (3, 4),  # C列: 姓, D列: 名
        "management_sheet_name": "【事務局管理用】個別面談予約リスト",
        "checkbox_col": 12,   # L列: キャンセル
        # LINE名・1to1トークURL(D列・E列)はここではなく、セミナー予約リストのO列・P列を
        # VLOOKUPするシート上の数式で即時反映させている(2026-08-17〜)。個別相談は必ず
        # セミナー参加後に予約されるため、予約が入った時点でセミナー側のデータは既に
        # 同期済みのはずで、この方が1日2回のAPI同期より速い。
        "row_offset": 0,      # 管理シートは生データをA2起点でそのままミラーしているため行番号は同じ
    },
]

# UTAGEの1to1トーク画面URL。custom domainはUTAGE連携アカウントごとに固有なので、
# 別アカウント・別プロジェクトに展開する場合はここを変更する。
LINE_TALK_ACCOUNT_ID = "tAS0YwOrTZIH"  # message_account_listで確認した「セレンディピティ愛されRich美女」のID
LINE_TALK_URL_TEMPLATE = f"https://love.kyoko-happy.com/account/{LINE_TALK_ACCOUNT_ID}/line/talk#{{friend_id}}"


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
            print(f"  [warn] attempt {attempt}/{retries} failed: {e}; retrying in {wait}s")
            time.sleep(wait)
    raise last_err


def utage_get(key, path, params, retries=5, backoff=5):
    qs = "&".join(f"{k}={urllib.parse.quote(str(v))}" for k, v in params.items())
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


def fetch_all_applicants(key, event_project_id):
    """イベントの申込者を全件取得する(ステータス絞り込みはせず、後段でstatus_participation
    フィールドを見て自前で判定する。APIのstatus_participationクエリが本当にサーバー側で
    絞り込んでいるか確証がないため、安全側に倒して全件取得+クライアント側フィルタにしている)"""
    result = []
    page = 1
    while True:
        data = with_retry(lambda page=page: utage_get(
            key, f"/events/{event_project_id}/applicants",
            {"page": page, "per_page": 100}))
        rows = data.get("data", [])
        result.extend(rows)
        meta = data.get("meta", {})
        if page * meta.get("per_page", 100) >= meta.get("total", 0) or not rows:
            break
        page += 1
    return result


def compute_cancelled_mails(applicants):
    """申込者一覧をメールアドレス単位で集約し、「本当にもう来ない人」のメールアドレス集合を返す。
    同じメールに1件でもACTIVE_STATUSES(reserved/attended/delay)の記録があれば、
    他にキャンセル系の古い記録(日程変更前の枠など)が残っていてもキャンセル扱いにしない。"""
    by_mail = {}
    for a in applicants:
        mail = (a.get("mail") or "").strip().lower()
        if not mail:
            continue
        by_mail.setdefault(mail, []).append(a.get("status_participation"))

    cancelled_mails = set()
    for mail, statuses in by_mail.items():
        if any(s in ACTIVE_STATUSES for s in statuses):
            continue  # 有効な予約が1件でも残っていれば対象外
        if any(s in CANCEL_STATUSES for s in statuses):
            cancelled_mails.add(mail)
    return cancelled_mails


def notify_chatwork(message):
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


def find_matches(ws, target, cancelled_mails):
    """生データシートを読み、キャンセル済みメールと一致する行を返す"""
    all_values = with_retry(lambda: ws.get_all_values())
    mail_col = target["mail_col"]
    name_cols = target["name_cols"]

    matches = []  # (row_number, name, mail)
    for i, row in enumerate(all_values):
        if i == 0:
            continue  # header
        row_num = i + 1
        mail = (row[mail_col - 1] if len(row) >= mail_col else "").strip().lower()
        if mail and mail in cancelled_mails:
            name = "".join(row[c - 1] for c in name_cols if len(row) >= c)
            matches.append((row_num, name, mail))
    return matches


def build_line_maps(applicants):
    """申込者一覧からmail→LINE表示名・mail→1to1トークURLの辞書を作る"""
    mail_to_line_name = {}
    mail_to_link = {}
    for a in applicants:
        mail = (a.get("mail") or "").strip().lower()
        line_friend = a.get("line_friend") or {}
        line_name = (line_friend.get("display_name") or "").strip()
        friend_id = (line_friend.get("id") or "").strip()
        if not mail:
            continue
        if line_name:
            mail_to_line_name[mail] = line_name
        if friend_id:
            mail_to_link[mail] = LINE_TALK_URL_TEMPLATE.format(friend_id=friend_id)
    return mail_to_line_name, mail_to_link


def process_delete_target(key, sh, target, dry_run):
    applicants = fetch_all_applicants(key, target["event_project_id"])
    cancelled_mails = compute_cancelled_mails(applicants)
    no_mail_cancel_count = sum(
        1 for a in applicants
        if a.get("status_participation") in CANCEL_STATUSES and not (a.get("mail") or "").strip())

    print(f"[{target['sheet_name']}] UTAGE側キャンセル(有効な予約が残っていない人): {len(cancelled_mails)}件"
          f"（うちメールなしで突合不可な記録: {no_mail_cancel_count}件）")

    ws = with_retry(lambda: sh.worksheet(target["sheet_name"]))
    to_delete = find_matches(ws, target, cancelled_mails)

    if not to_delete:
        print(f"[{target['sheet_name']}] スプシ側に削除対象なし")
        if not dry_run:
            mail_to_line_name, mail_to_link = build_line_maps(applicants)
            sync_mail_keyed_column(ws, ws, target, mail_to_line_name, target.get("line_name_col"), "LINE名", dry_run)
            sync_mail_keyed_column(ws, ws, target, mail_to_link, target.get("link_col"), "1to1トークURL", dry_run)
        return []

    print(f"[{target['sheet_name']}] 削除対象: {len(to_delete)}件")
    for row_num, name, mail in to_delete:
        print(f"  - row{row_num}: {name} ({mail})")

    if dry_run:
        print("  [dry-run] 実際の削除は行いません")
        return to_delete

    # 行番号が大きい方から削除する(小さい方から消すと後続行の番号がズレるため)
    for row_num, name, mail in sorted(to_delete, reverse=True):
        with_retry(lambda row_num=row_num: ws.delete_rows(row_num))

    # 削除で行がズレた後に、残った行に対してLINE名・1to1トークURLを同期する
    mail_to_line_name, mail_to_link = build_line_maps(applicants)
    sync_mail_keyed_column(ws, ws, target, mail_to_line_name, target.get("line_name_col"), "LINE名", dry_run)
    sync_mail_keyed_column(ws, ws, target, mail_to_link, target.get("link_col"), "1to1トークURL", dry_run)

    return to_delete


def read_column(ws, col):
    """指定列を1回のリクエストでまとめて読み、{行番号: 値} を返す。

    以前は行ごとに ws.cell() を呼んでおり、1回の実行で80回以上の読み取りが発生していた。
    同じサービスアカウントを複数ジョブで共有しているため、Google Sheets APIの
    分あたりクォータ(60回/分)を突破して429が頻発していた(2026-08-30改善)。"""
    values = with_retry(lambda: ws.col_values(col))
    return {i + 1: (v or "") for i, v in enumerate(values)}


def batch_write_cells(ws, updates, label):
    """[(行番号, 値), ...] を1回のリクエストでまとめて書き込む。"""
    if not updates:
        return
    body = [{"range": gspread.utils.rowcol_to_a1(row, col), "values": [[value]]}
            for row, col, value in updates]
    with_retry(lambda: ws.batch_update(body, value_input_option="USER_ENTERED"))
    print(f"  {label}を{len(updates)}件まとめて書き込みました")


def sync_mail_keyed_column(ws_raw, ws_mgmt, target, mail_to_value, col, label, dry_run):
    """生データの行をメールアドレスで引き当て、管理シートの指定列(col)に値を同期する共通処理。
    LINE名・1to1トークURLなど、キャンセルの有無に関わらず全員分を毎回同期したい列に使う
    (値が変わっていない行は書き込みをスキップする)。"""
    if not col:
        return 0

    all_values = with_retry(lambda: ws_raw.get_all_values())
    mail_col = target["mail_col"]
    row_offset = target.get("row_offset", 0)

    current_col = read_column(ws_mgmt, col)

    updates = []  # (mgmt_row, value)
    for i, row in enumerate(all_values):
        if i == 0:
            continue  # header
        row_num = i + 1
        mail = (row[mail_col - 1] if len(row) >= mail_col else "").strip().lower()
        value = mail_to_value.get(mail, "")
        if not value:
            continue
        mgmt_row = row_num + row_offset
        current = current_col.get(mgmt_row, "")
        if current.strip() == value:
            continue
        updates.append((mgmt_row, value))

    if not updates:
        return 0

    print(f"[{target['sheet_name']}] {label}を更新対象: {len(updates)}件")
    if dry_run:
        for mgmt_row, value in updates:
            print(f"  - row{mgmt_row}: {value}")
        return len(updates)

    batch_write_cells(ws_mgmt, [(r, col, v) for r, v in updates], label)

    return len(updates)


def sync_line_names_and_links(ws_raw, ws_mgmt, target, applicants, dry_run):
    """生データの各行についてUTAGE側のLINE表示名・1to1トークURLを取得し、管理シートに反映する。"""
    mail_to_line_name = {}
    mail_to_link = {}
    for a in applicants:
        mail = (a.get("mail") or "").strip().lower()
        line_friend = a.get("line_friend") or {}
        line_name = (line_friend.get("display_name") or "").strip()
        friend_id = (line_friend.get("id") or "").strip()
        if not mail:
            continue
        if line_name:
            mail_to_line_name[mail] = line_name
        if friend_id:
            mail_to_link[mail] = LINE_TALK_URL_TEMPLATE.format(friend_id=friend_id)

    count = 0
    count += sync_mail_keyed_column(
        ws_raw, ws_mgmt, target, mail_to_line_name, target.get("line_name_col"), "LINE名", dry_run)
    count += sync_mail_keyed_column(
        ws_raw, ws_mgmt, target, mail_to_link, target.get("link_col"), "1to1トークURL", dry_run)
    return count


def process_flag_target(key, sh, target, dry_run):
    applicants = fetch_all_applicants(key, target["event_project_id"])
    cancelled_mails = compute_cancelled_mails(applicants)
    no_mail_cancel_count = sum(
        1 for a in applicants
        if a.get("status_participation") in CANCEL_STATUSES and not (a.get("mail") or "").strip())

    print(f"[{target['sheet_name']}] UTAGE側キャンセル(有効な予約が残っていない人): {len(cancelled_mails)}件"
          f"（うちメールなしで突合不可な記録: {no_mail_cancel_count}件）")

    ws_raw = with_retry(lambda: sh.worksheet(target["sheet_name"]))
    ws_mgmt = with_retry(lambda: sh.worksheet(target["management_sheet_name"]))

    line_name_updates = sync_line_names_and_links(ws_raw, ws_mgmt, target, applicants, dry_run)

    matches = find_matches(ws_raw, target, cancelled_mails)

    if not matches:
        print(f"[{target['sheet_name']}] フラグ対象なし")
        return [], line_name_updates

    checkbox_col = target["checkbox_col"]
    row_offset = target["row_offset"]

    checkbox_values = read_column(ws_mgmt, checkbox_col)
    newly_flagged = []
    for row_num, name, mail in matches:
        mgmt_row = row_num + row_offset
        current = checkbox_values.get(mgmt_row, "")
        if str(current).strip().upper() == "TRUE":
            continue  # 前回までに既にフラグ済み
        newly_flagged.append((mgmt_row, name, mail))

    if not newly_flagged:
        print(f"[{target['sheet_name']}] 新規フラグ対象なし(既存分は全て処理済み)")
        return [], line_name_updates

    print(f"[{target['sheet_name']}] 新規フラグ対象: {len(newly_flagged)}件")
    for mgmt_row, name, mail in newly_flagged:
        print(f"  - {target['management_sheet_name']} row{mgmt_row}: {name} ({mail})")

    if dry_run:
        print("  [dry-run] 実際のチェックは行いません")
        return newly_flagged, line_name_updates

    batch_write_cells(ws_mgmt, [(r, checkbox_col, True) for r, _, _ in newly_flagged],
                      "キャンセルフラグ")

    return newly_flagged, line_name_updates


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with open(UTAGE_KEY_PATH) as f:
        key = f.read().strip()

    gc = with_retry(lambda: gspread.service_account(filename=SERVICE_ACCOUNT_PATH))
    sh = with_retry(lambda: gc.open_by_key(SPREADSHEET_ID))

    all_deleted = {}
    all_flagged = {}
    line_name_update_count = 0
    had_error = False
    for target in CANCEL_TARGETS:
        try:
            if target["mode"] == "delete":
                result = process_delete_target(key, sh, target, args.dry_run)
                if result:
                    all_deleted[target["sheet_name"]] = result
            elif target["mode"] == "flag":
                result, line_updates = process_flag_target(key, sh, target, args.dry_run)
                line_name_update_count += line_updates
                if result:
                    all_flagged[target["management_sheet_name"]] = result
            else:
                raise ValueError(f"unknown mode: {target['mode']}")
        except Exception as e:
            had_error = True
            print(f"  [error] {target['sheet_name']} の処理に失敗: {e}")

    if args.dry_run:
        print("\n[dry-run] 通知の送信も行いません")
        return

    if all_deleted or all_flagged:
        # キャンセルが見つかった時だけ通知する(差分なしの場合は静かに終了する、2026-08-17〜)
        lines = ["【愛されRich3期 キャンセル整理】"]
        for sheet_name, deleted in all_deleted.items():
            lines.append(f"■ {sheet_name}: {len(deleted)}件削除")
            for _, name, mail in deleted:
                lines.append(f"　・{name}（{mail}）")
        for sheet_name, flagged in all_flagged.items():
            lines.append(f"■ {sheet_name}: {len(flagged)}件を「キャンセル」チェック")
            for _, name, mail in flagged:
                lines.append(f"　・{name}（{mail}）")
        if had_error:
            lines.append("\n⚠️ 一部の対象で処理エラーが発生しました。ログを確認してください。")
        notify_chatwork("\n".join(lines))
    elif had_error:
        # 差分は見つからなかったが処理エラーがあった場合は、静かに失敗させず必ず知らせる
        notify_chatwork(
            "【愛されRich3期 キャンセル整理】\n"
            "⚠️ 処理中にエラーが発生しました。ログを確認してください。"
        )

    if had_error:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
