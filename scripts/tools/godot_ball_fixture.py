"""Actual Python ball-rule oracle with explicitly intercepted contact/restart seams."""

import argparse
from copy import deepcopy
import json
from pathlib import Path

from scripts.core.paths import USER_LOG_DIR
from scripts.core.settings import FIELD, GOAL_HALF_HEIGHT, GOAL_HEIGHT
from scripts.core.simulation_geometry import Vec2
from scripts.core.match_protocol import TRACE_FORMAT, VERSION
from scripts.match.match_engine import Match
from scripts.match.player_command import PlayerCommand
from scripts.tools.godot_match_fixture import write_fixture
from scripts.tools.godot_team_oracle import assert_sources_unchanged
from scripts.tools.match_contract_input import restore_contract_input

DEFAULT_OUTPUT = USER_LOG_DIR / "godot/ball_physics"
SCALARS = ("pickup_lock", "curve_acceleration", "knuckle_amplitude", "knuckle_phase", "flight_type",
           "flight_serial", "shot_serial", "shot_deception", "shot_outcome", "shot_miss_announced",
           "pass_outcome", "pass_brake", "eye_contact_bonus", "catch_forbidden", "last_keeper_response", "recovery_timer")
VECTORS = ("control_offset", "curve_vector", "intended_destination")


# {
#   責務: [identity: 検証選手の参照を試合内IDへ変換します]
#   処理: [1: 未指定を保持します; 2: 所属側と名簿内番号を結合します]
#   引数: [match: HOMEとAWAYを持つ検証試合; player: その試合の選手またはNone]
#   戻り値: [strまたはNone: 試合内の安定した参照名]
# }
def identity(match, player):
    if player is None:
        return None
    team = match.home if player.team is match.home else match.away
    return ("HOME" if team is match.home else "AWAY") + ":" + str(team.players.index(player))


# {
#   責務: [ball_values: Pythonボールの状態を参照比較用のJSON値へ写します]
#   処理: [1: 座標と速度・飛行付随値を読みます; 2: ベクトルを配列へ写します; 3: 選手と回収チームを識別名へ変換します]
#   引数: [match: 読取対象の検証試合]
#   戻り値: [dict: 状態参照を共有しない現在値。試合や乱数は更新しません]
# }
def ball_values(match: Match) -> dict:
    # 比較先へ実Playerや可変ベクトルを渡さず、同じキーの値へ揃えます。
    ball = match.ball
    return {"position": [ball.pos.x, ball.pos.y, ball.z], "velocity": [ball.vel.x, ball.vel.y, ball.vertical_speed],
            **{key: getattr(ball, key) for key in SCALARS}, **{key: list(getattr(ball, key)) for key in VECTORS},
            **{key: identity(match, getattr(ball, key)) for key in ("owner", "last_touch", "intended")},
            "recovery_team": None if ball.recovery_team is None else "HOME" if ball.recovery_team is match.home else "AWAY"}


