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


def read_column(ws, col_name, start_row=1, end_row=100):
    vals = with_retry(lambda: ws.get(f"{col_name}{start_row}:{col_name}{end_row}"))
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


def write_date(ws, m, target_date, stats=None):
    col_idx0 = date_to_col_idx0(target_date)
    col = col_letter(col_idx0)

    print(f"target_date={target_date} column={col}")

    expected_label = f"{target_date.month}/{target_date.day}"
    actual_label = with_retry(lambda: ws.acell(f"{col}9").value)
    if (actual_label or "").strip() != expected_label:
        raise RuntimeError(
            f"列の見出しが想定と違います。書き込み中止。"
            f"想定列={col} 期待={expected_label} 実際={actual_label!r}"
        )

    prev_col = col_letter(col_idx0 - 1)
    prev_vals = read_column(ws, prev_col, start_row=11, end_row=63)

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

    full_col = []
    for r in range(11, 64):
        val = cell_updates.get(r, "")
        if val == "" and r in prev_vals:
            val = ""
        print(f"  row{r:<2} {next((k for k, v in ROW.items() if v == r), ''):<18} = {val}")
        full_col.append([val])

    range_name = f"{col}11:{col}63"
    with_retry(lambda: ws.update(range_name=range_name, values=full_col))
    print(f"  書き込み完了: {col}列（{target_date}）")
    return m, decreased


def write_summary(ws, m, target_date, stats=None):
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

    summary_by_label = {
        "LP:PV": m.get("lp_pv_all_cum"), "LP:UU": m.get("lp_uu_all_cum"),
        "LP:LP登録数": m.get("reg_all_cum"), "LP:LP登録率": m.get("regrate_all"),
        "セミナー:予約数": total_cum,
        "セミナー:予約率": round(total_cum / m["reg_all_cum"], 4) if m.get("reg_all_cum") else "",
        "セミナー:参加数": attended,
        "セミナー:参加率": round(attended / booked_finished, 4) if booked_finished else "",
        "個別相談会:予約数": m.get("ind_cum"),
        "本講座:申込数": m.get("apply_cum"), "本講座:成約数": m.get("sale_cum"),
        "本講座:成約率": m.get("sale_rate"), "本講座:売上金額": m.get("amount_cum"),
    }

    if stats:
        summary_by_label["セミナー:キャンセル数"] = stats["cancelled"]["all"]

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
