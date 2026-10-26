"""UTF-8 JSON files used by the developer match reproduction command."""

from __future__ import annotations

import json
from pathlib import Path


# {
#   責務: [read_input_json: 再現入力ファイルをUTF-8またはBOM付きUTF-8で読み込む]
#   処理: [1: 指定パスのテキストを読む; 2: JSON値として復号する]
#   引数: [path: 利用者が指定した既存入力ファイル]
#   戻り値: [object: 未検証のJSON値。内容の検証は復元層が担当し、読込失敗はOSError、不正JSONはValueError]
# }
def read_input_json(path: Path) -> object:
    # BOMの有無だけを吸収し、不正なJSONや不存在を既定値へ置き換えない。
    return json.loads(path.read_text(encoding="utf-8-sig"))


# {
#   責務: [write_new_json: 既存ファイルを上書きせず調査用JSONを新規保存する]
#   処理: [1: 指定先を排他的に新規作成する; 2: 日本語を保持した有限JSONと末尾改行を書き込む]
#   引数: [path: 親フォルダが存在する新規出力先; payload: 保存するJSON対応値]
#   戻り値: [None: 保存値を変更しない。既存先・親不存在・書込失敗はOSError、非有限値はValueError]
# }
def write_new_json(path: Path, payload: object) -> None:
    # 存在確認と書込を分離せず、openの排他作成で既存の調査証拠を保護する。
    with path.open("x", encoding="utf-8") as output:
        json.dump(payload, output, ensure_ascii=False, indent=2, allow_nan=False)
        output.write("\n")


# {
#   責務: [write_reproduction_report: 再実行入力と比較結果をレポートv1として新規保存する]
#   処理: [1: レポート識別子と版・入力・比較結果を組み合わせる; 2: 共通の排他保存へ渡す]
#   引数: [path: 新規レポート先; record: 検証済み再現入力; report: 全イベントを含む比較結果]
#   戻り値: [None: レポートを保存する。不一致や未完走でも内容を省略せず、保存エラーは呼出し元へ返す]
# }
def write_reproduction_report(path: Path, record: dict, report: dict) -> None:
    # 入力と報告の形式を混同せず、inputだけを取り出して再実行できる形にする。
    write_new_json(
        path,
        {
            "format": "kadocalcio.match-repro-report",
            "version": 1,
            "input": record,
            "comparison": report,
        },
    )