# {
#   責務: [case_definitions: ボール部分演算の代表値と境界条件を列挙します]
#   処理: [1: 低速・高速・浮き球・所有変更を定義します; 2: 両ゴールの境界と最終接触の組合せを追加します; 3: 手の可否・高さ・回収順の接触条件を追加します]
#   引数: []
#   戻り値: [list: 実行前のケース入力列。乱数や実チームデータは使用しません]
# }
def case_definitions() -> list[dict]:
    # 寸法はPythonの正本を使い、境界ぴったりと直外を別ケースにします。
    x, y = FIELD.center
    right, left, top, bottom = FIELD.right, FIELD.left, FIELD.top, FIELD.bottom
    cases = [
        {"name": "slow_roll", "steps": 260, "ball": {"position": [x, y, 0], "velocity": [32, 11, 0]}},
        {"name": "fast_roll", "steps": 80, "ball": {"velocity": [370, -26, 0]}},
        {"name": "settling", "steps": 4, "ball": {"velocity": [6, 0, 0], "pass_brake": 2}},
        {"name": "negative_brake", "steps": 4, "ball": {"velocity": [120, 0, 0], "pass_brake": -1}},
        {"name": "lofted", "steps": 85, "ball": {"velocity": [180, 45, 235], "pass_brake": 0.65}},
        {"name": "soft_bounce", "steps": 4, "ball": {"position": [x, y, 0.1], "velocity": [95, 0, -20]}},
        {"name": "hard_bounce", "steps": 8, "ball": {"position": [x, y, 1], "velocity": [90, 0, -160]}},
        {"name": "curve", "steps": 80, "ball": {"velocity": [200, 30, 170], "curve_acceleration": 55, "curve_vector": [25, -44]}},
        {"name": "knuckle", "steps": 85, "ball": {"velocity": [190, 20, 150], "knuckle_amplitude": 36, "knuckle_phase": 0.4}},
        {"name": "knuckle_still", "steps": 3, "ball": {"knuckle_amplitude": 0.2}},
        {"name": "held", "steps": 3, "ball": {"owner": "HOME:1", "last_touch": "HOME:1", "intended": "AWAY:1", "velocity": [210, 20, 155], "pickup_lock": 0.3}},
        {"name": "spill_tackle", "steps": 4, "operation": "spill", "recovery": "AWAY", "ball": {"owner": "HOME:1", "intended": "HOME:2", "pass_outcome": "OVERHIT", "pass_brake": 0.4}},
        {"name": "spill_plain", "steps": 4, "operation": "spill", "ball": {"owner": "HOME:1", "catch_forbidden": True}},
        {"name": "spill_non_owner", "steps": 2, "operation": "spill", "ball": {"owner": "AWAY:1"}},
        {"name": "claim", "steps": 2, "operation": "claim", "ball": {"intended": "AWAY:1", "pickup_lock": 0.3, "curve_acceleration": 20, "pass_brake": 0.6}},
        {"name": "claim_default", "steps": 2, "operation": "claim_default", "ball": {}},
        {"name": "metadata_expiry", "steps": 4, "ball": {"last_touch": "AWAY:1", "intended": "HOME:1", "recovery_team": "HOME", "recovery_timer": 0.07, "pickup_lock": 0.07, "flight_serial": 7, "shot_serial": 11, "eye_contact_bonus": 0.2}},
    ]
    for side, goal_x, direction in (("right", right, 1), ("left", left, -1)):
        # 左右で同じ検査を行い、得点とポスト・場外の優先順も確認できます。
        for label, height, lateral, outcome in (("goal", 20, 0, ""), ("bar_exact", GOAL_HEIGHT, 0, ""),
                                                  ("bar_over", GOAL_HEIGHT + 0.01, 0, "OVER"),
                                                  ("side_exact", 0, GOAL_HALF_HEIGHT, ""),
                                                  ("wide", 0, GOAL_HALF_HEIGHT + 0.01, "WIDE"),
                                                  ("post", 18, GOAL_HALF_HEIGHT, "POST"),
                                                  ("post_not_shot", 18, GOAL_HALF_HEIGHT, "POST")):
            cases.append({"name": side + "_" + label, "steps": 2, "ball": {
                "position": [goal_x - direction, y + lateral, height], "velocity": [direction * 80, 0, 0],
                "shot_outcome": outcome, "flight_type": "パス" if label == "post_not_shot" else "シュート",
                "catch_forbidden": True}})
        for last in (None, "HOME:1", "AWAY:1"):
            cases.append({"name": side + "_endline_" + str(last), "steps": 1, "ball": {
                "position": [goal_x - direction, y + 110, 0], "velocity": [direction * 80, 0, 0], "last_touch": last}})
    for touch_y in (top - 1, bottom + 1):
        # 最終接触者なしの既定側も、両タッチラインで比較します。
        for last in (None, "HOME:1", "AWAY:1"):
            cases.append({"name": "throw_" + str(touch_y) + "_" + str(last), "steps": 1,
                          "ball": {"position": [x, touch_y, 0], "last_touch": last}})
    cases += [
        # 接触の技能判定とは分け、幾何条件と手の規則だけを入力にします。
        {"name": "line_exact", "steps": 1, "ball": {"position": [right, y, 0]}},
        {"name": "corner_priority", "steps": 1, "ball": {"position": [right + 1, top - 1, 0]}},
        {"name": "post_above", "steps": 1, "ball": {"position": [right + 1, top - 1, 110], "flight_type": "シュート", "shot_outcome": "POST"}},
        {"name": "keeper_hands", "steps": 1, "ball": {"position": [left + 70, y, 30]}, "players": [{"id": "HOME_GK", "position": [left + 70, y, 0]}]},
        {"name": "keeper_opponent_touch", "steps": 1, "ball": {"position": [left + 70, y, 0], "last_touch": "AWAY:1"}, "players": [{"id": "HOME_GK", "position": [left + 70, y, 0]}]},
        {"name": "keeper_self_touch", "steps": 1, "ball": {"position": [left + 70, y, 0], "last_touch": "HOME_GK"}, "players": [{"id": "HOME_GK", "position": [left + 70, y, 0]}]},
        {"name": "keeper_backpass_feet", "steps": 1, "ball": {"position": [left + 70, y, 0], "last_touch": "HOME:1", "intended": "HOME_GK"}, "players": [{"id": "HOME_GK", "position": [left + 70, y, 0]}]},
        {"name": "keeper_backpass_high", "steps": 1, "ball": {"position": [left + 70, y, 30], "last_touch": "HOME:1", "flight_type": "パス"}, "players": [{"id": "HOME_GK", "position": [left + 70, y, 0]}]},
        {"name": "keeper_outside_feet", "steps": 1, "ball": {"position": [left + 500, y, 0]}, "players": [{"id": "HOME_GK", "position": [left + 500, y, 0]}]},
        {"name": "keeper_box_edge", "steps": 1, "ball": {"position": [left + 400, y + 380, 0]}, "players": [{"id": "HOME_GK", "position": [left + 400, y + 380, 0]}]},
        {"name": "keeper_air_reach", "steps": 1, "ball": {"position": [left + 70, y, 71]}, "players": [{"id": "HOME_GK", "position": [left + 70, y, 20]}]},
        {"name": "keeper_air_too_high", "steps": 1, "ball": {"position": [left + 70, y, 72]}, "players": [{"id": "HOME_GK", "position": [left + 70, y, 20]}]},
        {"name": "keeper_fast_shot_skip", "steps": 1, "ball": {"position": [left + 70, y, 0], "velocity": [-220, 0, 0], "flight_type": "シュート"}, "players": [{"id": "HOME_GK", "position": [left + 70, y, 0]}]},
        {"name": "contact_order", "steps": 1, "ball": {}, "players": [{"id": "HOME:1", "position": [x, y, 0]}, {"id": "AWAY:1", "position": [x, y, 0]}]},
        {"name": "contact_recovery", "steps": 1, "ball": {"recovery_team": "AWAY", "recovery_timer": 1.25}, "players": [{"id": "HOME:1", "position": [x, y, 0]}, {"id": "AWAY:1", "position": [x + 12, y, 0]}]},
        {"name": "contact_lock", "steps": 1, "ball": {"last_touch": "HOME:1", "pickup_lock": 0.2}, "players": [{"id": "HOME:1", "position": [x, y, 0]}, {"id": "AWAY:1", "position": [x + 4, y, 0]}]},
        {"name": "contact_sent_off", "steps": 1, "ball": {}, "players": [{"id": "HOME:1", "position": [x, y, 0], "sent_off": True}]},
        {"name": "contact_too_high", "steps": 1, "ball": {"position": [x, y, 30]}, "players": [{"id": "HOME:1", "position": [x, y, 0]}]},
        {"name": "contact_air_low", "steps": 1, "ball": {"position": [x, y, 35]}, "players": [{"id": "HOME:1", "position": [x + 10, y, 2], "jump_accuracy": 0.0}]},
        {"name": "contact_air_high", "steps": 1, "ball": {"position": [x, y, 35]}, "players": [{"id": "HOME:1", "position": [x + 10, y, 2], "jump_accuracy": 1.0}]},
        {"name": "contact_intended", "steps": 1, "ball": {"intended": "HOME:1", "velocity": [30, 0, 0]}, "players": [{"id": "HOME:1", "position": [x + 2, y, 0]}]},
    ]
    return cases


