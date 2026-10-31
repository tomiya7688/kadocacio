"""Windowsの実cmd入口でPython選択と失敗停止を検査する。"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows cmd launcher")


# {
#   責務: [launcher_project: 通信や実ゲームの保存を行わない起動試験用プロジェクトを用意する]
#   処理: [1: 実batと要求版を配置; 2: 診断とゲームの観測用入口を置く]
#   引数: [tmp_path: 試験専用の一時ディレクトリ; request: 検査する実batの指定]
#   戻り値: [Path: 空白を含む試験プロジェクト。実venvと保存データは変更しない]
# }
@pytest.fixture(params=["run_game.bat", "run_static_analysis.bat", "run_ai_evaluator.bat"])
def launcher_project(tmp_path, request):
    project = tmp_path / "game ! project"
    project.mkdir()
    shutil.copyfile(Path(__file__).resolve().parents[1] / request.param, project / request.param)
    (project / ".python-version").write_text(sys.version.split()[0], encoding="utf-8")
    # 起動順を観測し、旧版拒否より後の処理が実行されていないことも確認する。
    tools = project / "scripts" / "tools"
    tools.mkdir(parents=True)
    (tools / "python_trust_check.py").write_text("from pathlib import Path\nPath('trust-ran').touch()\n", encoding="utf-8")
    # 開発ツールの演算や全検査を起動せず、同じ観測用入口で引数と終了状態を記録する。
    analysis = tools / "static_analysis"
    analysis.mkdir()
    (analysis / "run_all.py").write_text("import runpy\nrunpy.run_path('main.py', run_name='__main__')\n", encoding="utf-8")
    (tools / "ai_evaluator.py").write_text("import runpy\nrunpy.run_path('main.py', run_name='__main__')\n", encoding="utf-8")
    (project / "pygame.py").write_text("", encoding="utf-8")
    (project / "main.py").write_text(
        "import json, sys\nprint(json.dumps({'python': sys.executable, 'args': sys.argv[1:]}))\n",
        encoding="utf-8",
    )
    return project


# {
#   責務: [run_launcher: 指定環境で実cmdとbatを一度だけ実行し結果を返す]
#   処理: [1: 親のPython指定を除外して試験値を設定; 2: 上限時間付きでcmdを実行]
#   引数: [project: 隔離プロジェクト; python: 明示指定する実行ファイル。Noneは自動選択; extra_environment: 環境上書き。None値は削除; delayed_expansion: 親cmdの遅延展開を有効にする指定]
#   戻り値: [CompletedProcess: 終了コードとUTF-8出力。時間超過は試験失敗]
# }
def run_launcher(project, python=None, extra_environment=None, delayed_expansion=False):
    environment = os.environ.copy()
    environment.pop("KADOCACIO_PYTHON", None)
    environment.pop("PYTHONPATH", None)
    environment.update(CI="1", PYTHONUTF8="1", PYGAME_HIDE_SUPPORT_PROMPT="1")
    if python is not None:
        environment["KADOCACIO_PYTHON"] = str(python)
    for name, value in (extra_environment or {}).items():
        if value is None:
            environment.pop(name, None)
        else:
            environment[name] = value
    return subprocess.run(
        [
            os.environ["COMSPEC"],
            "/d",
            "/v:on" if delayed_expansion else "/v:off",
            "/c",
            next(project.glob("*.bat")).name,
            "--check-python-trust",
        ],
        cwd=project,
        env=environment,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )


# {
#   責務: [test_explicit_python_and_arguments: 指定Pythonと診断引数がゲーム入口へ届くことを確認する]
#   処理: [1: 実Pythonを指定してbatを起動; 2: 実行ファイルと引数を照合]
#   引数: [launcher_project: 隔離プロジェクト]
#   戻り値: [None: 別Pythonの使用、引数欠落、起動失敗は試験失敗]
# }
def test_explicit_python_and_arguments(launcher_project):
    result = run_launcher(launcher_project, sys.executable)
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(result.stdout)
    assert Path(report["python"]) == Path(sys.executable)
    assert report["args"] == ["--check-python-trust"]


# {
#   責務: [test_version_mismatch_stops_before_dependencies: 要求版の不一致を依存導入とゲームより前に拒否する]
#   処理: [1: 要求版を不一致にする; 2: 診断さえ実行されていないことを確認]
#   引数: [launcher_project: 隔離プロジェクト]
#   戻り値: [None: 不一致での続行は試験失敗]
# }
def test_version_mismatch_stops_before_dependencies(launcher_project):
    (launcher_project / ".python-version").write_text("0.0.0", encoding="utf-8")
    result = run_launcher(launcher_project, sys.executable)
    assert result.returncode != 0
    assert "Required Python version:" in result.stdout
    assert "0.0.0" in result.stdout
    assert not (launcher_project / "trust-ran").exists()


# {
#   責務: [test_base_python_cannot_be_modified: 明示した通常Pythonへの依存インストールを拒否する]
#   処理: [1: venvではないPython本体を指定; 2: 依存診断より前の失敗を確認]
#   引数: [launcher_project: 隔離プロジェクト]
#   戻り値: [None: ベース環境を変更し得る起動は試験失敗]
# }
def test_base_python_cannot_be_modified(launcher_project):
    result = run_launcher(launcher_project, Path(sys.base_prefix) / "python.exe")
    assert result.returncode != 0
    assert not (launcher_project / "trust-ran").exists()


# {
#   責務: [test_missing_override_does_not_fallback: 不正な明示指定を別Pythonへ黙って置換しない]
#   処理: [1: 存在しない実行ファイルを指定; 2: 依存診断より前の失敗を確認]
#   引数: [launcher_project: 隔離プロジェクト]
#   戻り値: [None: 意図しないフォールバックは試験失敗]
# }
def test_missing_override_does_not_fallback(launcher_project):
    environment = launcher_project / "runtime" / "venv"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(environment)], check=True, timeout=30)
    result = run_launcher(launcher_project, launcher_project / "missing.exe")
    assert result.returncode != 0
    assert not (launcher_project / "trust-ran").exists()


# {
#   責務: [test_local_environment_selection: 並行runtimeと互換venvの実Pythonを起動できることを確認する]
#   処理: [1: 指定配置へ空の実venvを作成; 2: 明示指定なしで選択された実行ファイルを照合]
#   引数: [launcher_project: 隔離プロジェクト; relative: runtimeまたは旧形式のvenv配置]
#   戻り値: [None: 選択先の誤りや空白パスの起動失敗は試験失敗]
# }
@pytest.mark.parametrize("relative", ["runtime/venv", ".venv"])
def test_local_environment_selection(launcher_project, relative):
    environment = launcher_project / relative
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", str(environment)], check=True, timeout=30)
    # 並行配置があるときは、古いvenvの実行ファイルを使用しない。
    if relative == "runtime/venv":
        old_python = launcher_project / ".venv" / "Scripts" / "python.exe"
        old_python.parent.mkdir(parents=True)
        old_python.write_bytes(b"invalid executable")
    result = run_launcher(launcher_project)
    assert result.returncode == 0, result.stdout + result.stderr
    assert Path(json.loads(result.stdout)["python"]) == environment / "Scripts" / "python.exe"


# {
#   責務: [test_game_failure_returns_failure: 各入口の異常終了をbatが成功にしないことを確認する]
#   処理: [1: 観測用入口を異常終了させる; 2: CI中に待機せず失敗を返すことを確認]
#   引数: [launcher_project: 隔離プロジェクト; source: 正または負の終了状態を返す観測用入口]
#   戻り値: [None: エラーの成功扱いやpause待機は試験失敗]
# }
@pytest.mark.parametrize(
    "source", ["raise SystemExit(4)\n", "import ctypes\nctypes.windll.kernel32.ExitProcess(0xC0000005)\n"]
)
def test_game_failure_returns_failure(launcher_project, source):
    (launcher_project / "main.py").write_text(source, encoding="utf-8")
    result = run_launcher(launcher_project, sys.executable)
    assert result.returncode != 0
    if (launcher_project / "run_game.bat").exists():
        expected = "game stopped"
    elif (launcher_project / "run_ai_evaluator.bat").exists():
        expected = "AI evaluation failed"
    else:
        expected = "Static analysis failed"
    assert expected in result.stdout
    if (launcher_project / "run_ai_evaluator.bat").exists():
        # キー待機の有無にかかわらず、正負の終了状態を呼出し元へ保持する。
        expected_code = 4 if source.startswith("raise") else 0xC0000005
        assert (result.returncode & 0xFFFFFFFF) == expected_code


# {
#   責務: [test_tool_trust_failure_stops: 証明書診断の失敗後に開発ツールを開始しない]
#   処理: [1: 診断を異常終了させる; 2: 後続入口未実行と失敗を確認]
#   引数: [launcher_project: 隔離プロジェクト]
#   戻り値: [None: 失敗後の開発ツール開始や成功扱いは試験失敗]
# }
def test_tool_trust_failure_stops(launcher_project):
    if (launcher_project / "run_game.bat").exists():
        pytest.skip("Tool launchers only; game launcher repairs dependencies")
    # pipの導入や実データへのアクセスを伴わず、負の診断終了を再現する。
    (launcher_project / "scripts/tools/python_trust_check.py").write_text(
        "import ctypes\nctypes.windll.kernel32.ExitProcess(0xC0000005)\n", encoding="utf-8"
    )
    (launcher_project / "main.py").write_text("from pathlib import Path\nPath('analysis-ran').touch()\n", encoding="utf-8")
    result = run_launcher(launcher_project, sys.executable)
    assert result.returncode != 0
    assert not (launcher_project / "analysis-ran").exists()


# {
#   責務: [test_tool_python_environment_is_ignored: 親環境が検証済みPythonのモジュール読込を変えない]
#   処理: [1: 不正なPython環境を指定; 2: 開発ツール入口の正常実行を確認]
#   引数: [launcher_project: 隔離プロジェクト]
#   戻り値: [None: 親環境による起動失敗は試験失敗]
# }
def test_tool_python_environment_is_ignored(launcher_project):
    if (launcher_project / "run_game.bat").exists():
        pytest.skip("Tool launcher environment isolation")
    # PYTHONHOMEによるvenvの無効化とPYTHONPATHからのモジュール注入を同時に拒否する。
    (launcher_project / "sitecustomize.py").write_text("raise RuntimeError('injected')\n", encoding="utf-8")
    result = run_launcher(
        launcher_project,
        sys.executable,
        {"PYTHONHOME": str(launcher_project / "missing"), "PYTHONPATH": str(launcher_project)},
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert "injected" not in result.stderr
    assert Path(json.loads(result.stdout)["python"]) == Path(sys.executable)


# {
#   責務: [test_evaluator_no_pause: CI以外の自動実行でもキー待機を省略できることを確認する]
#   処理: [1: CIを解除して待機省略を指定; 2: 親cmdの展開設定にかかわらずJSON単体出力と環境を照合]
#   引数: [launcher_project: AI評価batだけを置いた隔離プロジェクト; delayed_expansion: 親cmdの遅延展開設定]
#   戻り値: [None: 意図しない待機や失敗は試験失敗]
# }
@pytest.mark.parametrize("launcher_project", ["run_ai_evaluator.bat"], indirect=True)
@pytest.mark.parametrize("delayed_expansion", [False, True])
def test_evaluator_no_pause(launcher_project, delayed_expansion):
    # CIは空値で代用せず削除し、子Pythonでも未定義であることを観測する。
    (launcher_project / "main.py").write_text(
        "import json, os, sys\nprint(json.dumps({'python': sys.executable, 'ci': os.environ.get('CI')}))\n",
        encoding="utf-8",
    )
    result = run_launcher(
        launcher_project,
        sys.executable,
        {"CI": None, "KADOKA_NO_PAUSE": "1"},
        delayed_expansion,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    # 日本語を含む任意のpause出力が混ざれば、JSON単体として解析できない。
    report = json.loads(result.stdout)
    assert report["ci"] is None
    assert Path(report["python"]) == Path(sys.executable)
