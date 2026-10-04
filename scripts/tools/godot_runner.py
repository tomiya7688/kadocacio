"""Developer entry for pinned Godot launch, real-engine checks and smoke tests."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Sequence

from scripts.core.paths import PROJECT_ROOT, USER_LOG_DIR


GODOT_PROJECT = PROJECT_ROOT / "godot"
ERROR_LINE = re.compile(r"(?m)^\s*(?:SCRIPT ERROR|ERROR):")


def resolve_engine(explicit: str | None = None) -> Path:
    """An explicit/environment path fails closed, never silently falls back."""
    requested = explicit or os.environ.get("GODOT_BIN")
    if requested:
        resolved = shutil.which(requested) or requested
        candidate = Path(resolved).expanduser().resolve()
        if not candidate.is_file():
            raise ValueError(f"Godot executable not found: {candidate}")
        return candidate
    for name in ("godot_console", "godot", "godot4"):
        resolved = shutil.which(name)
        if resolved:
            return Path(resolved).resolve()
    raise ValueError("Set GODOT_BIN or pass --engine with a Godot console executable.")


def validate_engine(engine: Path, project: Path) -> str:
    expected = (project / "engine_version.txt").read_text(encoding="utf-8").strip()
    result = subprocess.run(
        [str(engine), "--version"], capture_output=True, text=True,
        encoding="utf-8", errors="replace", timeout=15, check=False,
    )
    version = result.stdout.strip()
    if result.returncode or not version.startswith(expected + ".stable."):
        raise ValueError(f"Expected Godot {expected} stable; got {version!r}")
    return version


def engine_command(engine: Path, project: Path, *args: str) -> list[str]:
    return [str(engine), "--path", str(project), *args]


def run_checked(command: Sequence[str], timeout: float, markers: Sequence[str] = ()) -> int:
    """Godot can log import/script errors and still exit 0; fail on either."""
    result = subprocess.run(
        list(command), capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout, check=False,
    )
    print(result.stdout, end="")
    print(result.stderr, end="")
    output = result.stdout + result.stderr
    if result.returncode or ERROR_LINE.search(output):
        return result.returncode or 1
    if any(marker not in output for marker in markers):
        print("FAIL: missing Godot completion marker")
        return 1
    return 0


def check_scripts(engine: Path, project: Path, timeout: float) -> int:
    status = run_checked(engine_command(engine, project, "--headless", "--import"), timeout)
    if status:
        return status
    for script in sorted(project.rglob("*.gd")):
        if ".godot" in script.relative_to(project).parts:
            continue
        status = run_checked(engine_command(
            engine, project, "--headless", "--check-only", "--script", str(script),
        ), timeout)
        if status:
            return status
    return 0


def check_error_detection(engine: Path, project: Path, timeout: float) -> int:
    """Exercise known-bad fixtures in ignored temporary files, not game sources."""
    output_root = USER_LOG_DIR / "godot"
    output_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="parse-", dir=output_root) as temporary:
        for kind in ("syntax", "type"):
            target = Path(temporary) / f"invalid_{kind}.gd"
            shutil.copyfile(project / "tests" / "fixtures" / f"invalid_{kind}.gd.txt", target)
            result = subprocess.run(engine_command(
                engine, project, "--headless", "--check-only", "--script", str(target),
            ), capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=timeout, check=False)
            if not result.returncode or "Parse Error" not in result.stdout + result.stderr:
                print(f"FAIL: Godot did not reject the {kind} fixture")
                return 1
            print(f"PASS: Godot rejected the {kind} fixture (exit {result.returncode})")
    return 0


def run_smoke(engine: Path, project: Path, timeout: float, headless: bool) -> int:
    options = ["--headless"] if headless else ["--windowed"]
    return run_checked(engine_command(
        engine, project, *options, "--audio-driver", "Dummy", "--quit-after", "120", "--", "--smoke-exit",
    ), timeout, ("KADOCALCIO_BOOTSTRAP_READY", "KADOCALCIO_BOOTSTRAP_STOP"))


def run_team_checks(engine: Path, project: Path, timeout: float) -> int:
    from scripts.tools.godot_team_oracle import assert_sources_unchanged, write_oracle

    oracle, fingerprints = write_oracle()
    try:
        return run_checked(engine_command(
            engine, project, "--headless", "--script", "res://tests/team_data_tests.gd",
            "--", "--oracle", str(oracle),
        ), timeout, ("KADOCALCIO_TEAM_TESTS:",))
    finally:
        assert_sources_unchanged(fingerprints)


def run_ui_checks(engine: Path, project: Path, timeout: float, headless: bool) -> int:
    from scripts.tools.godot_ui_contract import check_contract

    if not check_contract():
        print("FAIL: stale Godot UI contract; regenerate explicitly with --write")
        return 1
    options = ["--headless"] if headless else ["--windowed", "--audio-driver", "Dummy"]
    arguments = [] if headless else ["--", "--ui-window-test"]
    return run_checked(engine_command(
        engine, project, *options, "--script", "res://tests/run_tests.gd", *arguments,
    ), timeout, ("KADOCALCIO_TESTS:",))


def run_match_checks(engine: Path, project: Path, timeout: float) -> int:
    from scripts.tools.godot_match_fixture import write_fixture

    fixture, fingerprints = write_fixture()
    return run_native_trace_check(engine, project, timeout, fixture, fingerprints,
                                  "match_contract_tests.gd", "KADOCALCIO_MATCH_CONTRACT_TESTS:")


def run_kernel_checks(engine: Path, project: Path, timeout: float) -> int:
    from scripts.tools.godot_kernel_fixture import write_kernel_fixture

    fixture, fingerprints = write_kernel_fixture()
    return run_native_trace_check(engine, project, timeout, fixture, fingerprints,
                                  "match_kernel_tests.gd", "KADOCALCIO_MATCH_KERNEL_TESTS:")


def run_native_trace_check(engine: Path, project: Path, timeout: float, fixture: Path,
                           fingerprints: dict[str, str], script: str, marker: str) -> int:
    from scripts.core.match_trace_comparison import compare_traces
    from scripts.tools.godot_team_oracle import assert_sources_unchanged

    try:
        with tempfile.TemporaryDirectory(prefix="native-", dir=fixture.parent) as temporary:
            native = Path(temporary) / "trace.json"
            status = run_checked(engine_command(
                engine, project, "--headless", "--script", "res://tests/" + script,
                "--", "--fixture", str(fixture), "--output", str(native),
            ), timeout, (marker,))
            if status:
                return status
            report = compare_traces(json.loads(fixture.read_text(encoding="utf-8"))["reference"], json.loads(native.read_text(encoding="utf-8")))
            (fixture.parent / "diff.json").write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
            print("MATCH OBSERVATIONS: PASS" if report["same_observations"] else "MATCH OBSERVATIONS: DIFFER")
            return 0 if report["same_observations"] else 1
    finally:
        assert_sources_unchanged(fingerprints)


def run_ball_checks(engine: Path, project: Path, timeout: float) -> int:
    from scripts.tools.godot_ball_fixture import write_ball_fixture

    fixture, fingerprints = write_ball_fixture()
    return run_native_trace_check(engine, project, timeout, fixture, fingerprints,
                                  "ball_physics_tests.gd", "KADOCALCIO_BALL_TESTS:")


def execute(mode: str, engine: Path, project: Path, timeout: float, headless: bool) -> int:
    if mode == "run":
        options = ["--headless"] if headless else []
        return subprocess.call(engine_command(engine, project, *options))
    status = check_scripts(engine, project, timeout)
    if status or mode == "check":
        return status
    if mode == "ui-test":
        return run_ui_checks(engine, project, timeout, headless)
    if mode == "smoke":
        return run_smoke(engine, project, timeout, headless)
    status = run_ui_checks(engine, project, timeout, True)
    if status:
        return status
    status = run_team_checks(engine, project, timeout)
    if status:
        return status
    status = run_match_checks(engine, project, timeout)
    if status:
        return status
    status = run_kernel_checks(engine, project, timeout)
    if status:
        return status
    status = run_ball_checks(engine, project, timeout)
    if status:
        return status
    status = check_error_detection(engine, project, timeout)
    return status or run_smoke(engine, project, timeout, True)


def positive_timeout(value: str) -> float:
    timeout = float(value)
    if not 0 < timeout <= 300:
        raise argparse.ArgumentTypeError("timeout must be in (0, 300] seconds")
    return timeout


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", nargs="?", default="run", choices=("run", "check", "test", "smoke", "ui-test"))
    parser.add_argument("--engine", help="Pinned Godot executable (or set GODOT_BIN)")
    parser.add_argument("--headless", action="store_true", help="Run/smoke/ui-test without a window; test is always headless")
    parser.add_argument("--timeout", type=positive_timeout, default=60.0, help="Per-check timeout, not normal gameplay")
    args = parser.parse_args(argv)
    try:
        engine = resolve_engine(args.engine)
        print(f"Godot: {validate_engine(engine, GODOT_PROJECT)} ({engine})", flush=True)
        return execute(args.mode, engine, GODOT_PROJECT, args.timeout, args.headless)
    except (OSError, ValueError, subprocess.TimeoutExpired) as error:
        print(f"GODOT FAILED: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