# {
#   責務: [configure: ボール単体ケースをPythonの検証試合へ設定します]
#   処理: [1: 全選手を接触しない位置へ移しスキルを無効化します; 2: ボールの指定値と参照を復元します; 3: 明示された接触検査選手の位置と能力を設定します]
#   引数: [match: 作成直後の検証試合; case: ボールと必要な選手の入力]
#   戻り値: [dict: HOMEとAWAYの名簿順IDから実選手への対応。入力元のチームJSONは変更しません]
# }
def configure(match: Match, case: dict) -> dict:
    # 対象外の選手が偶然接触しないよう、幾何検査の初期条件を隔離します。
    players = {side + ":" + str(index): player for side, team in (("HOME", match.home), ("AWAY", match.away)) for index, player in enumerate(team.players)}
    for player in players.values():
        player.pos.update(FIELD.centerx, FIELD.top + 20)
        player.z = 0.0
        player.motion_velocity.update(8, -4)
        player.skills = frozenset()
        player.technique_command = PlayerCommand.IDLE
    references = {**players, "HOME_GK": match.home.keeper, "AWAY_GK": match.away.keeper}
    # 検査用のIDを実参照へ戻し、位置・速度・通常値を型ごとに設定します。
    ball = match.ball
    ball.owner = ball.last_touch = ball.intended = None
    ball.pos.update(FIELD.center)
    ball.z = 0.0
    ball.vel.update(0, 0)
    for key, value in case["ball"].items():
        if key in ("position", "velocity"):
            horizontal, vertical = ("pos", "z") if key == "position" else ("vel", "vertical_speed")
            getattr(ball, horizontal).update(value[:2])
            setattr(ball, vertical, value[2])
        elif key in VECTORS:
            getattr(ball, key).update(value)
        elif key in ("owner", "last_touch", "intended"):
            setattr(ball, key, references.get(value))
        elif key == "recovery_team":
            ball.recovery_team = match.home if value == "HOME" else match.away
        else:
            setattr(ball, key, value)
    for record in case.get("players", []):
        # このケースに必要な選手だけをボール近くへ置き直します。
        player = references[record["id"]]
        player.pos.update(record["position"][:2])
        player.z = record["position"][2]
        player.sent_off = record.get("sent_off", False)
        player.jump_accuracy = record.get("jump_accuracy", player.jump_accuracy)
    return players


