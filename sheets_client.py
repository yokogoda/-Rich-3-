#!/usr/bin/env python3
"""
愛されRich美女3期 UTAGE自動更新システム - Google Sheets API通信・書き込みモジュール (sheets_client.py)
"""
import datetime
import time

from config import (
    CUM_ROWS,
    DATE_COL_START,
    DAY_ROWS,
    OPEN_SEMINAR_SLOTS,
    ROW,
    ROW_GROUP_LABELS,
    SEMINAR_CAPACITY,
    SHEET_DATE_ORIGIN,
)


def with_retry(fn, retries=5, backoff=5):
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            return fn()
        except Exception as e:
            last_err = e
            print(f"  [warn] call attempt {attempt}/{retries} failed: {e}; retrying in {backoff}s")
            time.sleep(backoff)
    raise last_err


def col_letter(idx0):
    letters = ""
    n = idx0 + 1
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def date_to_col_idx0(d):
    return DATE_COL_START - 1 + (d - SHEET_DATE_ORIGIN).days


def read_column(ws, col_name, start_row=1, end_row=100, raw=False):
    """1列をまとめて読み、{行番号: 値} で返す。

    raw=True で書式を通さない生の値を返す(パーセントなら 0.5、金額なら 240000)。
    書き戻す値を読むときは必ず raw=True にする。既定の整形済み文字列("50%"など)を
    そのまま書き戻すと、RAW書き込みでは文字列として入って数式・集計が壊れる。
    """
    opts = {"value_render_option": "UNFORMATTED_VALUE"} if raw else {}
    vals = with_retry(lambda: ws.get(f"{col_name}{start_row}:{col_name}{end_row}", **opts))
    out = {}
    for r_idx0, r in enumerate(vals):
        row_num = start_row + r_idx0
        out[row_num] = r[0] if r else ""
    return out


def batch_write_cells(ws, updates_dict):
    if not updates_dict:
        return
    data = [{"range": f"A{r}" if isinstance(r, int) else r, "values": [[v]]} for r, v in updates_dict.items()]
    for d in data:
        if isinstance(d["range"], int):
            d["range"] = f"A{d['range']}"
    with_retry(lambda: ws.batch_update(data))


def _normalize_label(s):
    """折り返しセルは改行入りで返るので、空白と改行を落としてから比較する。"""
    return "".join(str(s or "").split())


def verify_row_alignment(ws):
    """ROWの行番号がシート上の見出しと本当に対応しているかを確かめる。

    ★これが無いと行ズレは一切検知できない。列見出し(9行目の日付)の一致も、
      累計の逆行チェックも、行がまるごとズレた書き込みは素通りさせる。
      2026-09-12〜14に実際に3日分の列が壊れたので追加した(2026-09-15)。
      詳しい経緯は config.ROW_GROUP_LABELS のコメントを見ること。

    不一致があれば RuntimeError を投げて書き込み自体を中止する。
    「古いコードで書いて数字を壊す」より「書かずに止まる」方が損害が小さい。
    ラベル由来のウェビナー視聴状況は後から埋め直せないため、壊す方が高くつく。
    """
    rows = sorted(ROW_GROUP_LABELS)
    labels = read_column(ws, "B", start_row=rows[0], end_row=rows[-1])

    mismatched = []
    for row_num in rows:
        actual = _normalize_label(labels.get(row_num, ""))
        for expected in ROW_GROUP_LABELS[row_num]:
            if _normalize_label(expected) not in actual:
                mismatched.append(
                    f"B{row_num}: 「{expected}」を含むはずが {actual or '(空欄)'!r}"
                )
                break

    if mismatched:
        raise RuntimeError(
            "シートの行の並びがコードの想定と一致しません。書き込みを中止します。"
            "（コードが古いか、シートの行が動かされています。"
            "git pull して deploy.sh を実行し直してください）: "
            + " / ".join(mismatched)
        )


