"""Shared presentation tokens and bounded text for entry screens."""

from __future__ import annotations

import pygame

BACKGROUND = (12, 22, 29)
SURFACE = (23, 38, 47)
TEXT = (238, 244, 240)
MUTED = (169, 188, 190)
ACCENT = (126, 229, 187)
BORDER = (56, 78, 85)


# {
#   責務: [fit_label: 読める文字サイズを保ち、表示文字列を指定幅へ省略する]
#   処理: [1: 改行等を空白へ正規化する; 2: 全文または省略記号が入るか判定する; 3: 二分探索で入る接頭辞を求める]
#   引数: [font: 実測するフォント; value: 表示値; width: 許容するピクセル幅]
#   戻り値: [str: 全文・末尾省略の文字列・省略記号すら入らない時の空文字。入力データは変更しない]
# }
def fit_label(font: pygame.font.Font, value: str, width: int) -> str:
    """Fit a single-line label without shrinking it below readable sizes."""
    # 改行を一行表示へ揃え、元の値ではなく表示用文字列を扱う。
    value = " ".join(str(value).split())
    if font.size(value)[0] <= width:
        return value
    suffix = "…"
    if font.size(suffix)[0] > width:
        return ""
    # 毎文字を順に削る代わりに、フォント実測の回数を二分探索で抑える。
    low, high = 0, len(value)
    while low < high:
        middle = (low + high + 1) // 2
        if font.size(value[:middle] + suffix)[0] <= width:
            low = middle
        else:
            high = middle - 1
    return value[:low] + suffix
