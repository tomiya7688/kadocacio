from __future__ import annotations

import hashlib
import json
import re
import shutil
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from scripts.core.paths import LEAGUE_TEMPLATE_DIR, PROJECT_ROOT
from scripts.core.settings import clamp, parse_hex_color
from scripts.league.league_simulation_session import LeagueSimulationSession
from scripts.league.league_simulation_workers import (
    _run_headless_league_match,
    _run_synchronized_match_batch,
)
from scripts.league.league_templates import (
    DEFAULT_TEMPLATE_ID,
    DEFAULT_TEMPLATE_NAME,
    create_league_template,
    delete_league_template,
    list_league_templates,
    load_template_payload,
    rename_league_template,
    save_template_payload,
)
from scripts.league.league_worker_budget import (
    available_memory_bytes as _available_memory_bytes,
    recommended_worker_count as _recommended_worker_count,
)
from scripts.team.team_data import team_choice_from_snapshot, team_snapshot_from_choice


ROOT = PROJECT_ROOT
LEAGUES_PATH = ROOT / "leagues.json"
LEAGUE_STATE_PATH = ROOT / "league_state.json"
LEAGUE_SAVE_DIR = ROOT / "league_save"
DEFAULT_SAVE_NAME = "自動セーブ"
YEAR_DAYS = 365
SCHEDULE_VERSION = 5
SAVE_VERSION = 3
MAX_LEAGUES = 999
MAX_TOURNAMENTS = 999


def available_memory_bytes() -> int:
    """Compatibility wrapper for callers that patch this measurement."""
    return _available_memory_bytes()


def recommended_worker_count(
    task_count: int,
    *,
    reserve_for_ui: bool = True,
    cpu_limit_percent: int = 100,
) -> int:
    """Compatibility wrapper preserving patchable memory measurements."""
    return _recommended_worker_count(
        task_count,
        reserve_for_ui=reserve_for_ui,
        cpu_limit_percent=cpu_limit_percent,
        available_memory=available_memory_bytes(),
    )


def _default_leagues() -> list[dict]:
    colors = ("#E35D5B", "#4C83D1", "#50A56C", "#B17AD4", "#D99B39")
    leagues = []
    previous = ""
    for letter, color in zip("ABCDE", colors):
        name = f"{letter}リーグ"
        leagues.append({
            "リーグ名": name, "表示色": color, "開幕日": 14,
            "最終節日": 330, "上位リーグ": previous, "所属チーム": [],
        })
        previous = name
    return leagues


def load_competition_template(template_id: str = DEFAULT_TEMPLATE_ID) -> dict:
    try:
        payload = load_template_payload(template_id, LEAGUES_PATH, LEAGUE_TEMPLATE_DIR)
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        payload = {
            "テンプレートID": DEFAULT_TEMPLATE_ID,
            "テンプレート名": DEFAULT_TEMPLATE_NAME,
            "リーグ一覧": _default_leagues(),
            "トーナメント一覧": [],
        }
    leagues = [
        entry for entry in payload.get("リーグ一覧", [])
        if isinstance(entry, dict) and entry.get("リーグ名")
    ]
    tournaments = [
        entry for entry in payload.get("トーナメント一覧", [])
        if isinstance(entry, dict) and entry.get("トーナメント名")
    ]
    return {
        "テンプレートID": str(payload.get("テンプレートID", DEFAULT_TEMPLATE_ID)),
        "テンプレート名": str(payload.get("テンプレート名", DEFAULT_TEMPLATE_NAME)),
        "リーグ一覧": leagues or _default_leagues(),
        "トーナメント一覧": tournaments,
    }


def load_league_definitions(template_id: str = DEFAULT_TEMPLATE_ID) -> list[dict]:
    return load_competition_template(template_id)["リーグ一覧"]


def load_tournament_definitions(template_id: str = DEFAULT_TEMPLATE_ID) -> list[dict]:
    return load_competition_template(template_id)["トーナメント一覧"]


def save_competition_definitions(
    definitions: list[dict],
    tournaments: list[dict],
    *,
    template_id: str = DEFAULT_TEMPLATE_ID,
    template_name: str = DEFAULT_TEMPLATE_NAME,
) -> None:
    save_template_payload(
        template_id,
        template_name,
        definitions,
        tournaments,
        LEAGUES_PATH,
        LEAGUE_TEMPLATE_DIR,
    )


def save_league_definitions(definitions: list[dict]) -> None:
    save_competition_definitions(definitions, load_tournament_definitions())