def write_date(ws, m, target_date, stats=None):
    col_idx0 = date_to_col_idx0(target_date)
    col = col_letter(col_idx0)

    print(f"target_date={target_date} column={col}")

    # 安全確認①: 列(9行目の日付)が合っているか
    expected_label = f"{target_date.month}/{target_date.day}"
    actual_label = with_retry(lambda: ws.acell(f"{col}9").value)
    if (actual_label or "").strip() != expected_label:
        raise RuntimeError(
            f"列の見出しが想定と違います。書き込み中止。"
            f"想定列={col} 期待={expected_label} 実際={actual_label!r}"
        )

    # 安全確認②: 行の並びが合っているか(①では行ズレを検知できない)
    verify_row_alignment(ws)

    # ★行の範囲はROWから引く。数字を直書きすると、行を足したときに
    #   その行だけ無言で書かれなくなる(2026-09-11: 11〜63固定のままROWが73まで
    #   伸びていたため、セミナー予約数などが落ちる状態だった)。
    row_first, row_last = min(ROW.values()), max(ROW.values())
    prev_col = col_letter(col_idx0 - 1)
    prev_vals = read_column(ws, prev_col, start_row=row_first, end_row=row_last)

    if stats:
        m["sem_cum"] = stats["booked"]["all"]
        m["sem_day"] = stats["booked_day"]
        reg_all = m.get("reg_all_cum") or 0
        m["sem_rate"] = round(stats["booked"]["all"] / reg_all, 4) if reg_all else ""

    cell_updates = {ROW[k]: m[k] for k in list(ROW.keys()) if k in m}

    decreased = []
    for key_name in CUM_ROWS:
        row_num = ROW[key_name]
        prev_raw = prev_vals.get(row_num, "")
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

    for key_name in DAY_ROWS:
        row_num = ROW[key_name]
        prev_raw = prev_vals.get(row_num, "")
        try:
            prev_val = float(str(prev_raw).replace(",", "").replace("¥", "")) if prev_raw not in (None, "") else 0
        except ValueError:
            prev_val = 0
        new_val = m.get(key_name, 0)
        if isinstance(new_val, (int, float)) and new_val > 20 and prev_val > 0 and new_val > prev_val * 8:
            print(f"  [warn] {target_date} {key_name}: 前日({prev_val})の8倍以上に急増({new_val}) 要確認")

    # ★このコードが値を持たない行は、空欄で潰さず「今そこにある値」を書き戻す。
    #   代表例は行35〜41(ウェビナー視聴状況)。「対象日＝前日」の実行でしか計算しないので、
    #   バックフィルや再実行のときはキーが無い。ここで空欄にすると、前日に書いた値は
    #   ラベル由来の性質上もう二度と取り直せない。
    #   (移植前はこのリポジトリが行32〜41を一切計算しておらず、もう一方のMacの値を毎朝消していた)
    #   旧実装は cell_updates に無い行へ無条件に "" を入れていた
    #   (元の値を残すつもりの if が空文字を代入していて機能していなかった / 2026-09-15修正)。
    own_vals = read_column(ws, col, start_row=row_first, end_row=row_last, raw=True)

    full_col = []
    kept = []
    for r in range(row_first, row_last + 1):
        if r in cell_updates:
            val = cell_updates[r]
        else:
            val = own_vals.get(r, "")
            if str(val).strip() != "":
                kept.append(r)
        print(f"  row{r:<2} {next((k for k, v in ROW.items() if v == r), ''):<18} = {val}")
        full_col.append([val])

    if kept:
        print(f"  このコードが値を持たない行は現状維持しました: {kept}")

    range_name = f"{col}{row_first}:{col}{row_last}"
    with_retry(lambda: ws.update(range_name=range_name, values=full_col))
    print(f"  書き込み完了: {col}列（{target_date}）")
    return m, decreased


