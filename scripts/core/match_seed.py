"""Stable seed rules shared by watched and headless league fixtures."""

from __future__ import annotations

import hashlib


# {
#   責務: [league_fixture_seed: 観戦とヘッドレスで共通のリーグ試合seedを計算する]
#   処理: [1: 試合IDと両チーム名を既存の順序と区切りで文字列化する; 2: UTF-8のSHA-256の先頭8バイトを非負整数へ変換する]
#   引数: [fixture_id: 対戦を識別する値; home_name: ホーム名; away_name: アウェー名。文字列表現を既存方式と揃える]
#   戻り値: [int: 既存リーグ式と同じ64bit seed。グローバル乱数を消費しない]
# }
def league_fixture_seed(fixture_id: object, home_name: object, away_name: object) -> int:
    """Preserve the existing league seed formula across execution paths."""
    # 実行ごとに変わるhash()ではなく、入力順とバイト順を固定した既存式を保つ。
    seed_text = f"{fixture_id}:{home_name}:{away_name}"
    return int.from_bytes(hashlib.sha256(seed_text.encode("utf-8")).digest()[:8], "big")
