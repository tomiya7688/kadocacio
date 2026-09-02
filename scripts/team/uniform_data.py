"""Serializable pixel-uniform schema, validation, and file exchange."""

from __future__ import annotations

import json
import re
from copy import deepcopy
from pathlib import Path

from scripts.core.paths import UNIFORMS_DIR


UNIFORM_FORMAT = "カドカルチョユニフォーム"
UNIFORM_VERSION = 1
UNIFORM_PART_SIZES = {
    "胸": (6, 6),
    "左腕": (3, 5),
    "右腕": (3, 5),
    "左脚": (3, 5),
    "右脚": (3, 5),
}
UNIFORM_COLOR_TOKENS = ("P", "S")
_HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{6}")


def _valid_cell(value: object) -> bool:
    return str(value).upper() in UNIFORM_COLOR_TOKENS or bool(_HEX_COLOR.fullmatch(str(value)))


def _solid_grid(width: int, height: int, value: str) -> list[list[str]]:
    return [[value for _ in range(width)] for _ in range(height)]


def default_uniform() -> dict:
    parts = {}
    for part, (width, height) in UNIFORM_PART_SIZES.items():
        parts[part] = _solid_grid(width, height, "S" if part.endswith("脚") else "P")
    return {"バージョン": UNIFORM_VERSION, "パーツ": parts}


def normalize_uniform(value: object) -> dict:
    source = value if isinstance(value, dict) else {}
    if isinstance(source.get("ユニフォーム"), dict):
        source = source["ユニフォーム"]
    source_parts = source.get("パーツ", {}) if isinstance(source.get("パーツ"), dict) else {}
    normalized = default_uniform()
    for part, (width, height) in UNIFORM_PART_SIZES.items():
        rows = source_parts.get(part)
        if not isinstance(rows, list):
            continue
        fallback = "S" if part.endswith("脚") else "P"
        output = []
        for y in range(height):
            source_row = rows[y] if y < len(rows) and isinstance(rows[y], list) else []
            output.append([
                str(source_row[x]).upper() if x < len(source_row) and _valid_cell(source_row[x]) else fallback
                for x in range(width)
            ])
        normalized["パーツ"][part] = output
    return normalized


def validate_uniform(value: object) -> list[str]:
    if not isinstance(value, dict):
        return ["オブジェクトが必要です"]
    parts = value.get("パーツ")
    if not isinstance(parts, dict):
        return ["パーツが必要です"]
    issues = []
    for part, (width, height) in UNIFORM_PART_SIZES.items():
        rows = parts.get(part)
        if not isinstance(rows, list) or len(rows) != height:
            issues.append(f"{part}は{width}×{height}で指定してください")
            continue
        if any(not isinstance(row, list) or len(row) != width for row in rows):
            issues.append(f"{part}は{width}×{height}で指定してください")
            continue
        if any(not _valid_cell(cell) for row in rows for cell in row):
            issues.append(f"{part}に無効な色があります")
    return issues


def _rgb(value: str, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    if not _HEX_COLOR.fullmatch(str(value)):
        return fallback
    return tuple(int(str(value)[offset:offset + 2], 16) for offset in (1, 3, 5))


def runtime_uniform(
    value: object,
    primary: tuple[int, int, int],
    secondary: tuple[int, int, int],
) -> dict[str, tuple[tuple[tuple[int, int, int], ...], ...]]:
    uniform = normalize_uniform(value)
    colors = {"P": tuple(primary[:3]), "S": tuple(secondary[:3])}
    return {
        part: tuple(tuple(colors.get(cell, _rgb(cell, colors["P"])) for cell in row) for row in rows)
        for part, rows in uniform["パーツ"].items()
    }


def safe_uniform_filename(value: object) -> str:
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(value or "ユニフォーム")).strip(" .")
    return (stem or "ユニフォーム") + ".uniform.json"


def export_uniform(value: object, name: object) -> Path:
    UNIFORMS_DIR.mkdir(parents=True, exist_ok=True)
    path = UNIFORMS_DIR / safe_uniform_filename(name)
    payload = {"形式": UNIFORM_FORMAT, "バージョン": UNIFORM_VERSION, "ユニフォーム": normalize_uniform(value)}
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)
    return path


def load_uniform(path: Path) -> dict:
    resolved = path.resolve()
    try:
        resolved.relative_to(UNIFORMS_DIR.resolve())
    except ValueError as error:
        raise ValueError("uniformsフォルダ外は読み込めません") from error
    payload = json.loads(resolved.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or payload.get("形式") != UNIFORM_FORMAT:
        raise ValueError("カドカルチョのユニフォームファイルではありません")
    uniform = payload.get("ユニフォーム")
    issues = validate_uniform(uniform)
    if issues:
        raise ValueError(" / ".join(issues))
    return deepcopy(uniform)


def list_uniform_files() -> list[Path]:
    if not UNIFORMS_DIR.exists():
        return []
    return sorted(UNIFORMS_DIR.glob("*.uniform.json"), key=lambda path: path.name.casefold())


__all__ = (
    "UNIFORM_COLOR_TOKENS",
    "UNIFORM_PART_SIZES",
    "default_uniform",
    "export_uniform",
    "list_uniform_files",
    "load_uniform",
    "normalize_uniform",
    "runtime_uniform",
    "safe_uniform_filename",
    "validate_uniform",
)