class LeagueManager:
    """Calendar, schedules, standings and persisted league simulation state."""

    def __init__(
        self,
        team_choices: list[dict],
        *,
        template_id: str = DEFAULT_TEMPLATE_ID,
        load_state: bool = True,
    ) -> None:
        template = load_competition_template(template_id)
        self.template_id = str(template["テンプレートID"])
        self.template_name = str(template["テンプレート名"])
        self.definitions = template["リーグ一覧"]
        self.tournaments = template["トーナメント一覧"]
        self.team_choices: list[dict] = []
        self.base_team_choices: list[dict] = []
        self.choices_by_id: dict[str, dict] = {}
        self.team_snapshots: dict[str, dict] = {}
        self.year = 1
        self.day = 1
        self.selected_leagues: set[str] = set()
        self.selected_tournaments: set[str] = set()
        self.tournament_progress: dict[str, dict] = {}
        self.fixtures: list[dict] = []
        self.watch_fixture_id = ""
        self.last_results: list[dict] = []
        self.history: list[dict] = []
        self._historical_teams_cache: tuple[tuple, list[dict]] | None = None
        self.team_signature: dict[str, list[str]] = {}
        self.league_memberships: dict[str, str] = {}
        self.league_participations: dict[str, list[str]] = {}
        self.season_standings_snapshot: dict[str, list[dict]] = {}
        self.promotion_events: list[dict] = []
        self.schedule_version = 0
        self.save_name = DEFAULT_SAVE_NAME
        self.save_path: Path | None = None
        self.last_save_error = ""
        self._prepare_save_directory()
        if load_state:
            self._load_state()
        self.refresh_teams(team_choices)

    @staticmethod
    def template_entries() -> list[dict]:
        return list_league_templates(LEAGUES_PATH, LEAGUE_TEMPLATE_DIR)

    def competition_template_payload(self) -> dict:
        return {
            "テンプレートID": self.template_id,
            "テンプレート名": self.template_name,
            "リーグ一覧": deepcopy(self.definitions),
            "トーナメント一覧": deepcopy(self.tournaments),
        }

    def duplicate_template(self, name: str) -> str:
        return create_league_template(
            name,
            self.competition_template_payload(),
            LEAGUES_PATH,
            LEAGUE_TEMPLATE_DIR,
        )

    def rename_template(self, name: str) -> None:
        rename_league_template(self.template_id, name, LEAGUES_PATH, LEAGUE_TEMPLATE_DIR)
        self.template_name = str(name).strip()[:40]

    def delete_template(self) -> None:
        delete_league_template(self.template_id, LEAGUE_TEMPLATE_DIR)

    def _save_definitions(self) -> None:
        save_competition_definitions(
            self.definitions,
            self.tournaments,
            template_id=self.template_id,
            template_name=self.template_name,
        )

    @property
    def league_names(self) -> list[str]:
        return [str(entry["リーグ名"]) for entry in self.definitions]

    @property
    def tournament_names(self) -> list[str]:
        return [str(entry["トーナメント名"]) for entry in self.tournaments]

    def tournament_definition(self, tournament_name: str) -> dict:
        return next((entry for entry in self.tournaments if entry.get("トーナメント名") == tournament_name), {})

    @property
    def date_label(self) -> str:
        return f"year{self.year}　{self.day}日目"

    def league_definition(self, league_name: str) -> dict:
        return next((entry for entry in self.definitions if entry.get("リーグ名") == league_name), {})

    def league_color(self, league_name: str) -> tuple[int, int, int]:
        definition = self.league_definition(league_name)
        return parse_hex_color(str(definition.get("表示色", "#D8A945")), (216, 169, 69))

    def add_league(self, league_name: str) -> str:
        if self.season_has_started():
            raise ValueError("開幕後はリーグを追加できません")
        name = str(league_name).strip()[:30]
        if not name:
            raise ValueError("リーグ名が空です")
        if "|" in name:
            raise ValueError("リーグ名に | は使用できません")
        if name in self.league_names:
            raise ValueError("同じ名前のリーグが既にあります")
        if len(self.definitions) >= MAX_LEAGUES:
            raise ValueError(f"リーグは最大{MAX_LEAGUES}個までです")
        palette = ("#E35D5B", "#4C83D1", "#50A56C", "#B17AD4", "#D99B39", "#42A7A1", "#D36F9B")
        self.definitions.append({
            "リーグ名": name,
            "表示色": palette[len(self.definitions) % len(palette)],
            "開幕日": 14,
            "最終節日": 330,
            "上位リーグ": self.league_names[-1] if self.league_names else "",
            "所属チーム": [],
        })
        self._save_definitions()
        self.team_signature[name] = []
        self.save()
        return name

    def add_tournament(self, tournament_name: str) -> str:
        if self.season_has_started():
            raise ValueError("開幕後はトーナメントを追加できません")
        name = str(tournament_name).strip()[:30]
        if not name:
            raise ValueError("トーナメント名が空です")
        if "|" in name:
            raise ValueError("トーナメント名に | は使用できません")
        if name in self.tournament_names or name in self.league_names:
            raise ValueError("同じ名前の大会が既にあります")
        if len(self.tournaments) >= MAX_TOURNAMENTS:
            raise ValueError(f"トーナメントは最大{MAX_TOURNAMENTS}個までです")
        source = self.league_names[0] if self.league_names else ""
        self.tournaments.append({
            "トーナメント名": name,
            "表示色": "#D87C3F",
            "参加方式": "リーグ全体",
            "対象リーグ": source,
            "対象リーグ一覧": [source] if source else [],
            "前年順位上限": 4,
            "開始希望日": 40,
        })
        self.selected_tournaments.add(name)
        self._save_definitions()
        self._rebuild_editor_schedule()
        return name

    def delete_tournament(self, tournament_name: str) -> str:
        if self.season_has_started():
            return "開幕後はトーナメントを削除できません"
        if tournament_name not in self.tournament_names:
            return "削除するトーナメントが見つかりません"
        self.tournaments = [entry for entry in self.tournaments if entry.get("トーナメント名") != tournament_name]
        self.selected_tournaments.discard(tournament_name)
        self.tournament_progress.pop(tournament_name, None)
        self._save_definitions()
        self._rebuild_editor_schedule()
        return ""

    def rename_tournament(self, old_name: str, new_name: str) -> str:
        if self.season_has_started():
            return "開幕後はトーナメント名を変更できません"
        definition = self.tournament_definition(old_name)
        name = str(new_name).strip()[:30]
        if not definition:
            return "変更するトーナメントが見つかりません"
        if not name:
            return "トーナメント名が空です"
        if "|" in name:
            return "トーナメント名に | は使用できません"
        if name != old_name and (name in self.tournament_names or name in self.league_names):
            return "同じ名前の大会が既にあります"
        definition["トーナメント名"] = name
        if old_name in self.selected_tournaments:
            self.selected_tournaments.remove(old_name)
            self.selected_tournaments.add(name)
        self._save_definitions()
        self._rebuild_editor_schedule()
        return ""

    def configure_tournament(self, tournament_name: str, *, source_league: str | None = None,
                             source_leagues: list[str] | None = None,
                             participation: str | None = None, rank_limit: int | None = None,
                             preferred_day: int | None = None) -> str:
        if self.season_has_started():
            return "開幕後はトーナメント設定を変更できません"
        definition = self.tournament_definition(tournament_name)
        if not definition:
            return "トーナメントが見つかりません"
        if source_league is not None:
            if source_league not in self.league_names:
                return "対象リーグが見つかりません"
            definition["対象リーグ"] = source_league
            definition["対象リーグ一覧"] = [source_league]
        if source_leagues is not None:
            cleaned = [name for name in self.league_names if name in {str(value) for value in source_leagues}]
            if not cleaned:
                return "参加元リーグを1つ以上選んでください"
            definition["対象リーグ一覧"] = cleaned
            definition["対象リーグ"] = cleaned[0]
        if participation is not None:
            if participation not in ("リーグ全体", "前年順位"):
                return "参加方式が不正です"
            definition["参加方式"] = participation
        if rank_limit is not None:
            definition["前年順位上限"] = max(1, min(999, int(rank_limit)))
        if preferred_day is not None:
            definition["開始希望日"] = max(1, min(self.promotion_playoff_day(self.year) - 14, int(preferred_day)))
        self._save_definitions()
        self._rebuild_editor_schedule()
        return ""

    def toggle_tournament_source(self, tournament_name: str, league_name: str) -> str:
        definition = self.tournament_definition(tournament_name)
        if not definition or league_name not in self.league_names:
            return "参加元リーグが見つかりません"
        sources = list(definition.get("対象リーグ一覧") or [definition.get("対象リーグ", "")])
        sources = [name for name in sources if name in self.league_names]
        if league_name in sources:
            if len(sources) <= 1:
                return "参加元リーグは1つ以上必要です"
            sources.remove(league_name)
        else:
            sources.append(league_name)
        return self.configure_tournament(tournament_name, source_leagues=sources)

    def season_has_started(self) -> bool:
        return any(fixture.get("played") for fixture in self.fixtures)

    def _rebuild_editor_schedule(self) -> None:
        self.team_signature = self._current_signature()
        self.fixtures = self._build_all_schedules()
        self.watch_fixture_id = ""
        self.last_results = []
        self.season_standings_snapshot = {}
        self.promotion_events = []
        self.schedule_version = SCHEDULE_VERSION
        self.save()

    def assign_team_to_league(self, team_id: str, league_name: str) -> str:
        team_id = str(team_id)
        league_name = str(league_name)
        if self.season_has_started():
            return "開幕後はチーム配置を変更できません。新しいリーグ戦で編集してください"
        if team_id not in self.choices_by_id:
            return "有効なチームが見つかりません"
        if league_name and league_name not in self.league_names:
            return "配置先リーグが見つかりません"
        participating = list(self.league_participations.get(team_id, []))
        if league_name:
            definition = self.league_definition(league_name)
            members = [str(value) for value in definition.setdefault("所属チーム", [])]
            if league_name in participating:
                participating.remove(league_name)
                definition["所属チーム"] = [value for value in members if value != team_id]
            else:
                participating.append(league_name)
                if team_id not in members:
                    definition["所属チーム"].append(team_id)
        else:
            participating = []
            for definition in self.definitions:
                definition["所属チーム"] = [value for value in definition.get("所属チーム", []) if str(value) != team_id]
        self.league_participations[team_id] = [name for name in self.league_names if name in participating]
        priority = self.league_memberships.get(team_id, "")
        if priority not in self.league_participations[team_id]:
            priority = self.league_participations[team_id][0] if self.league_participations[team_id] else ""
        self.league_memberships[team_id] = priority
        self.choices_by_id[team_id]["league"] = priority
        if self.save_path is not None and self.league_participations[team_id]:
            self.team_snapshots[team_id] = team_snapshot_from_choice(self.choices_by_id[team_id])
        self._save_definitions()
        self._rebuild_editor_schedule()
        return ""

    def team_in_league(self, team_id: str, league_name: str) -> bool:
        team_id = str(team_id)
        return (
            league_name in self.league_participations.get(team_id, [])
            or self.league_memberships.get(team_id, "") == league_name
        )

    def set_priority_league(self, team_id: str, league_name: str) -> str:
        team_id = str(team_id)
        if self.season_has_started():
            return "開幕後は優先リーグを変更できません"
        if not self.team_in_league(team_id, league_name):
            return "参加していないリーグは優先できません"
        self.league_memberships[team_id] = league_name
        if team_id in self.choices_by_id:
            self.choices_by_id[team_id]["league"] = league_name
        self._rebuild_editor_schedule()
        return ""

    def rename_league(self, old_name: str, new_name: str) -> str:
        old_name = str(old_name)
        name = str(new_name).strip()[:30]
        if self.season_has_started():
            return "開幕後はリーグ名を変更できません"
        if old_name not in self.league_names:
            return "変更するリーグが見つかりません"
        if not name:
            return "リーグ名が空です"
        if "|" in name:
            return "リーグ名に | は使用できません"
        if name != old_name and name in self.league_names:
            return "同じ名前のリーグが既にあります"
        self.league_definition(old_name)["リーグ名"] = name
        for definition in self.definitions:
            if definition.get("上位リーグ") == old_name:
                definition["上位リーグ"] = name
        for tournament in self.tournaments:
            if tournament.get("対象リーグ") == old_name:
                tournament["対象リーグ"] = name
            tournament["対象リーグ一覧"] = [name if value == old_name else value for value in tournament.get("対象リーグ一覧", [])]
        for team_id, leagues in list(self.league_participations.items()):
            self.league_participations[team_id] = [name if value == old_name else value for value in leagues]
        for team_id, league_name in list(self.league_memberships.items()):
            if league_name == old_name:
                self.league_memberships[team_id] = name
                if team_id in self.choices_by_id:
                    self.choices_by_id[team_id]["league"] = name
        if old_name in self.selected_leagues:
            self.selected_leagues.remove(old_name)
            self.selected_leagues.add(name)
        self._save_definitions()
        self._rebuild_editor_schedule()
        return ""

    def delete_league(self, league_name: str) -> str:
        if self.season_has_started():
            return "開幕後はリーグを削除できません"
        if league_name not in self.league_names:
            return "削除するリーグが見つかりません"
        if len(self.definitions) <= 1:
            return "最後のリーグは削除できません"
        self.definitions = [entry for entry in self.definitions if entry.get("リーグ名") != league_name]
        for definition in self.definitions:
            if definition.get("上位リーグ") == league_name:
                definition["上位リーグ"] = ""
        for team_id, current in list(self.league_memberships.items()):
            if current == league_name:
                self.league_memberships[team_id] = ""
                if team_id in self.choices_by_id:
                    self.choices_by_id[team_id]["league"] = ""
        self.selected_leagues.discard(league_name)
        replacement = self.league_names[0] if self.league_names else ""
        for tournament in self.tournaments:
            if tournament.get("対象リーグ") == league_name:
                tournament["対象リーグ"] = replacement
            tournament["対象リーグ一覧"] = [value for value in tournament.get("対象リーグ一覧", []) if value != league_name]
        for team_id, leagues in list(self.league_participations.items()):
            self.league_participations[team_id] = [value for value in leagues if value != league_name]
            if self.league_memberships.get(team_id, "") not in self.league_participations[team_id]:
                self.league_memberships[team_id] = self.league_participations[team_id][0] if self.league_participations[team_id] else ""
        if not self.selected_leagues and self.league_names:
            self.selected_leagues.add(self.league_names[0])
        self._save_definitions()
        self._rebuild_editor_schedule()
        return ""

    def set_fixture_day(self, fixture_id: str, day: int) -> str:
        fixture = self.fixture(str(fixture_id))
        if fixture is None:
            return "試合が見つかりません"
        if fixture.get("played"):
            return "終了済みの試合日は変更できません"
        if fixture.get("fixture_type") == "PLAYOFF":
            return "入れ替え戦は12月第2土曜日固定です"
        maximum = self.promotion_playoff_day(self.year) - 7
        fixture["day"] = max(self.day, min(maximum, int(day)))
        self.save()
        return ""

    def upper_league(self, league_name: str) -> str:
        upper = str(self.league_definition(league_name).get("上位リーグ", "")).strip()
        return upper if upper in self.league_names and upper != league_name else ""

    def set_upper_league(self, league_name: str, upper_league: str) -> str:
        if league_name not in self.league_names:
            return "リーグが見つかりません"
        upper = str(upper_league).strip()
        if upper and upper not in self.league_names:
            return "上位リーグが見つかりません"
        if upper == league_name:
            return "同じリーグを上位には設定できません"
        if self.season_has_started():
            return "開幕後は上下関係を変更できません"
        cursor = upper
        visited = {league_name}
        while cursor:
            if cursor in visited:
                return "リーグの上下関係が循環します"
            visited.add(cursor)
            cursor = self.upper_league(cursor)
        self.league_definition(league_name)["上位リーグ"] = upper
        self.fixtures = [fixture for fixture in self.fixtures if fixture.get("fixture_type") != "PLAYOFF"]
        self.season_standings_snapshot = {}
        self._save_definitions()
        self.save()
        return ""

    def cycle_upper_league(self, league_name: str, amount: int) -> str:
        choices = ["", *[name for name in self.league_names if name != league_name]]
        current = self.upper_league(league_name)
        start = choices.index(current) if current in choices else 0
        for offset in range(1, len(choices) + 1):
            candidate = choices[(start + int(amount) * offset) % len(choices)]
            error = self.set_upper_league(league_name, candidate)
            if not error:
                return ""
        return "有効な上位リーグを設定できません"

    def teams_in_league(self, league_name: str) -> list[dict]:
        return sorted(
            (
                choice for choice in self.team_choices
                if self.team_in_league(str(choice.get("id", "")), league_name)
            ),
            key=lambda choice: str(choice.get("name", "")).casefold(),
        )

    def definition_participations(self) -> dict[str, list[str]]:
        memberships: dict[str, list[str]] = {}
        for definition in self.definitions:
            league_name = str(definition.get("リーグ名", ""))
            for team_id in definition.get("所属チーム", []):
                memberships.setdefault(str(team_id), []).append(league_name)
        return memberships

    def definition_memberships(self) -> dict[str, str]:
        return {team_id: leagues[0] if leagues else "" for team_id, leagues in self.definition_participations().items()}

    @staticmethod
    def _replace_team_identifier(value, old_id: str, new_id: str):
        if isinstance(value, dict):
            return {
                (new_id if str(key) == old_id else key): LeagueManager._replace_team_identifier(item, old_id, new_id)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [LeagueManager._replace_team_identifier(item, old_id, new_id) for item in value]
        return new_id if value == old_id else value

    def rename_team_reference(self, old_id: str, new_id: str) -> None:
        """Keep the active season valid when a team JSON is renamed or moved."""
        if not old_id or old_id == new_id:
            return
        self.definitions = self._replace_team_identifier(self.definitions, old_id, new_id)
        self.league_memberships = self._replace_team_identifier(self.league_memberships, old_id, new_id)
        self.league_participations = self._replace_team_identifier(self.league_participations, old_id, new_id)
        self.fixtures = self._replace_team_identifier(self.fixtures, old_id, new_id)
        self.last_results = self._replace_team_identifier(self.last_results, old_id, new_id)
        self.history = self._replace_team_identifier(self.history, old_id, new_id)
        self.team_signature = self._replace_team_identifier(self.team_signature, old_id, new_id)
        self.season_standings_snapshot = self._replace_team_identifier(self.season_standings_snapshot, old_id, new_id)
        self.promotion_events = self._replace_team_identifier(self.promotion_events, old_id, new_id)
        self.tournament_progress = self._replace_team_identifier(self.tournament_progress, old_id, new_id)
        self._save_definitions()
        self.save()

    def _current_signature(self) -> dict[str, list[str]]:
        return {
            league: [str(choice["id"]) for choice in self.teams_in_league(league)]
            for league in self.league_names
        }

    def _migrate_stale_team_ids(self) -> bool:
        """Resolve old root-level IDs after a team was moved into a folder.

        A basename is only migrated when it identifies exactly one current team,
        so two folders may safely contain different teams with the same filename.
        """
        current_ids = {str(choice["id"]) for choice in self.team_choices}
        ids_by_filename: dict[str, list[str]] = {}
        for team_id in current_ids:
            filename = team_id.removeprefix("json:").rsplit("/", 1)[-1].casefold()
            ids_by_filename.setdefault(filename, []).append(team_id)
        referenced_ids = {
            str(team_id)
            for definition in self.definitions
            for team_id in definition.get("所属チーム", [])
        } | set(self.league_memberships) | set(self.league_participations)
        replacements = {}
        for old_id in referenced_ids - current_ids:
            filename = old_id.removeprefix("json:").rsplit("/", 1)[-1].casefold()
            candidates = ids_by_filename.get(filename, [])
            if len(candidates) == 1:
                replacements[old_id] = candidates[0]
        for old_id, new_id in replacements.items():
            self.definitions = self._replace_team_identifier(self.definitions, old_id, new_id)
            self.league_memberships = self._replace_team_identifier(self.league_memberships, old_id, new_id)
            self.league_participations = self._replace_team_identifier(self.league_participations, old_id, new_id)
            self.fixtures = self._replace_team_identifier(self.fixtures, old_id, new_id)
            self.last_results = self._replace_team_identifier(self.last_results, old_id, new_id)
            self.history = self._replace_team_identifier(self.history, old_id, new_id)
            self.team_signature = self._replace_team_identifier(self.team_signature, old_id, new_id)
            self.season_standings_snapshot = self._replace_team_identifier(self.season_standings_snapshot, old_id, new_id)
            self.promotion_events = self._replace_team_identifier(self.promotion_events, old_id, new_id)
            self.tournament_progress = self._replace_team_identifier(self.tournament_progress, old_id, new_id)
        if replacements:
            self._save_definitions()
        return bool(replacements)

    def refresh_teams(self, team_choices: list[dict]) -> None:
        self.base_team_choices = deepcopy(list(team_choices))
        current_choices = deepcopy(list(team_choices))
        restored = {
            team_id: choice
            for team_id, snapshot in self.team_snapshots.items()
            if (choice := team_choice_from_snapshot(snapshot)) is not None
        }
        # Saved participants override teams/*.json. Teams that were not part of
        # this save remain available for pre-season placement in the editor.
        self.team_choices = []
        seen: set[str] = set()
        for external in current_choices:
            team_id = str(external.get("id", ""))
            self.team_choices.append(deepcopy(restored.get(team_id, external)))
            seen.add(team_id)
        self.team_choices.extend(
            deepcopy(choice) for team_id, choice in restored.items() if team_id not in seen
        )
        self._migrate_stale_team_ids()
        configured_participations = self.definition_participations()
        if not self.league_participations:
            if self.league_memberships:
                self.league_participations = {
                    str(team_id): [str(league)] if str(league) in self.league_names else []
                    for team_id, league in self.league_memberships.items()
                }
            else:
                self.league_participations = deepcopy(configured_participations)
        if not self.league_memberships:
            configured = self.definition_memberships()
            self.league_memberships = {
                str(choice["id"]): str(choice["league"])
                if "league" in choice else configured.get(str(choice["id"]), "")
                for choice in self.team_choices
            }
        for team_id, league_name in list(self.league_memberships.items()):
            if league_name not in self.league_names:
                self.league_memberships[team_id] = ""
        for team_id, leagues in list(self.league_participations.items()):
            self.league_participations[team_id] = [name for name in self.league_names if name in leagues]
        for choice in self.team_choices:
            choice_id = str(choice["id"])
            self.league_participations.setdefault(choice_id, configured_participations.get(choice_id, []))
            explicit_league = str(choice.get("league", "")) if "league" in choice else ""
            if explicit_league in self.league_names:
                self.league_participations[choice_id] = [explicit_league]
            if not self.league_participations[choice_id] and self.league_memberships.get(choice_id, "") in self.league_names:
                self.league_participations[choice_id] = [self.league_memberships[choice_id]]
            if self.league_memberships.get(choice_id, "") not in self.league_participations[choice_id]:
                self.league_memberships[choice_id] = self.league_participations[choice_id][0] if self.league_participations[choice_id] else ""
            if choice_id in self.league_memberships:
                choice["league"] = self.league_memberships[choice_id]
            else:
                self.league_memberships[choice_id] = self.league_participations[choice_id][0] if self.league_participations[choice_id] else ""
        self.choices_by_id = {str(choice["id"]): choice for choice in self.team_choices}
        signature = self._current_signature()
        if signature != self.team_signature or not self.fixtures or self.schedule_version != SCHEDULE_VERSION:
            had_existing_schedule = bool(self.fixtures)
            self.team_signature = signature
            self.fixtures = self._build_all_schedules()
            self.schedule_version = SCHEDULE_VERSION
            self.watch_fixture_id = ""
            self.last_results = []
            # A changed team composition or calendar cannot be mixed safely
            # with already elapsed dates from the old schedule.
            if had_existing_schedule:
                self.day = 1
        for fixture in self.fixtures:
            home = self.choices_by_id.get(str(fixture.get("home_id")))
            away = self.choices_by_id.get(str(fixture.get("away_id")))
            if home is not None:
                fixture["home_name"] = home.get("name", fixture.get("home_name", ""))
            if away is not None:
                fixture["away_name"] = away.get("name", fixture.get("away_name", ""))
        if not self.selected_leagues:
            playable = [name for name in self.league_names if len(self.teams_in_league(name)) >= 2]
            self.selected_leagues = set(playable[:1] or self.league_names[:1])
        self.selected_leagues.intersection_update(self.league_names)
        self.selected_tournaments.intersection_update(self.tournament_names)
        self.save()

    def _participant_team_ids(self) -> set[str]:
        team_ids = {
            str(team_id)
            for team_id, leagues in self.league_participations.items()
            if leagues
        }
        for fixture in self.fixtures:
            for key in ("home_id", "away_id"):
                team_id = str(fixture.get(key, ""))
                if team_id:
                    team_ids.add(team_id)
        return team_ids

    def _update_team_snapshots(self) -> None:
        """Persist current save-local abilities for every participating team."""
        for team_id in self._participant_team_ids():
            choice = self.choices_by_id.get(team_id)
            if choice is not None:
                self.team_snapshots[team_id] = team_snapshot_from_choice(choice)

    @staticmethod
    def _safe_save_stem(name: str) -> str:
        cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", str(name).strip())[:48]
        return cleaned.strip(" .") or DEFAULT_SAVE_NAME

    def _prepare_save_directory(self) -> None:
        try:
            LEAGUE_SAVE_DIR.mkdir(parents=True, exist_ok=True)
            migrated = LEAGUE_SAVE_DIR / f"{DEFAULT_SAVE_NAME}.json"
            if LEAGUE_STATE_PATH.exists() and not migrated.exists():
                shutil.copy2(LEAGUE_STATE_PATH, migrated)
        except OSError:
            return

    def _default_save_path(self) -> Path:
        return LEAGUE_SAVE_DIR / f"{DEFAULT_SAVE_NAME}.json"

    def _apply_state(self, state: dict) -> None:
        self._historical_teams_cache = None
        competition = state.get("competition_template", {})
        if isinstance(competition, dict):
            saved_leagues = competition.get("リーグ一覧", [])
            saved_tournaments = competition.get("トーナメント一覧", [])
            if isinstance(saved_leagues, list) and saved_leagues:
                self.template_id = str(competition.get("テンプレートID", DEFAULT_TEMPLATE_ID))
                self.template_name = str(competition.get("テンプレート名", DEFAULT_TEMPLATE_NAME))
                self.definitions = deepcopy(saved_leagues)
                self.tournaments = deepcopy(saved_tournaments) if isinstance(saved_tournaments, list) else []
        self.save_name = str(state.get("save_name", self.save_name or DEFAULT_SAVE_NAME))
        self.year = max(1, int(state.get("year", 1)))
        self.day = int(clamp(float(state.get("day", 1)), 1, YEAR_DAYS))
        self.selected_leagues = {str(name) for name in state.get("selected_leagues", [])}
        self.selected_tournaments = {str(name) for name in state.get("selected_tournaments", [])}
        self.fixtures = [fixture for fixture in state.get("fixtures", []) if isinstance(fixture, dict)]
        self.watch_fixture_id = str(state.get("watch_fixture_id", ""))
        self.last_results = [result for result in state.get("last_results", []) if isinstance(result, dict)]
        self.history = [entry for entry in state.get("history", []) if isinstance(entry, dict)]
        memberships = state.get("league_memberships", {})
        self.league_memberships = memberships if isinstance(memberships, dict) else {}
        participations = state.get("league_participations", {})
        self.league_participations = participations if isinstance(participations, dict) else {}
        snapshots = state.get("season_standings_snapshot", {})
        self.season_standings_snapshot = snapshots if isinstance(snapshots, dict) else {}
        self.promotion_events = [entry for entry in state.get("promotion_events", []) if isinstance(entry, dict)]
        progress = state.get("tournament_progress", {})
        self.tournament_progress = progress if isinstance(progress, dict) else {}
        signature = state.get("team_signature", {})
        self.team_signature = signature if isinstance(signature, dict) else {}
        saved_teams = state.get("チームスナップショット", {})
        self.team_snapshots = saved_teams if isinstance(saved_teams, dict) else {}
        self.schedule_version = int(state.get("schedule_version", 0))

    def _load_state(self, path: Path | None = None) -> None:
        target = path or self._default_save_path()
        try:
            with target.open("r", encoding="utf-8-sig") as file:
                state = json.load(file)
            if not isinstance(state, dict):
                return
            self._apply_state(state)
            self.save_path = target
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            if path is None:
                self.save_path = target

    def _state_payload(self) -> dict:
        self._update_team_snapshots()
        return {
            "save_version": SAVE_VERSION,
            "save_name": self.save_name,
            "saved_at": datetime.now().isoformat(timespec="seconds"),
            "competition_template": self.competition_template_payload(),
            "year": self.year,
            "day": self.day,
            "selected_leagues": sorted(self.selected_leagues),
            "selected_tournaments": sorted(self.selected_tournaments),
            "fixtures": self.fixtures,
            "watch_fixture_id": self.watch_fixture_id,
            "last_results": self.last_results,
            # Completed seasons are the permanent record of this save slot.
            # Do not cap this list: a long-running player league must retain
            # every season's table and every played fixture.
            "history": self.history,
            "league_memberships": self.league_memberships,
            "league_participations": self.league_participations,
            "season_standings_snapshot": self.season_standings_snapshot,
            "promotion_events": self.promotion_events,
            "tournament_progress": self.tournament_progress,
            "team_signature": self.team_signature,
            "チームスナップショット": self.team_snapshots,
            "schedule_version": self.schedule_version,
        }

    def save(self) -> None:
        # A deleted active slot stays deleted until the user creates or loads
        # another slot; ordinary refreshes must not silently resurrect it.
        if self.save_path is None:
            return
        target = self.save_path
        try:
            target.parent.mkdir(parents=True, exist_ok=True)
            temporary = target.with_suffix(".json.tmp")
            with temporary.open("w", encoding="utf-8") as file:
                json.dump(self._state_payload(), file, ensure_ascii=False, indent=2)
            temporary.replace(target)
            self.save_path = target
            self.last_save_error = ""
        except OSError as error:
            self.last_save_error = str(error)

    def list_saves(self) -> list[dict]:
        self._prepare_save_directory()
        saves: list[dict] = []
        try:
            paths = sorted(LEAGUE_SAVE_DIR.glob("*.json"), key=lambda item: item.stat().st_mtime, reverse=True)
        except OSError:
            return saves
        known_team_ids = {str(choice.get("id", "")) for choice in self.base_team_choices}
        for path in paths:
            errors: list[str] = []
            state: dict = {}
            try:
                with path.open("r", encoding="utf-8-sig") as file:
                    loaded = json.load(file)
                if not isinstance(loaded, dict):
                    errors.append("JSONの一番外側がオブジェクトではありません")
                else:
                    state = loaded
            except (OSError, json.JSONDecodeError, UnicodeError) as error:
                errors.append(f"JSONを読み込めません: {error}")
            fixtures = state.get("fixtures", [])
            if state and not isinstance(fixtures, list):
                errors.append("fixturesが配列ではありません")
                fixtures = []
            fixture_ids: set[str] = set()
            snapshots = state.get("チームスナップショット", {})
            if snapshots and not isinstance(snapshots, dict):
                errors.append("チームスナップショットがオブジェクトではありません")
                snapshots = {}
            snapshot_ids: set[str] = set()
            if isinstance(snapshots, dict):
                for team_id, snapshot in snapshots.items():
                    restored = team_choice_from_snapshot(snapshot)
                    if restored is None or str(restored.get("id", "")) != str(team_id):
                        errors.append(f"保存チームを復元できません: {team_id}")
                    else:
                        snapshot_ids.add(str(team_id))
            available_team_ids = known_team_ids | snapshot_ids
            memberships = state.get("league_memberships", {})
            if memberships and not isinstance(memberships, dict):
                errors.append("league_membershipsがオブジェクトではありません")
            elif isinstance(memberships, dict):
                for team_id, league_name in memberships.items():
                    if available_team_ids and str(team_id) not in available_team_ids:
                        errors.append(f"所属情報のチームが見つかりません: {team_id}")
            for fixture in fixtures:
                if not isinstance(fixture, dict):
                    errors.append("試合データに不正な項目があります")
                    continue
                fixture_id = str(fixture.get("id", ""))
                if not fixture_id or fixture_id in fixture_ids:
                    errors.append("試合IDが空か重複しています")
                fixture_ids.add(fixture_id)
                for key, label in (("home_id", "ホーム"), ("away_id", "アウェー")):
                    team_id = str(fixture.get(key, ""))
                    if team_id and available_team_ids and team_id not in available_team_ids:
                        errors.append(f"{label}チームが見つかりません: {fixture.get(key)}")
            saves.append({
                "path": path,
                "file_name": path.name,
                "name": str(state.get("save_name", path.stem)),
                "year": max(1, int(state.get("year", 1))) if state else 1,
                "day": int(state.get("day", 1)) if state else 1,
                "saved_at": str(state.get("saved_at", "")),
                "template_name": str(
                    state.get("competition_template", {}).get("テンプレート名", DEFAULT_TEMPLATE_NAME)
                    if isinstance(state.get("competition_template", {}), dict)
                    else DEFAULT_TEMPLATE_NAME
                ),
                "errors": list(dict.fromkeys(errors))[:6],
                "loadable": not errors,
            })
        return saves

    def create_new_save(self, name: str) -> Path:
        stem = self._safe_save_stem(name)
        target = LEAGUE_SAVE_DIR / f"{stem}.json"
        suffix = 2
        while target.exists():
            target = LEAGUE_SAVE_DIR / f"{stem}_{suffix}.json"
            suffix += 1
        self.save_name = target.stem
        self.save_path = target
        self.year = 1
        self.day = 1
        self.selected_leagues = set()
        self.selected_tournaments = set()
        self.tournament_progress = {}
        self.fixtures = []
        self.watch_fixture_id = ""
        self.last_results = []
        self.history = []
        self._historical_teams_cache = None
        self.team_snapshots = {}
        self.team_choices = deepcopy(self.base_team_choices)
        self.choices_by_id = {str(choice["id"]): choice for choice in self.team_choices}
        configured_participations = self.definition_participations()
        self.league_participations = deepcopy(configured_participations)
        configured = self.definition_memberships()
        self.league_memberships = {
            str(choice["id"]): str(choice["league"])
            if "league" in choice else configured.get(str(choice["id"]), "")
            for choice in self.team_choices
        }
        for choice in self.team_choices:
            team_id = str(choice["id"])
            if self.league_memberships[team_id] not in self.league_participations.get(team_id, []):
                entries = self.league_participations.get(team_id, [])
                self.league_memberships[team_id] = entries[0] if entries else ""
            choice["league"] = self.league_memberships[team_id]
        self.season_standings_snapshot = {}
        self.promotion_events = []
        self.team_signature = self._current_signature()
        self.fixtures = self._build_all_schedules()
        self.schedule_version = SCHEDULE_VERSION
        self._update_team_snapshots()
        playable = [name for name in self.league_names if len(self.teams_in_league(name)) >= 2]
        self.selected_leagues = set(playable[:1] or self.league_names[:1])
        self.selected_tournaments = set(self.tournament_names)
        self.save()
        return target

    def load_save(self, path_or_name: str | Path) -> list[str]:
        requested = Path(path_or_name)
        target = requested if requested.is_absolute() else LEAGUE_SAVE_DIR / requested.name
        try:
            target.resolve().relative_to(LEAGUE_SAVE_DIR.resolve())
        except (OSError, ValueError):
            return ["league_saveフォルダ外のファイルは読み込めません"]
        info = next((item for item in self.list_saves() if item["path"].resolve() == target.resolve()), None)
        if info is None:
            return ["セーブデータが見つかりません"]
        if info["errors"]:
            return list(info["errors"])
        self._load_state(target)
        self.refresh_teams(self.base_team_choices)
        return []

    def delete_save(self, path_or_name: str | Path) -> str:
        requested = Path(path_or_name)
        target = requested if requested.is_absolute() else LEAGUE_SAVE_DIR / requested.name
        try:
            target.resolve().relative_to(LEAGUE_SAVE_DIR.resolve())
            target.unlink()
            if self.save_path and self.save_path.resolve() == target.resolve():
                self.save_path = None
            return ""
        except (OSError, ValueError) as error:
            return str(error)

    def _round_robin_rounds(self, team_ids: list[str]) -> list[list[tuple[str, str]]]:
        rotation: list[str | None] = list(team_ids)
        if len(rotation) % 2:
            rotation.append(None)
        if len(rotation) < 2:
            return []
        first_leg: list[list[tuple[str, str]]] = []
        for round_index in range(len(rotation) - 1):
            pairings: list[tuple[str, str]] = []
            for index in range(len(rotation) // 2):
                first = rotation[index]
                second = rotation[-1 - index]
                if first is None or second is None:
                    continue
                if (round_index + index) % 2:
                    first, second = second, first
                pairings.append((first, second))
            first_leg.append(pairings)
            rotation = [rotation[0], rotation[-1], *rotation[1:-1]]
        return first_leg + [[(away, home) for home, away in games] for games in first_leg]

    def _build_all_schedules(self) -> list[dict]:
        fixtures: list[dict] = []
        for league_name in self.league_names:
            team_ids = [str(choice["id"]) for choice in self.teams_in_league(league_name)]
            rounds = self._round_robin_rounds(team_ids)
            definition = self.league_definition(league_name)
            start_day = max(1, int(definition.get("開幕日", definition.get("開始日", 14))))
            # 入れ替え戦より前にレギュラーシーズンを完了させる。
            final_day = int(clamp(
                float(definition.get("最終節日", 330)),
                start_day,
                self.promotion_playoff_day(self.year) - 7,
            ))
            for round_index, games in enumerate(rounds, start=1):
                if len(rounds) <= 1:
                    match_day = round((start_day + final_day) * 0.5)
                else:
                    progress = (round_index - 1) / (len(rounds) - 1)
                    match_day = round(start_day + (final_day - start_day) * progress)
                for match_index, (home_id, away_id) in enumerate(games, start=1):
                    home = self.choices_by_id.get(home_id, {})
                    away = self.choices_by_id.get(away_id, {})
                    fixtures.append({
                        "id": f"year{self.year}:{league_name}:R{round_index}:M{match_index}",
                        "year": self.year,
                        "league": league_name,
                        "round": round_index,
                        "day": match_day,
                        "home_id": home_id,
                        "away_id": away_id,
                        "home_name": home.get("name", home_id),
                        "away_name": away.get("name", away_id),
                        "fixture_type": "REGULAR",
                        "played": False,
                        "home_score": None,
                        "away_score": None,
                        "watched": False,
                    })
        self._resolve_multi_league_conflicts(fixtures)
        occupied_days = {int(fixture["day"]) for fixture in fixtures}
        self.tournament_progress = {}
        for definition in self.tournaments:
            name = str(definition.get("トーナメント名", ""))
            participants = self._tournament_participants(definition)
            if len(participants) < 2:
                continue
            preferred = int(definition.get("開始希望日", 40))
            day = self._next_free_competition_day(preferred, occupied_days)
            created, byes = self._make_tournament_round(name, participants, 1, day)
            fixtures.extend(created)
            occupied_days.add(day)
            self.tournament_progress[name] = {"round": 1, "byes": byes, "champion_id": ""}
        return fixtures

    def _resolve_multi_league_conflicts(self, fixtures: list[dict]) -> None:
        """Keep priority-league dates and move a team's lower-priority clashes."""
        maximum = self.promotion_playoff_day(self.year) - 7
        occupied: dict[str, set[int]] = {}
        ordered = sorted(fixtures, key=lambda fixture: (
            -sum(self.league_memberships.get(str(fixture.get(key, "")), "") == fixture.get("league") for key in ("home_id", "away_id")),
            int(fixture.get("day", 0)),
            str(fixture.get("id", "")),
        ))
        for fixture in ordered:
            team_ids = (str(fixture.get("home_id", "")), str(fixture.get("away_id", "")))
            day = int(fixture.get("day", 1))
            for team_id in team_ids:
                occupied.setdefault(team_id, set())
            if any(day in occupied[team_id] for team_id in team_ids):
                candidate = day + 1
                while candidate <= maximum and any(candidate in occupied[team_id] for team_id in team_ids):
                    candidate += 1
                if candidate > maximum:
                    candidate = day - 1
                    while candidate >= 1 and any(candidate in occupied[team_id] for team_id in team_ids):
                        candidate -= 1
                if candidate >= 1:
                    day = candidate
                    fixture["day"] = day
            for team_id in team_ids:
                occupied[team_id].add(day)

    def _tournament_participants(self, definition: dict) -> list[str]:
        sources = list(definition.get("対象リーグ一覧") or [definition.get("対象リーグ", "")])
        sources = [str(name) for name in sources if str(name) in self.league_names]
        current: list[str] = []
        for league_name in sources:
            current.extend(str(choice["id"]) for choice in self.teams_in_league(league_name))
        current = list(dict.fromkeys(current))
        if definition.get("参加方式") != "前年順位":
            return current
        limit = max(1, int(definition.get("前年順位上限", 4)))
        previous = next((entry for entry in reversed(self.history) if int(entry.get("year", 0)) == self.year - 1), None)
        ranked: list[str] = []
        for league_name in sources:
            rows = previous.get("leagues", {}).get(league_name, {}).get("standings", []) if previous else []
            league_ranked = [str(row.get("team_id", "")) for row in rows if str(row.get("team_id", "")) in self.choices_by_id]
            if not league_ranked:
                league_ranked = [str(choice["id"]) for choice in self.teams_in_league(league_name)]
            ranked.extend(league_ranked[:limit])
        return list(dict.fromkeys(ranked))

    def _next_free_competition_day(self, preferred: int, occupied_days: set[int]) -> int:
        maximum = self.promotion_playoff_day(self.year) - 7
        day = max(self.day, min(maximum, int(preferred)))
        while day in occupied_days and day < maximum:
            day += 1
        while day in occupied_days and day > self.day:
            day -= 1
        return day

    def _make_tournament_round(self, name: str, team_ids: list[str], round_number: int, day: int) -> tuple[list[dict], list[str]]:
        ids = list(team_ids)
        byes = ids[-1:] if len(ids) % 2 else []
        paired = ids[:-1] if byes else ids
        fixtures = []
        for index in range(0, len(paired), 2):
            home_id, away_id = paired[index], paired[index + 1]
            home = self.choices_by_id.get(home_id, {})
            away = self.choices_by_id.get(away_id, {})
            fixtures.append({
                "id": f"year{self.year}:TOURNAMENT:{name}:R{round_number}:M{index // 2 + 1}",
                "year": self.year, "league": name, "tournament": name,
                "round": round_number, "day": day,
                "home_id": home_id, "away_id": away_id,
                "home_name": home.get("name", home_id), "away_name": away.get("name", away_id),
                "fixture_type": "TOURNAMENT", "competition_label": f"{name} 第{round_number}回戦",
                "played": False, "home_score": None, "away_score": None, "watched": False,
            })
        return fixtures, byes

    def _advance_tournament_if_ready(self, tournament_name: str) -> None:
        progress = self.tournament_progress.get(tournament_name)
        if not progress or progress.get("champion_id"):
            return
        round_number = int(progress.get("round", 1))
        current = [fixture for fixture in self.fixtures if fixture.get("tournament") == tournament_name and int(fixture.get("round", 0)) == round_number]
        if not current or any(not fixture.get("played") for fixture in current):
            return
        winners = list(progress.get("byes", []))
        for fixture in current:
            home_won = int(fixture.get("home_score", 0)) > int(fixture.get("away_score", 0))
            if int(fixture.get("home_score", 0)) == int(fixture.get("away_score", 0)):
                home_won = int(fixture.get("home_penalties", 0)) > int(fixture.get("away_penalties", 0))
            winners.append(str(fixture["home_id"] if home_won else fixture["away_id"]))
        if len(winners) == 1:
            progress["champion_id"] = winners[0]
            return
        occupied = {int(fixture["day"]) for fixture in self.fixtures}
        preferred = max(int(fixture["day"]) for fixture in current) + 1
        day = self._next_free_competition_day(preferred, occupied)
        created, byes = self._make_tournament_round(tournament_name, winners, round_number + 1, day)
        self.fixtures.extend(created)
        progress.update({"round": round_number + 1, "byes": byes})

    @staticmethod
    def promotion_playoff_day(year: int) -> int:
        """Day number of the second Saturday in December.

        year1 starts on Monday and this 365-day calendar advances weekdays by
        one each year.  The result is always between day 342 and day 348.
        """
        jan_first_weekday = (max(1, int(year)) - 1) % 7  # Monday == 0
        december_first_weekday = (jan_first_weekday + 334) % 7
        return 335 + ((5 - december_first_weekday) % 7) + 7

    def _fixture_selected(self, fixture: dict) -> bool:
        if fixture.get("fixture_type") == "TOURNAMENT":
            return str(fixture.get("tournament", "")) in self.selected_tournaments
        if fixture.get("fixture_type") == "PLAYOFF":
            return bool({str(fixture.get("upper_league", "")), str(fixture.get("lower_league", ""))} & self.selected_leagues)
        return fixture.get("league") in self.selected_leagues

    def fixtures_on_day(self, day: int, *, selected_only: bool = True, unplayed_only: bool = False) -> list[dict]:
        return [
            fixture for fixture in self.fixtures
            if fixture.get("year") == self.year
            and fixture.get("day") == day
            and (not selected_only or self._fixture_selected(fixture))
            and (not unplayed_only or not fixture.get("played"))
        ]

    def next_matchday(self) -> int | None:
        self.ensure_promotion_playoffs()
        days = [
            int(fixture["day"]) for fixture in self.fixtures
            if self._fixture_selected(fixture)
            and not fixture.get("played")
            and int(fixture.get("day", 0)) > self.day
        ]
        return min(days) if days else None

    def next_fixtures(self) -> list[dict]:
        next_day = self.next_matchday()
        return self.fixtures_on_day(next_day, unplayed_only=True) if next_day is not None else []

    def fixture(self, fixture_id: str) -> dict | None:
        return next((fixture for fixture in self.fixtures if fixture.get("id") == fixture_id), None)

    def toggle_league(self, league_name: str) -> list[dict]:
        if league_name not in self.league_names:
            return []
        overdue: list[dict] = []
        if league_name in self.selected_leagues:
            self.selected_leagues.remove(league_name)
            fixture = self.fixture(self.watch_fixture_id)
            if fixture and not self._fixture_selected(fixture):
                self.watch_fixture_id = ""
        else:
            self.selected_leagues.add(league_name)
            overdue = [
                fixture for fixture in self.fixtures
                if fixture.get("league") == league_name
                and not fixture.get("played")
                and int(fixture.get("day", YEAR_DAYS + 1)) <= self.day
            ]
            self.last_results = []
        self.save()
        return overdue

    def toggle_tournament(self, tournament_name: str) -> list[dict]:
        if tournament_name not in self.tournament_names:
            return []
        overdue: list[dict] = []
        if tournament_name in self.selected_tournaments:
            self.selected_tournaments.remove(tournament_name)
        else:
            self.selected_tournaments.add(tournament_name)
            overdue = [fixture for fixture in self.fixtures if fixture.get("tournament") == tournament_name
                       and not fixture.get("played") and int(fixture.get("day", YEAR_DAYS + 1)) <= self.day]
        self.save()
        return overdue

    def toggle_watch(self, fixture_id: str) -> None:
        fixture = self.fixture(fixture_id)
        if fixture is None or fixture.get("played") or not self._fixture_selected(fixture):
            return
        self.watch_fixture_id = "" if self.watch_fixture_id == fixture_id else fixture_id
        self.save()

    def simulate_fixture(self, fixture: dict) -> dict:
        """Synchronous compatibility path; normal UI uses LeagueSimulationSession."""
        if fixture.get("played"):
            return self.result_from_fixture(fixture)
        home_choice = self.choices_by_id.get(str(fixture.get("home_id")))
        away_choice = self.choices_by_id.get(str(fixture.get("away_id")))
        if home_choice is None or away_choice is None:
            result = {"fixture_id": fixture["id"], "home_score": 0, "away_score": 0}
        else:
            result = _run_headless_league_match({"fixture": fixture, "home_choice": home_choice, "away_choice": away_choice})
        self.apply_headless_results([result])
        return self.result_from_fixture(fixture)

    def apply_headless_results(self, results: list[dict]) -> None:
        accumulated = [result for result in self.last_results if int(result.get("day", -1)) == self.day]
        known = {str(result.get("fixture_id")) for result in accumulated}
        for result in results:
            fixture = self.fixture(str(result.get("fixture_id", "")))
            if fixture is None or fixture.get("played") or result.get("fulltime", True) is not True:
                continue
            self.record_result(fixture, int(result.get("home_score", 0)), int(result.get("away_score", 0)), watched=False)
            self._resolve_promotion_playoff(fixture)
            fixture["match_stats"] = {
                "home_shots": int(result.get("home_shots", 0)),
                "away_shots": int(result.get("away_shots", 0)),
                "home_possession": float(result.get("home_possession", 0.0)),
                "away_possession": float(result.get("away_possession", 0.0)),
                "goal_scorers": result.get("goal_scorers", []),
                "engine_steps": int(result.get("engine_steps", 0)),
            }
            if fixture["id"] not in known:
                accumulated.append(self.result_from_fixture(fixture))
                known.add(fixture["id"])
        self.last_results = sorted(accumulated, key=lambda item: (str(item["league"]), int(item["round"]), str(item["home_name"])))
        self.ensure_promotion_playoffs()
        self.save()

    def record_result(self, fixture: dict, home_score: int, away_score: int, *, watched: bool) -> None:
        fixture["played"] = True
        fixture["home_score"] = max(0, int(home_score))
        fixture["away_score"] = max(0, int(away_score))
        fixture["watched"] = bool(watched)
        if fixture.get("fixture_type") == "TOURNAMENT" and fixture["home_score"] == fixture["away_score"]:
            seed = int.from_bytes(hashlib.sha256(str(fixture.get("id", "")).encode("utf-8")).digest()[:2], "big")
            fixture["home_penalties"] = 5 if seed % 2 == 0 else 4
            fixture["away_penalties"] = 4 if seed % 2 == 0 else 5
        if fixture.get("fixture_type") == "TOURNAMENT":
            self._advance_tournament_if_ready(str(fixture.get("tournament", "")))

    @staticmethod
    def result_from_fixture(fixture: dict) -> dict:
        return {
            "fixture_id": fixture.get("id", ""),
            "year": fixture.get("year", 0),
            "league": fixture.get("league", ""),
            "tournament": fixture.get("tournament", ""),
            "round": fixture.get("round", 0),
            "day": fixture.get("day", 0),
            "home_id": fixture.get("home_id", ""),
            "away_id": fixture.get("away_id", ""),
            "home_name": fixture.get("home_name", ""),
            "away_name": fixture.get("away_name", ""),
            "home_score": fixture.get("home_score", 0),
            "away_score": fixture.get("away_score", 0),
            "watched": fixture.get("watched", False),
            "fixture_type": fixture.get("fixture_type", "REGULAR"),
            "competition_label": fixture.get("competition_label", ""),
            "home_penalties": fixture.get("home_penalties"),
            "away_penalties": fixture.get("away_penalties"),
        }

    def ensure_promotion_playoffs(self) -> list[dict]:
        created: list[dict] = []
        playoff_day = self.promotion_playoff_day(self.year)
        for lower_league in self.league_names:
            upper_league = self.upper_league(lower_league)
            if not upper_league:
                continue
            prefix = f"year{self.year}:PLAYOFF:{upper_league}:{lower_league}:"
            if any(str(fixture.get("id", "")).startswith(prefix) for fixture in self.fixtures):
                continue
            regular = [
                fixture for fixture in self.fixtures
                if fixture.get("fixture_type", "REGULAR") == "REGULAR"
                and fixture.get("league") in (upper_league, lower_league)
            ]
            if not regular or any(not fixture.get("played") for fixture in regular):
                continue
            upper_table = self._calculate_standings(upper_league)
            lower_table = self._calculate_standings(lower_league)
            if len(upper_table) < 2 or len(lower_table) < 2:
                continue
            self.season_standings_snapshot.setdefault(upper_league, deepcopy(upper_table))
            self.season_standings_snapshot.setdefault(lower_league, deepcopy(lower_table))
            pairings = (
                (upper_table[-1], lower_table[0], 1),
                (upper_table[-2], lower_table[1], 2),
            )
            for upper_row, lower_row, match_number in pairings:
                fixture = {
                    "id": prefix + str(match_number),
                    "year": self.year,
                    "league": upper_league,
                    "upper_league": upper_league,
                    "lower_league": lower_league,
                    "round": 999,
                    "day": playoff_day,
                    "home_id": upper_row["team_id"],
                    "away_id": lower_row["team_id"],
                    "home_name": upper_row["name"],
                    "away_name": lower_row["name"],
                    "fixture_type": "PLAYOFF",
                    "competition_label": f"{upper_league}⇔{lower_league} 入れ替え戦{match_number}",
                    "played": False,
                    "home_score": None,
                    "away_score": None,
                    "watched": False,
                }
                self.fixtures.append(fixture)
                created.append(fixture)
        if created:
            self.save()
        return created

    def _resolve_promotion_playoff(self, fixture: dict) -> None:
        if fixture.get("fixture_type") != "PLAYOFF":
            return
        if any(event.get("fixture_id") == fixture.get("id") for event in self.promotion_events):
            return
        home_score = int(fixture.get("home_score", 0))
        away_score = int(fixture.get("away_score", 0))
        if home_score == away_score:
            digest = hashlib.sha256(str(fixture.get("id", "")).encode("utf-8")).digest()
            lower_wins = bool(digest[0] & 1)
            fixture["home_penalties"] = 4 if not lower_wins else 3
            fixture["away_penalties"] = 4 if lower_wins else 3
        else:
            lower_wins = away_score > home_score
        upper_id = str(fixture.get("home_id", ""))
        lower_id = str(fixture.get("away_id", ""))
        upper_league = str(fixture.get("upper_league", ""))
        lower_league = str(fixture.get("lower_league", ""))
        if lower_wins:
            upper_entries = self.league_participations.setdefault(upper_id, [upper_league])
            lower_entries = self.league_participations.setdefault(lower_id, [lower_league])
            self.league_participations[upper_id] = [lower_league if value == upper_league else value for value in upper_entries]
            self.league_participations[lower_id] = [upper_league if value == lower_league else value for value in lower_entries]
            self.league_memberships[upper_id] = lower_league
            self.league_memberships[lower_id] = upper_league
            if upper_id in self.choices_by_id:
                self.choices_by_id[upper_id]["league"] = lower_league
            if lower_id in self.choices_by_id:
                self.choices_by_id[lower_id]["league"] = upper_league
        self.team_signature = self._current_signature()
        self.promotion_events.append({
            "fixture_id": fixture.get("id"),
            "year": self.year,
            "upper_league": upper_league,
            "lower_league": lower_league,
            "upper_team_id": upper_id,
            "upper_team_name": fixture.get("home_name", ""),
            "lower_team_id": lower_id,
            "lower_team_name": fixture.get("away_name", ""),
            "promoted": bool(lower_wins),
        })

    def _process_day(self) -> dict | None:
        self.ensure_promotion_playoffs()
        due = self.fixtures_on_day(self.day, unplayed_only=True)
        watched = next((fixture for fixture in due if fixture.get("id") == self.watch_fixture_id), None)
        if watched is not None:
            self.last_results = []
            self.save()
            return watched
        self.last_results = []
        self.save()
        return None

    def advance_day(self) -> dict | None:
        if self.day >= YEAR_DAYS:
            self._start_next_year()
        else:
            self.day += 1
        return self._process_day()

    def advance_to_next_matchday(self) -> dict | None:
        next_day = self.next_matchday()
        if next_day is None:
            return self.advance_day()
        self.day = next_day
        return self._process_day()

    def complete_watched_fixture(self, fixture_id: str, home_score: int, away_score: int) -> list[dict]:
        watched = self.fixture(fixture_id)
        if watched is None or watched.get("played"):
            return []
        self.record_result(watched, home_score, away_score, watched=True)
        self._resolve_promotion_playoff(watched)
        results = [self.result_from_fixture(watched)]
        remaining = self.fixtures_on_day(self.day, unplayed_only=True)
        self.last_results = results
        self.watch_fixture_id = ""
        self.ensure_promotion_playoffs()
        self.save()
        return remaining

    def standings(self, league_name: str) -> list[dict]:
        snapshot = self.season_standings_snapshot.get(league_name)
        return deepcopy(snapshot) if snapshot is not None else self._calculate_standings(league_name)

    def _calculate_standings(self, league_name: str) -> list[dict]:
        teams = self.teams_in_league(league_name)
        table = {
            str(team["id"]): {
                "team_id": str(team["id"]), "name": team.get("name", ""), "short": team.get("short", ""),
                "played": 0, "won": 0, "drawn": 0, "lost": 0,
                "gf": 0, "ga": 0, "gd": 0, "points": 0,
            }
            for team in teams
        }
        for fixture in self.fixtures:
            if (
                fixture.get("league") != league_name
                or fixture.get("fixture_type", "REGULAR") != "REGULAR"
                or not fixture.get("played")
            ):
                continue
            home = table.get(str(fixture.get("home_id")))
            away = table.get(str(fixture.get("away_id")))
            if home is None or away is None:
                continue
            home_score = int(fixture.get("home_score", 0))
            away_score = int(fixture.get("away_score", 0))
            home["played"] += 1
            away["played"] += 1
            home["gf"] += home_score
            home["ga"] += away_score
            away["gf"] += away_score
            away["ga"] += home_score
            if home_score > away_score:
                home["won"] += 1
                home["points"] += 3
                away["lost"] += 1
            elif away_score > home_score:
                away["won"] += 1
                away["points"] += 3
                home["lost"] += 1
            else:
                home["drawn"] += 1
                away["drawn"] += 1
                home["points"] += 1
                away["points"] += 1
        for row in table.values():
            row["gd"] = row["gf"] - row["ga"]
        return sorted(
            table.values(),
            key=lambda row: (-row["points"], -row["gd"], -row["gf"], -row["won"], str(row["name"]).casefold()),
        )

    def available_years(self) -> list[int]:
        years = {self.year}
        years.update(int(entry.get("year", 0)) for entry in self.history if int(entry.get("year", 0)) > 0)
        return sorted(years, reverse=True)

    def standings_for_year(self, league_name: str, year: int) -> list[dict]:
        if int(year) == self.year:
            return self.standings(league_name)
        entry = next((item for item in self.history if int(item.get("year", 0)) == int(year)), None)
        if not entry:
            return []
        league = entry.get("leagues", {}).get(league_name, {})
        return deepcopy(league.get("standings", [])) if isinstance(league, dict) else []

    def results_for_year(self, league_name: str, year: int) -> list[dict]:
        if int(year) == self.year:
            return [self.result_from_fixture(item) for item in self.fixtures if item.get("league") == league_name and item.get("played")]
        entry = next((item for item in self.history if int(item.get("year", 0)) == int(year)), None)
        if not entry:
            return []
        league = entry.get("leagues", {}).get(league_name, {})
        return deepcopy(league.get("results", [])) if isinstance(league, dict) else []

    def all_results_for_year(self, year: int) -> list[dict]:
        """Return every played fixture for a season without duplicating playoffs."""
        if int(year) == self.year:
            return [self.result_from_fixture(item) for item in self.fixtures if item.get("played")]
        entry = next((item for item in self.history if int(item.get("year", 0)) == int(year)), None)
        if not entry:
            return []
        stored = entry.get("results")
        if isinstance(stored, list):
            return deepcopy([item for item in stored if isinstance(item, dict)])

        # Save version 2 stored regular results per league and playoffs in a
        # separate list. Reconstruct one list so old saves get the new UI too.
        reconstructed: list[dict] = []
        known: set[str] = set()
        leagues = entry.get("leagues", {})
        if isinstance(leagues, dict):
            for league in leagues.values():
                if not isinstance(league, dict):
                    continue
                for result in league.get("results", []):
                    if not isinstance(result, dict):
                        continue
                    fixture_id = str(result.get("fixture_id", ""))
                    if fixture_id and fixture_id in known:
                        continue
                    reconstructed.append(deepcopy(result))
                    if fixture_id:
                        known.add(fixture_id)
        for result in entry.get("promotion_playoffs", []):
            if not isinstance(result, dict):
                continue
            fixture_id = str(result.get("fixture_id", ""))
            if fixture_id and fixture_id in known:
                continue
            reconstructed.append(deepcopy(result))
            if fixture_id:
                known.add(fixture_id)
        return reconstructed

    def historical_teams(self) -> list[dict]:
        """Return stable team selectors, including teams no longer in the template."""
        cache_key = (
            len(self.history),
            self.year,
            tuple(sorted((str(team_id), str(choice.get("name", ""))) for team_id, choice in self.choices_by_id.items())),
        )
        if self._historical_teams_cache and self._historical_teams_cache[0] == cache_key:
            return deepcopy(self._historical_teams_cache[1])
        teams: dict[str, dict] = {
            str(team_id): {"team_id": str(team_id), "name": str(choice.get("name", team_id))}
            for team_id, choice in self.choices_by_id.items()
        }
        for year in self.available_years():
            for league_name in self.league_names_for_year(year):
                for row in self.standings_for_year(league_name, year):
                    team_id = str(row.get("team_id", ""))
                    if team_id:
                        teams.setdefault(team_id, {"team_id": team_id, "name": str(row.get("name", team_id))})
            for result in self.all_results_for_year(year):
                for side in ("home", "away"):
                    team_id = str(result.get(f"{side}_id", ""))
                    if team_id:
                        teams.setdefault(team_id, {"team_id": team_id, "name": str(result.get(f"{side}_name", team_id))})
        ordered = sorted(teams.values(), key=lambda item: str(item["name"]).casefold())
        self._historical_teams_cache = (cache_key, deepcopy(ordered))
        return ordered

    def _league_names_from_history(self, year: int) -> list[str]:
        entry = next((item for item in self.history if int(item.get("year", 0)) == int(year)), None)
        leagues = entry.get("leagues", {}) if entry else {}
        return [str(name) for name in leagues] if isinstance(leagues, dict) else []

    def league_names_for_year(self, year: int) -> list[str]:
        if int(year) == self.year:
            return list(self.league_names)
        return self._league_names_from_history(year)

    def team_standings_for_year(self, team_id: str, year: int) -> list[dict]:
        standings: list[dict] = []
        for league_name in self.league_names_for_year(year):
            table = self.standings_for_year(league_name, year)
            for rank, row in enumerate(table, start=1):
                if str(row.get("team_id", "")) != str(team_id):
                    continue
                item = deepcopy(row)
                item.update({"year": int(year), "league": league_name, "rank": rank})
                standings.append(item)
        return standings

    def team_standings_history(self, team_id: str) -> list[dict]:
        return [
            row
            for year in sorted(self.available_years())
            for row in self.team_standings_for_year(team_id, year)
        ]

    def team_results_for_year(self, team_id: str, year: int) -> list[dict]:
        team_id = str(team_id)
        choice = self.choices_by_id.get(team_id, {})
        known_names = {str(choice.get("name", ""))} - {""}
        known_names.update(
            str(row.get("name", ""))
            for row in self.team_standings_for_year(team_id, year)
            if row.get("name")
        )
        matched: list[dict] = []
        for result in self.all_results_for_year(year):
            ids = (str(result.get("home_id", "")), str(result.get("away_id", "")))
            names = (str(result.get("home_name", "")), str(result.get("away_name", "")))
            # IDs are authoritative in v3. Name matching keeps v2 saves usable.
            if team_id in ids:
                side = "home" if ids[0] == team_id else "away"
            elif not any(ids) and known_names.intersection(names):
                side = "home" if names[0] in known_names else "away"
            else:
                continue
            item = deepcopy(result)
            item.setdefault("year", int(year))
            item["team_side"] = side
            matched.append(item)
        return sorted(matched, key=lambda item: (int(item.get("day", 0)), int(item.get("round", 0)), str(item.get("fixture_id", ""))))

    def promotion_events_for_year(self, year: int) -> list[dict]:
        if int(year) == self.year:
            return deepcopy(self.promotion_events)
        entry = next((item for item in self.history if int(item.get("year", 0)) == int(year)), None)
        return deepcopy(entry.get("promotion_events", [])) if entry else []

    def _start_next_year(self) -> None:
        champions = {}
        league_history = {}
        for league_name in self.league_names:
            table = self.standings(league_name)
            if table:
                champions[league_name] = table[0]["name"]
            league_history[league_name] = {
                "champion": table[0]["name"] if table else "",
                "standings": deepcopy(table),
                "results": [
                    self.result_from_fixture(fixture)
                    for fixture in self.fixtures
                    if fixture.get("league") == league_name and fixture.get("played")
                ],
            }
        self.history.append({
            "year": self.year,
            "champions": champions,
            "leagues": league_history,
            "results": [
                self.result_from_fixture(fixture)
                for fixture in self.fixtures if fixture.get("played")
            ],
            "promotion_playoffs": [
                self.result_from_fixture(fixture)
                for fixture in self.fixtures if fixture.get("fixture_type") == "PLAYOFF"
            ],
            "promotion_events": deepcopy(self.promotion_events),
        })
        self.year += 1
        self.day = 1
        self.season_standings_snapshot = {}
        self.promotion_events = []
        self.fixtures = self._build_all_schedules()
        self.watch_fixture_id = ""
        self.last_results = []
        self.save()

__all__ = ("LeagueManager", "LeagueSimulationSession")
