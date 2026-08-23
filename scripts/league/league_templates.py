from __future__ import annotations

import json
import re
import uuid
from copy import deepcopy
from pathlib import Path


DEFAULT_TEMPLATE_ID = "default"
DEFAULT_TEMPLATE_NAME = "標準テンプレート"


def _read_payload(path: Path) -> dict:
    with path.open("r", encoding="utf-8-sig") as file:
        payload = json.load(file)
    if not isinstance(payload, dict):
        raise ValueError("テンプレートJSONの一番外側はオブジェクトにしてください")
    return payload


def _template_path(template_id: str, template_dir: Path) -> Path:
    cleaned = re.sub(r"[^0-9a-zA-Z_-]", "", str(template_id))
    if not cleaned or cleaned == DEFAULT_TEMPLATE_ID:
        raise ValueError("テンプレートIDが不正です")
    path = template_dir / f"{cleaned}.json"
    path.resolve().relative_to(template_dir.resolve())
    return path


def load_template_payload(template_id: str, default_path: Path, template_dir: Path) -> dict:
    template_id = str(template_id or DEFAULT_TEMPLATE_ID)
    path = default_path if template_id == DEFAULT_TEMPLATE_ID else _template_path(template_id, template_dir)
    payload = _read_payload(path)
    return {
        "テンプレートID": template_id,
        "テンプレート名": str(payload.get("テンプレート名", DEFAULT_TEMPLATE_NAME if template_id == DEFAULT_TEMPLATE_ID else path.stem)),
        "リーグ一覧": deepcopy(payload.get("リーグ一覧", [])),
        "トーナメント一覧": deepcopy(payload.get("トーナメント一覧", [])),
    }


def list_league_templates(default_path: Path, template_dir: Path) -> list[dict]:
    try:
        default_payload = load_template_payload(DEFAULT_TEMPLATE_ID, default_path, template_dir)
        default_name = default_payload["テンプレート名"]
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        default_name = DEFAULT_TEMPLATE_NAME
    entries = [{
        "id": DEFAULT_TEMPLATE_ID,
        "name": default_name,
        "path": default_path,
        "is_default": True,
    }]
    try:
        paths = sorted(template_dir.glob("*.json"), key=lambda path: path.name.casefold())
    except OSError:
        return entries
    for path in paths:
        try:
            payload = _read_payload(path)
            template_id = str(payload.get("テンプレートID", path.stem))
            if template_id == DEFAULT_TEMPLATE_ID or _template_path(template_id, template_dir) != path:
                continue
            name = str(payload.get("テンプレート名", path.stem)).strip()
            leagues = payload.get("リーグ一覧", [])
            tournaments = payload.get("トーナメント一覧", [])
            if not name or not isinstance(leagues, list) or not isinstance(tournaments, list):
                continue
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            continue
        entries.append({"id": template_id, "name": name, "path": path, "is_default": False})
    return entries


def save_template_payload(
    template_id: str,
    template_name: str,
    definitions: list[dict],
    tournaments: list[dict],
    default_path: Path,
    template_dir: Path,
) -> None:
    template_id = str(template_id or DEFAULT_TEMPLATE_ID)
    name = str(template_name).strip()[:40]
    if not name:
        raise ValueError("テンプレート名が空です")
    target = default_path if template_id == DEFAULT_TEMPLATE_ID else _template_path(template_id, template_dir)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "テンプレート名": name,
        "リーグ一覧": definitions,
        "トーナメント一覧": tournaments,
    }
    if template_id != DEFAULT_TEMPLATE_ID:
        payload = {"テンプレートID": template_id, **payload}
    temporary = target.with_suffix(".json.tmp")
    with temporary.open("w", encoding="utf-8") as file:
        json.dump(payload, file, ensure_ascii=False, indent=2)
    temporary.replace(target)


def create_league_template(
    name: str,
    source_payload: dict,
    default_path: Path,
    template_dir: Path,
) -> str:
    clean_name = str(name).strip()[:40]
    if not clean_name:
        raise ValueError("テンプレート名が空です")
    if any(entry["name"] == clean_name for entry in list_league_templates(default_path, template_dir)):
        raise ValueError("同じ名前のテンプレートが既にあります")
    template_id = uuid.uuid4().hex
    save_template_payload(
        template_id,
        clean_name,
        deepcopy(source_payload.get("リーグ一覧", [])),
        deepcopy(source_payload.get("トーナメント一覧", [])),
        default_path,
        template_dir,
    )
    return template_id


def rename_league_template(
    template_id: str,
    name: str,
    default_path: Path,
    template_dir: Path,
) -> None:
    clean_name = str(name).strip()[:40]
    if not clean_name:
        raise ValueError("テンプレート名が空です")
    if any(
        entry["id"] != template_id and entry["name"] == clean_name
        for entry in list_league_templates(default_path, template_dir)
    ):
        raise ValueError("同じ名前のテンプレートが既にあります")
    payload = load_template_payload(template_id, default_path, template_dir)
    save_template_payload(
        template_id,
        clean_name,
        payload["リーグ一覧"],
        payload["トーナメント一覧"],
        default_path,
        template_dir,
    )


def delete_league_template(template_id: str, template_dir: Path) -> None:
    if str(template_id) == DEFAULT_TEMPLATE_ID:
        raise ValueError("標準テンプレートは削除できません")
    path = _template_path(template_id, template_dir)
    path.unlink()