def write_summary(ws, m, target_date, stats=None):
    """期間累計サマリー(行5〜7)を更新する。列は行5のグループ名+行6の指標名で探す。
    ★このシートは列の挿入が絶対NG★ サマリー行はデータ行と列を共有しているため、
    列を挿入すると行9以降の日付列が全部ずれる。
    またI5:W7には結合セルがあり、結合の先頭以外のセルへの書き込みは無音で無視される。
    指標を足すときは結合の外側=X列以降に「行5=グループ名 / 行6=指標名」を置くこと。"""
    row5 = with_retry(lambda: ws.row_values(5))
    row6 = with_retry(lambda: ws.row_values(6))

    summary_col = {}
    last_group = ""
    max_len = max(len(row5), len(row6))
    for i in range(max_len):
        g = row5[i].strip() if i < len(row5) and row5[i].strip() else last_group
        m_label = row6[i].strip() if i < len(row6) else ""
        if g:
            last_group = g
        if g and m_label:
            key = f"{g}:{m_label}"
            summary_col[key] = col_letter(i)

    total_cum = stats["booked"]["all"] if stats else (m.get("sem_cum") or 0)
    attended = stats["attended"] if stats else 0
    booked_finished = stats.get("booked_finished", 0) if stats else 0

    # 【2026-09-11】サマリー(行4〜7)を行の並びに合わせて作り直しました。
    #   旧: LP / セミナー / 個別相談会 / 本講座
    #   新: ウェビナーLP / ウェビナー / 個別相談会 / 本講座 / セミナーLP / セミナー
    # 旧ラベル「LP:〜」はセミナーLPのことでしたが、ウェビナーLPと紛らわしいので
    # 「セミナーLP:〜」へ改名し、指標名の重複(LP登録数→登録数)も外しました。
    # ★古いラベルのままだと該当列が見つからず、その指標だけ更新されません(warnは出ます)。
    summary_by_label = {
        "セミナーLP:PV": m.get("lp_pv_all_cum"), "セミナーLP:UU": m.get("lp_uu_all_cum"),
        "セミナーLP:登録数": m.get("reg_all_cum"), "セミナーLP:登録率": m.get("regrate_all"),
        "ウェビナーLP:PV": m.get("web_pv_all_cum"), "ウェビナーLP:UU": m.get("web_uu_all_cum"),
        "ウェビナーLP:登録数": m.get("web_reg_all_cum"),
        "ウェビナーLP:登録率": m.get("web_regrate_all"),
        "セミナー:予約数": total_cum,
        "セミナー:予約率": round(total_cum / m["reg_all_cum"], 4) if m.get("reg_all_cum") else "",
        "セミナー:参加数": attended,
        "セミナー:参加率": round(attended / booked_finished, 4) if booked_finished else "",
        "個別相談会:予約数": m.get("ind_cum"),
        # 分母はセミナー参加数。monolith版(本番)が書いていた指標で、分割版で欠けていた。
        # 書かないとセルが古い値のまま残り続け、誰も気づけないため必ず書く(2026-09-07復元)。
        "個別相談会:予約率": (round(m["ind_cum"] / attended, 4)
                              if attended and isinstance(m.get("ind_cum"), (int, float)) else ""),
        "本講座:申込数": m.get("apply_cum"), "本講座:成約数": m.get("sale_cum"),
        "本講座:成約率": m.get("sale_rate"), "本講座:売上金額": m.get("amount_cum"),
    }

    if stats:
        summary_by_label["セミナー:キャンセル数"] = stats["cancelled"]["all"]

    # ウェビナーの予約・視聴(2026-09-15に本番から移植)。
    # まだ集計開始日に達していない日や、ラベル由来を書かない実行(対象日が前日でない)では
    # m にキーが無いので、あるものだけ書く。無いものを書くとサマリーが空欄で消える。
    #
    # 【2026-09-16追加】予約の内訳(広告/ハウス)。行は足さずサマリーだけに出す。
    #   理由: 行を挿入するとROWが全部ずれ、古いコードを持つMacが別の行へ書き続ける
    #   (2026-09-12〜14に実際に3日間壊れた)。予約数はcreated_atで遡れるので、
    #   日別の推移が必要になった時点で後から行を足して埋め直せる。
    # 「ウェビナー:予約率」は2026-09-16に定義を変更(LP経由の予約 ÷ LP登録)。
    #   旧定義は分子にLP非経由の予約が入っていて、放っておくと100%を超える壊れた率だった。
    for label, key in [("ウェビナー:予約数", "web_book_cum"),
                       ("ウェビナー:予約率", "web_bookrate"),
                       ("ウェビナー内訳:広告(ウェビナーLP)", "web_book_ad_web"),
                       ("ウェビナー内訳:広告(セミナー期)", "web_book_ad_sem"),
                       ("ウェビナー内訳:ハウス", "web_book_house"),
                       ("ウェビナー内訳:広告LP予約率", "web_bookrate_ad"),
                       ("ウェビナー:視聴開始", "web_lab_start"),
                       ("ウェビナー:視聴完了", "web_lab_done"),
                       ("ウェビナー:視聴完了率", "web_donerate")]:
        if key in m:
            summary_by_label[label] = m[key]

    updates = []
    missing = []
    for label, value in summary_by_label.items():
        cell_col = summary_col.get(label)
        if not cell_col:
            missing.append(label)
            continue
        updates.append({"range": f"{cell_col}7", "values": [[value]]})

    if missing:
        print(f"  [warn] サマリー列が見つからず書き込めなかった項目: {missing}")

    if updates:
        with_retry(lambda: ws.batch_update(updates))

    with_retry(lambda: ws.update_acell("I4", f"期間累計サマリー（{target_date.month}/{target_date.day}時点）"))


def write_agg_route_block(sh, stats, target_date):
    ws = with_retry(lambda: sh.worksheet("集計"))
    b = stats["booked"]
    c = stats["cancelled"]
    a = stats["applied"]

    table_data = [
        ["予約数(累計)", b["all"], b["organic"], b["ad"]],
        ["キャンセル数", c["all"], c["organic"], c["ad"]],
        ["申込数(合計)", a["all"], a["organic"], a["ad"]],
    ]
    with_retry(lambda: ws.update(range_name="A17:D19", values=table_data))

    slot_rows = []
    for date_key, count in stats.get("per_slot", {}).items():
        slot_rows.append([count])

    if slot_rows:
        with_retry(lambda: ws.update(range_name="B9:B13", values=[[stats["per_slot"].get(d, 0)] for d in [
            "2026-08-18", "2026-08-22", "2026-08-28", "2026-09-05", "2026-09-11"
        ]]))

    print(f"  集計タブ 日程別件数を更新: {stats.get('per_slot')}")
    print(f"  集計タブ A15:D20 を更新しました (予約{b['all']} / キャンセル{c['all']} / 申込{a['all']})")
