"""Public-only short reference trace; input/trace comparison developer CLI."""

import argparse
import json
from pathlib import Path

from scripts.core.match_trace_comparison import compare_traces
from scripts.core.paths import PROJECT_ROOT, USER_LOG_DIR
from scripts.tools.godot_match_contract import check_contract
from scripts.tools.godot_team_oracle import assert_sources_unchanged, file_fingerprints, public_team_paths, reference_case
from scripts.tools.match_contract_input import create_contract_input
from scripts.tools.match_contract_trace import capture_trace
from scripts.tools.match_contract_cases import comparison_cases, input_cases, trace_cases

DEFAULT_OUTPUT = USER_LOG_DIR / "godot/match_contract"


# {
#   責務: [write_fixture: 公開チームだけから短い実試合の境界照合データを保存する]
#   処理: [1: 更新上限と定義を検査; 2: 公開2チームで観測・不正値・差分例を生成; 3: 全終了経路で原本ハッシュを確認]
#   引数: [output: ログ出力先; steps: 捕捉する固定更新数1..500]
#   戻り値: [tuple: 保存ファイルと原本ハッシュ。条件不成立はValueError]
# }
def write_fixture(output: Path = DEFAULT_OUTPUT, steps: int = 96) -> tuple[Path, dict[str, str]]:
    if type(steps) is not int or not 1 <= steps <= 500:
        raise ValueError("fixture steps must be in 1..500")
    if not check_contract():
        raise ValueError("match contract is stale; regenerate explicitly with --write")
    paths = public_team_paths()[:2]
    if len(paths) != 2:
        raise ValueError("two tracked public teams are required")
    before = file_fingerprints(paths)
    try:
        choices = [reference_case(json.loads(path.read_text(encoding="utf-8-sig")), path.relative_to(PROJECT_ROOT / "teams").as_posix()) for path in paths]
        if not all(case["valid"] for case in choices):
            raise ValueError("public fixture team is invalid")
        operations = [{"kind": "START"}, {"kind": "SET_SPEED", "value": 10}, {"kind": "PAUSE"}, {"kind": "STEP", "dt": 0.05}, {"kind": "RESUME"}] + [{"kind": "STEP", "dt": 0.05} for _ in range(steps)]
        payload = create_contract_input(choices[0]["choice"], choices[1]["choice"], operations,
                                        seed=2**63 + 12345, max_steps=steps + 1, venue_mode="NEUTRAL", ai_rethink_multiplier=1.0)
        reference = capture_trace(payload)
        fixture = {"input": payload, "reference": reference,
                   "input_cases": input_cases(payload), "trace_cases": trace_cases(reference),
                   "comparison_cases": comparison_cases(reference)}
        output.mkdir(parents=True, exist_ok=True)
        path = output / "fixture.json"
        path.write_text(json.dumps(fixture, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        return path, before
    finally:
        assert_sources_unchanged(before)


# {
#   責務: [main: 参照fixture生成または外部観測との比較を実行する]
#   処理: [1: CLI設定を解析; 2: 生成または差分を保存; 3: 不正入力と入出力エラーを診断へ変換]
#   引数: [argv: CLI引数。Noneなら実行プロセスの引数]
#   戻り値: [int: 一致・生成成功0、不一致1、入力・保存失敗2]
# }
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--steps", type=int, default=96)
    parser.add_argument("--actual", type=Path, help="Compare a native observation trace JSON")
    parser.add_argument("--fixture", type=Path, help="Previously captured fixture; required with --actual")
    args = parser.parse_args(argv)
    try:
        if args.actual:
            if args.fixture is None:
                raise ValueError("--actual requires --fixture")
            report = compare_traces(json.loads(args.fixture.read_text(encoding="utf-8"))["reference"], json.loads(args.actual.read_text(encoding="utf-8")))
            args.output.mkdir(parents=True, exist_ok=True)
            (args.output / "diff.json").write_text(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2), encoding="utf-8")
            print("MATCH OBSERVATIONS: PASS" if report["same_observations"] else "MATCH OBSERVATIONS: DIFFER")
            return 0 if report["same_observations"] else 1
        if args.fixture:
            raise ValueError("--fixture requires --actual")
        path, _ = write_fixture(args.output, args.steps)
        print(f"MATCH CONTRACT FIXTURE: {path}")
        return 0
    except (ValueError, KeyError, OSError) as error:
        print(f"MATCH CONTRACT FAILED: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