# {
#   責務: [capture_case: 実Pythonの自由ボール処理から一ケースの参照軌道を取得します]
#   処理: [1: 中立地・固定シードの試合と入力を構成します; 2: 指定の保持変更を実行します; 3: 成否・再開の境界を検査用応答へ差し替えます; 4: 最初の接触・場外まで固定更新を観測します]
#   引数: [home: 正規化済みのホームチーム入力; away: アウェーチーム入力; case: 初期値・操作・最大更新回数]
#   戻り値: [tuple: 初期状態と時点列。全試合・技能成功率・再開進行の参照ではありません]
# }
def capture_case(home: dict, away: dict, case: dict) -> tuple[dict, list[dict]]:
    # ケースごとに試合を作り直し、他ケースの乱数や飛行状態を持ち越しません。
    match = Match(home, away, "NEUTRAL", seed=41)
    match.start_new()
    players = configure(match, case)
    initial = {"ball": ball_values(match), "players": [{"id": key, "position": [player.pos.x, player.pos.y, player.z],
               "velocity": [player.motion_velocity.x, player.motion_velocity.y, 0], "sent_off": player.sent_off,
               "contact_jump_accuracy": player.effective_stat(player.jump_accuracy)} for key, player in players.items()]}
    operation = case.get("operation", "flight")
    # この二つの所有変更だけは実メソッドで行い、軌道計算の前提へ反映します。
    if operation == "spill":
        match.release_ball_from_knockback(players["HOME:1"], Vec2(0.6, 0.8), match.away if case.get("recovery") else None)
    elif operation.startswith("claim"):
        match.change_owner(players["HOME:1"], (8, -3) if operation == "claim" else None)
    # GKセーブは不成立に固定し、通常接触は確率抽選を固定して取得直前で止めます。
    # 比較対象は実弾道・幾何候補・場外検出で、技能成否・監督・再開進行ではありません。
    match.keeper_save = lambda: False
    match.rng.random = lambda: 0.0
    match.choose_pass_target = lambda player: None
    match.apply_pending_manager_changes = lambda reason: None
    pending = {"boundary": None, "contact": None, "ball": None}

    # {
    #   責務: [goal: 得点候補の検出だけを記録します]
    #   処理: [1: 得点側と検出時の位置を境界観測へ保存します]
    #   引数: [team: 得点候補となった実チーム]
    #   戻り値: [None: スコア加算・演出・再配置は実行しません]
    # }
    def goal(team):
        pending["boundary"] = {"kind": "GOAL", "side": "HOME" if team is match.home else "AWAY", "spot": list(match.ball.pos)}

    # {
    #   責務: [set_piece: セットプレー候補の種別と再開位置だけを記録します]
    #   処理: [1: 呼出元が決めた種別・側・位置を境界観測へ保存します]
    #   引数: [kind: 再開の種別; team: 再開側の実チーム; spot: 再開候補位置]
    #   戻り値: [None: キッカー移動や準備時間を進めません]
    # }
    def set_piece(kind, team, spot):
        pending["boundary"] = {"kind": kind, "side": "HOME" if team is match.home else "AWAY", "spot": list(spot)}

    original_throw = match.start_throw_in

    # {
    #   責務: [throw: 実スローイン検出の側と位置を取得します]
    #   処理: [1: 再開で変わる前のボールを保存します; 2: 元のスロー準備入口を呼びます; 3: 決定された側と位置を境界観測へ保存します]
    #   引数: []
    #   戻り値: [None: 準備入口の状態変更は検証試合だけに反映します。スロー進行は比較対象外です]
    # }
    def throw():
        # 場外へ出た物理状態と、準備用に置き直されたボールを混同しません。
        pending["ball"] = ball_values(match)
        original_throw()
        pending["boundary"] = {"kind": "THROW_IN", "side": "HOME" if match.throw_in_team is match.home else "AWAY", "spot": list(match.throw_in_spot)}

    # {
    #   責務: [touch: 実処理が取得しようとした最初の選手を記録して更新を中断します]
    #   処理: [1: 選手IDと手の可否を保存します; 2: 所有変更前にStopIterationで検査ループへ戻します]
    #   引数: [player: 取得処理へ到達した選手; args: 所有変更・GK処理の互換引数。使用しません]
    #   戻り値: [None: 常にStopIterationを送出します。実技能の成功率は評価しません]
    # }
    def touch(player, *args):
        pending["contact"] = {"kind": "TOUCH", "player": identity(match, player), "hands_legal": player.is_keeper and match.keeper_can_use_hands(player)}
        raise StopIteration

    match.handle_goal, match.start_set_piece, match.start_throw_in = goal, set_piece, throw
    match.change_owner = match.resolve_keeper_contact = touch
    frames = []
    # 接触中断だけを捕捉し、それ以外の演算失敗は検証失敗として伝播させます。
    for step in range(case["steps"]):
        try:
            match.update_loose_ball(0.05)
        except StopIteration:
            pass
        frames.append({"step": step + 1, "case_name": case["name"], "ball": pending["ball"] or ball_values(match),
                       "boundary": pending["boundary"], "contact": pending["contact"]})
        if pending["boundary"] is not None or pending["contact"] is not None:
            break
    return initial, frames


