"""Generate and validate compact Codex context documents for major source folders."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Sequence


ROOT = Path(__file__).resolve().parents[2]
TICK = chr(96)

CONTEXT_SPECS = {
    "scripts/app": {
        "responsibility": "Pygame application shell: input, screen transitions, rendering orchestration, and player-facing presentation.",
        "entrypoints": ("game_app.py", "rendering.py"),
        "classes": ("Game", "RendererMixin", "GpuPresenter"),
        "data": ("Reads runtime configuration and league/team state through lower-level modules; do not invent local data roots.",),
        "allowed": ("scripts.core", "scripts.match", "scripts.league", "scripts.team"),
        "forbidden": ("scripts.tools.static_analysis", "direct writes to repository-root runtime outputs"),
        "read_first": ("game_app.py for flow/input", "rendering.py for visual changes", "matching tests from AGENTS.md"),
        "ignore": ("unrelated screens/render paths", "developer evaluation tools"),
        "related": ("AGENTS.md", "SPEC.md", "doc/クラス一覧.md"),
    },
    "scripts/core": {
        "responsibility": "Portable shared primitives, paths, settings, simulation drivers, telemetry, and scale/limit models.",
        "entrypoints": ("paths.py", "simulation_runtime.py", "settings.py"),
        "classes": ("PerformanceSettings", "RealtimeSimulationDriver", "SimulationLimits", "SimulationResult"),
        "data": ("Owns canonical runtime path resolution and shared settings contracts.",),
        "allowed": ("Python standard library", "narrow portability adapters such as simulation_geometry.py"),
        "forbidden": ("scripts.app", "scripts.league", "scripts.team", "new direct pygame dependencies outside the portability boundary"),
        "read_first": ("paths.py for filesystem work", "simulation_runtime.py for headless/fixed-step work", "stat_scale.py for player-stat scale"),
        "ignore": ("UI/rendering code", "game-specific editor behavior"),
        "related": ("AGENTS.md", "doc/UPD_Commander適用方針.md", "doc/クラス一覧.md"),
    },
    "scripts/match": {
        "responsibility": "Soccer match domain: fixed-step rules, player/team/ball state, AI decisions, physics, commands, and match results.",
        "entrypoints": ("match_engine.py", "player.py", "team.py"),
        "classes": ("Match", "Player", "Team", "Ball", "PlayerCommand"),
        "data": ("Consumes normalized team snapshots; match hot paths should not perform filesystem I/O.",),
        "allowed": ("scripts.core", "other scripts.match modules"),
        "forbidden": ("scripts.app", "scripts.tools", "filesystem discovery/persistence in match hot paths"),
        "read_first": ("the smallest *_system.py matching the behavior", "match_engine.py only for orchestration/cross-system behavior", "matching match tests"),
        "ignore": ("rendering", "league persistence", "developer tooling"),
        "related": ("AGENTS.md", "SPEC.md", "doc/クラス一覧.md"),
    },
    "scripts/league": {
        "responsibility": "League definitions, fixtures, standings, saves/migrations, background match sessions, and league-facing views.",
        "entrypoints": ("league_manager.py", "league_simulation_session.py", "save_migrations.py"),
        "classes": ("LeagueManager", "LeagueSimulationSession", "LeagueAutoProgressConfig"),
        "data": ("Uses user_data/config and user_data/saves through scripts.core.paths; save compatibility is versioned.",),
        "allowed": ("scripts.core", "scripts.match", "scripts.team"),
        "forbidden": ("repository-root live saves", "silent overwrite after load/migration failure"),
        "read_first": ("league_manager.py for state/persistence", "league_simulation_session.py for background matches", "specific *_view.py for UI-only work"),
        "ignore": ("match rendering internals", "unrelated team editor code"),
        "related": ("AGENTS.md", "doc/実行時データ配置.md", "doc/クラス一覧.md"),
    },
    "scripts/team": {
        "responsibility": "Team data identity/loading, editor and uniform tooling, templates/ratings, and team-tuner workflows.",
        "entrypoints": ("team_data.py", "team_editor_data.py", "team_identity.py"),
        "classes": ("TeamEditor", "UniformEditor", "TeamTunerSession"),
        "data": ("Standard teams live under bundled teams; packaged user edits live under user_data/teams with stable team IDs.",),
        "allowed": ("scripts.core", "scripts.match for simulation/tuning"),
        "forbidden": ("path-derived permanent team identity", "implicit repository-root user writes in packaged mode"),
        "read_first": ("team_data.py for loading", "team_identity.py for IDs", "team_editor_data.py for JSON editing/validation"),
        "ignore": ("league scheduling", "rendering outside editor/uniform scope"),
        "related": ("AGENTS.md", "doc/チーム生成基準値テンプレート.md", "doc/クラス一覧.md"),
    },
    "scripts/tools": {
        "responsibility": "Developer-only CLI workflows for evaluation, migration, generation, packaging validation, context reduction, and Git automation.",
        "entrypoints": ("context_pack.py", "git_workflow.py", "distribution_layout.py"),
        "classes": ("NinetyMatchStressGame", "LeagueEvaluationRunner"),
        "data": ("Generated evaluation/performance outputs belong under ignored user_data/logs; migration tools must support safe/dry-run behavior where applicable.",),
        "allowed": ("runtime modules when needed for evaluation/migration", "scripts.tools.static_analysis"),
        "forbidden": ("being imported by player-facing runtime hot paths", "silently mutating user data without an explicit tool action"),
        "read_first": ("the single CLI module matching the task", "tests for that tool", "AGENTS.md tool map"),
        "ignore": ("unrelated migration/evaluation tools", "large generated logs"),
        "related": ("AI_CONTEXT.md", "AGENTS.md", "doc/実行時データ配置.md"),
    },
    "scripts/tools/static_analysis": {
        "responsibility": "Pre-commit/CI repository inspection: architecture rules, UPD checks, reports, and the shared validation runner.",
        "entrypoints": ("run_all.py", "architecture_boundary.py", "upd_checker.py"),
        "classes": ("Rule", "Violation", "Profile"),
        "data": ("Writes generated reports under ignored static_analysis/reports; checks source without changing runtime behavior.",),
        "allowed": ("Python standard library", "developer-only checker dependencies"),
        "forbidden": ("imports from player-facing runtime code into this package", "runtime side effects"),
        "read_first": ("run_all.py for check orchestration", "the checker module being changed", "tests/test_static_analysis_runner.py"),
        "ignore": ("gameplay implementation unless a checker explicitly inspects it",),
        "related": ("AGENTS.md", "AI_CONTEXT.md", "doc/UPD_Commander適用方針.md"),
    },
}


def discover_modules(relative: str, *, root: Path = ROOT) -> list[str]:
    folder = root / relative
    if not folder.is_dir():
        return []
    return sorted(
        path.name
        for path in folder.glob("*.py")
        if path.name != "__init__.py"
    )


def discover_packages(relative: str, *, root: Path = ROOT) -> list[str]:
    folder = root / relative
    if not folder.is_dir():
        return []
    return sorted(
        path.name + "/"
        for path in folder.iterdir()
        if path.is_dir() and (path / "__init__.py").is_file()
    )


def bullet_lines(items: Sequence[str]) -> list[str]:
    return [f"- {item}" for item in items] if items else ["- (none)"]


def quoted(items: Sequence[str]) -> list[str]:
    return [f"{TICK}{item}{TICK}" for item in items]


def render_context(relative: str, spec: dict, *, root: Path = ROOT) -> str:
    modules = quoted(discover_modules(relative, root=root))
    packages = quoted(discover_packages(relative, root=root))
    lines = [
        f"# {relative} Context",
        "",
        f"> AUTO-GENERATED by {TICK}python -m scripts.tools.context_docs{TICK}. Do not hand-edit.",
        "",
        "## Responsibility",
        str(spec["responsibility"]),
        "",
        "## Main entrypoints",
        *bullet_lines(quoted(spec["entrypoints"])),
        "",
        "## Notable classes",
        *bullet_lines(quoted(spec["classes"])),
        "",
        "## Data",
        *bullet_lines(spec["data"]),
        "",
        "## Dependency rules",
        "Allowed:",
        *bullet_lines(spec["allowed"]),
        "",
        "Forbidden / avoid:",
        *bullet_lines(spec["forbidden"]),
        "",
        "## Read first",
        *bullet_lines(spec["read_first"]),
        "",
        "## Ignore normally",
        *bullet_lines(spec["ignore"]),
        "",
        "## Current modules",
        *bullet_lines(modules),
        "",
        "## Child packages",
        *bullet_lines(packages),
        "",
        "## Related",
        *bullet_lines(quoted(spec["related"])),
        "",
    ]
    return "\n".join(lines)


def generate_context_docs(*, root: Path = ROOT, check: bool = False) -> int:
    stale: list[str] = []
    for relative, spec in CONTEXT_SPECS.items():
        target = root / relative / "CONTEXT.md"
        expected = render_context(relative, spec, root=root)
        if check:
            if not target.is_file() or target.read_text(encoding="utf-8") != expected:
                stale.append(relative)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(expected, encoding="utf-8")

    if check:
        if stale:
            print("CONTEXT DOCS: STALE")
            for relative in stale:
                print(f"- {relative}/CONTEXT.md")
            print("Run: python -m scripts.tools.context_docs")
            return 1
        print("CONTEXT DOCS: PASS")
        return 0

    print(f"CONTEXT DOCS: GENERATED ({len(CONTEXT_SPECS)})")
    return 0


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="fail when generated CONTEXT.md files are missing or stale",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    return generate_context_docs(check=args.check)


if __name__ == "__main__":
    raise SystemExit(main())
