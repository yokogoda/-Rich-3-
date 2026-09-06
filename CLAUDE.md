# Claude Code Handover Guide: 毎週月曜日 配信スケジュール自動報告システム

このリポジトリ・プロジェクトにおける**毎週月曜日の配信スケジュール自動報告業務**を Claude Code 引き継ぐための運用マニュアルです。

---

## 1. 概要と構成

* **目的**: Googleスプレッドシート（配信スケジュール管理マスター）から今週（月〜日）の配信スケジュールを自動取得し、Chatworkへ整形レポートを投稿する。
* **主要スクリプト**:
  * 実体: `~/.config/utage-pdca/chatwork_schedule_reporter.py`
  * Git同期版: `/Users/godayoko/Desktop/愛されRich3期/aisare-rich-3ki-report/chatwork_schedule_reporter.py`
* **連携データソース**:
  * **スプレッドシートID**: `12zT7vCUqcAZ0YexlnCt2U3BWeT0YbYMW1DPjtgT54WQ`
  * **マスターURL**: `https://docs.google.com/spreadsheets/d/12zT7vCUqcAZ0YexlnCt2U3BWeT0YbYMW1DPjtgT54WQ/edit#gid=1930246157`
  * **対象タブ名**: `配信スケジュール管理` (gid: `1930246157`)
* **送信先**:
  * 本番 Chatwork ルーム: `439651539` (`~/.config/utage-pdca/chatwork_room_id.txt`)
  * テスト Chatwork ルーム: `404971332` (`~/.config/utage-pdca/private_chatwork_room_id.txt`)
  * Chatwork API トークン: `~/.config/utage-pdca/chatwork_api_token.txt`
  * Google API サービスアカウント: `~/.config/mcp-google-sheets/service-account.json`

---

## 2. 実行コマンド（Claude Code用クイックリファレンス）

### ① プレビュー確認（送信なし）
今週（または日曜日実行時は翌週）の配信スケジュールを抽出し、ターミナル上にテキストプレビューを表示します。
```bash
python3 ~/.config/utage-pdca/chatwork_schedule_reporter.py
```

### ② テスト送信（テスト用Chatworkルームへ送信）
本番フラグに影響を与えず、テスト用ルームID（`404971332`）へメッセージを送信します。
```bash
python3 ~/.config/utage-pdca/chatwork_schedule_reporter.py --send --test
```

### ③ 本番送信（定例報告：Chatwork本番ルームへ送信）
本番用ルーム（`439651539`）へ配信スケジュールメッセージを送信し、重複送信防止フラグを作成します。
```bash
python3 ~/.config/utage-pdca/chatwork_schedule_reporter.py --send
```

---

## 3. 日付判定ロジックと動作仕様

* **月曜日〜土曜日実行時**: 当週の月曜日〜日曜日（例: 9/7(月)〜9/13(日)）を自動計算し、対象日の項目を抽出。
* **日曜日実行時**: 事前準備に対応するため、翌週の月曜日〜日曜日（例: 9/7(月)〜9/13(日)）を自動計算して抽出。
* **データ取得処理**:
  * 優先: `gspread`（サービスアカウント経由でリアルタイム取得）
  * フォールバック: Google Sheets CSV export (`gviz/tq`)

---

## 4. スプレッドシートへのスケジュール新規追加手順

ユーザーから新しい配信予定の追加（例: 「9/12 9:00 構築チームからB3登録者へウェビナー訴求追加」など）を指示された場合、以下のPythonコードで即時追加が可能です。

```python
import gspread, os

sa_path = os.path.expanduser('~/.config/mcp-google-sheets/service-account.json')
gc = gspread.service_account(filename=sa_path)
sh = gc.open_by_key('12zT7vCUqcAZ0YexlnCt2U3BWeT0YbYMW1DPjtgT54WQ')
ws = sh.worksheet('配信スケジュール管理')

new_row = [
    'FALSE',                    # 実行チェック
    '2026-09-12',               # 配信予定日 (YYYY-MM-DD)
    '土',                        # 曜日
    '9:00',                     # 配信時間
    'UTAGE (LINE)',             # 配信媒体
    'ウェビナー訴求(B2遷移)',      # 原稿タイトル / 配信名
    'B3登録者',                  # 配信対象
    '構築チーム',                # 担当役割
    '設定完了',                  # 確認ステータス
    'ウェビナー訴求(B2遷移)'       # アクション事項
]

# 時系列順になるように該当行へ追加・挿入
ws.append_row(new_row)
```

追加後は `python3 ~/.config/utage-pdca/chatwork_schedule_reporter.py --send --test` で正しく反映されるか確認してください。

---

## 5. リポジトリ同期手順

スクリプトを更新した場合は、必ず設定ディレクトリとリポジトリの両方に反映し、GitHubにプッシュしてください。

```bash
# 1. ローカル設定ディレクトリからリポジトリへコピー
cp ~/.config/utage-pdca/chatwork_schedule_reporter.py "/Users/godayoko/Desktop/愛されRich3期/aisare-rich-3ki-report/chatwork_schedule_reporter.py"

# 2. Gitコミット＆プッシュ
git -C "/Users/godayoko/Desktop/愛されRich3期/aisare-rich-3ki-report" add chatwork_schedule_reporter.py
git -C "/Users/godayoko/Desktop/愛されRich3期/aisare-rich-3ki-report" commit -m "Update schedule reporter script"
git -C "/Users/godayoko/Desktop/愛されRich3期/aisare-rich-3ki-report" push origin main
```