# {
#   責務: [observation: ボール部分観測を既存のトレース形式で包みます]
#   処理: [1: 時点値へ固定の未評価フィールドを加えてトレース要素を構成します]
#   引数: [frame: ボール・境界・候補の実観測; index: トレース内の連番]
#   戻り値: [dict: 全試合のスコア・時計・結果を評価したとは扱わない部分観測]
# }
def observation(frame: dict, index: int) -> dict:
    return {"operation_index": index, "snapshot": {**frame, "paused": False, "simulation_elapsed": 0.0,
            "status": {"state": "PLAYING", "game_time": 0.0, "home_score": 0, "away_score": 0},
            "home": {"players": []}, "away": {"players": []}, "restart": None}, "events": [], "result": None}


# {
#   責務: [write_ball_fixture: ボールの実Python参照と入力を開発用JSONへ保存します]
#   処理: [1: 既存の試合入力と元ファイルの指紋を取得します; 2: 全ケースを実行して観測列を作ります; 3: 有限なJSONを保存します; 4: 成否にかかわらず元チームの指紋を確認します]
#   引数: [output: fixtureを保存する開発用ディレクトリ]
#   戻り値: [tuple: fixtureのPathと元ファイル指紋。読込・実行・保存・指紋不一致は例外を通知します]
# }
def write_ball_fixture(output: Path = DEFAULT_OUTPUT) -> tuple[Path, dict[str, str]]:
    # 通常の入力生成器を再利用し、参照生成中に元チームを書き換えないことを監視します。
    path, hashes = write_fixture(output, 1)
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
        home, away, _, _ = restore_contract_input(document["input"])
        cases, entries = [], []
        # ケースの初期値と実観測を併記し、Godotは入力側から独立に計算します。
        for case in case_definitions():
            initial, frames = capture_case(home, away, case)
            cases.append({**deepcopy(case), "initial": initial, "frames": frames})
            first_index = len(entries)
            entries.extend(observation(frame, first_index + index) for index, frame in enumerate(frames))
        document["cases"] = cases
        document["reference"] = {"format": TRACE_FORMAT, "version": VERSION, "source": {
            "implementation": "python-ball-rules/Match.update_loose_ball", "execution": "simulation",
            "rng": "contact success intercepted; flight deterministic", "seed_text": "41"}, "entries": entries}
        path.write_text(json.dumps(document, ensure_ascii=False, allow_nan=False), encoding="utf-8")
        return path, hashes
    finally:
        # 途中の例外でも元データの変更検出を省略しません。
        assert_sources_unchanged(hashes)


# {
#   責務: [main: ボール参照生成の開発者用CLIを提供します]
#   処理: [1: 出力ディレクトリを解析します; 2: fixtureを保存して保存先を表示します]
#   引数: [argv: 任意のCLI引数。Noneならプロセス引数]
#   戻り値: [int: 成功0。生成や保存の失敗は例外として通知します]
# }
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    path, _ = write_ball_fixture(args.output)
    print(f"GODOT BALL FIXTURE: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
