"""固定版formatterの実行・非更新チェック・生成物除外を確認する。"""

import ast
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest
from functools import partial
from pathlib import Path


# {
#   責務: [PythonFormatterTests: 実Ruffの意味保存・再実行性・除外とCIの差分限定を検査する]
#   フィールド: []
# }
class PythonFormatterTests(unittest.TestCase):
    # {
    #   責務: [run_formatter: リポジトリの固定設定で一つの試験ファイルだけを整形または確認する]
    #   処理: [1: 現在のPythonと固定設定を指定する; 2: 上限時間付きの実CLIで結果を取得する]
    #   引数: [path: 試験専用ファイル; check: 書換えず不整形を検出するか; config: 省略時はリポジトリの設定]
    #   戻り値: [CompletedProcess: 標準出力・標準エラー・終了コード。30秒無応答は試験エラー]
    # }
    def run_formatter(self, path, *, check=False, config=None):
        # グローバルのformatterや暗黙の全体整形を使わず、対象を必ず指定する。
        config = config or Path(__file__).resolve().parents[1] / "ruff.toml"
        command = [sys.executable, "-m", "ruff", "format", "--config", str(config), "--no-cache"]
        if check:
            command.append("--check")
        return subprocess.run(
            command + ["--", str(path)], cwd=config.parent, capture_output=True, text=True, encoding="utf-8", timeout=30
        )

    # {
    #   責務: [clean_git_environment: 親リポジトリへ操作を向ける環境変数を試験から除く]
    #   処理: [1: GIT_変数を除いた新しい辞書を返す]
    #   引数: [source: 呼出し元の環境。元の辞書は変更しない]
    #   戻り値: [dict: Gitの宛先・index・注入設定を引き継がない環境]
    # }
    def clean_git_environment(self, source):
        # フック経由の実行でも、使い捨てrepo以外へadd/commitしない。
        return {name: value for name, value in source.items() if not name.upper().startswith("GIT_")}

    # {
    #   責務: [find_windows_git_bash: Git実体の近傍から同梱Bashだけを解決する]
    #   処理: [1: cmd/bin/usr/bin/mingw64/bin配置を候補探索する; 2: 実在するBashを返す]
    #   引数: [git_executable: 検出したGit実体]
    #   戻り値: [Path: Bash実体。未導入は説明付きの試験失敗。WSLへフォールバックしない]
    # }
    def find_windows_git_bash(self, git_executable):
        # 親は最大3階層だけ調べ、全ディスクの探索は行わない。
        for parent in list(Path(git_executable).resolve().parents)[:3]:
            for relative in ("bin/bash.exe", "usr/bin/bash.exe"):
                candidate = parent / relative
                if candidate.is_file():
                    return candidate
        self.fail("開発試験にはGit同梱のbin/bash.exeまたはusr/bin/bash.exeが必要です")

    # {
    #   責務: [load_ci_script: 検査対象と同じCI本文を説明付きで取り出す]
    #   処理: [1: 対象ステップとrun記法を確認する; 2: Bash本文を返す]
    #   引数: []
    #   戻り値: [str: 実CI本文。構造変更はIndexErrorではなく試験の説明付き失敗]
    # }
    def load_ci_script(self):
        # 外部YAML依存を増やさず、管理下のステップ構造の変化を明示する。
        root = Path(__file__).resolve().parents[1]
        workflow = (root / ".github/workflows/python-app.yml").read_text(encoding="utf-8")
        marker = "      - name: Check changed Python formatting\n"
        self.assertEqual(workflow.count(marker), 1, "CI整形ステップの名前・構造が変更されています")
        block = workflow.split(marker, 1)[1]
        self.assertIn("        run: |\n", block, "CI整形のrun記法が変更されています")
        return textwrap.dedent(block.split("        run: |\n", 1)[1].split("\n      - name:", 1)[0])

    # {
    #   責務: [run_ci_script: 隔離repoと環境で実CI本文を一度実行する]
    #   処理: [1: Bashへ本文を渡し終了状態を得る]
    #   引数: [bash: 実在するBash; script: CI本文; repo: 一時repo; environment: 隔離環境]
    #   戻り値: [CompletedProcess: 終了コード・診断。45秒無応答は試験エラー]
    # }
    def run_ci_script(self, bash, script, repo, environment):
        # 成否の判断は各シナリオへ残し、呼出し方法だけを共通化する。
        return subprocess.run(
            [str(bash), "--noprofile", "--norc", "-s"],
            input=script,
            cwd=repo,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=45,
        )

    # {
    #   責務: [run_fixture_git: 隔離repoだけの準備操作を実行する]
    #   処理: [1: hook・署名・fsmonitorを無効にして指定操作を実行する]
    #   引数: [repo: 一時repo; hooks: 空のhookディレクトリ; environment: 隔離環境; arguments: 試験内で固定したGit引数]
    #   戻り値: [str: 標準出力。失敗や30秒無応答は試験エラー]
    # }
    def run_fixture_git(self, repo, hooks, environment, *arguments):
        # 引数だけでなく環境も制限し、親プロセスのGit状態を使用しない。
        return subprocess.run(
            [
                "git",
                "-c",
                f"core.hooksPath={hooks}",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "commit.gpgsign=false",
                "-c",
                "user.name=FormatterFixture",
                "-c",
                "user.email=fixture@localhost",
                *arguments,
            ],
            cwd=repo,
            env=environment,
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=30,
            check=True,
        ).stdout.strip()

    # {
    #   責務: [test_check_is_read_only_and_format_preserves_ast: 不整形の検出と意味を変えない再整形を確認する]
    #   処理: [1: 試験専用の不整形コードを準備する; 2: checkの非更新と終了1を確認する; 3: 整形後の構文木・再check・再整形の同一性を確認する]
    #   引数: []
    #   戻り値: [None: 検出漏れ・書換え・構文の意味変更・非冪等は試験失敗]
    # }
    def test_check_is_read_only_and_format_preserves_ast(self):
        # 日本語・空白を含むパスで、オプションとファイルの境界も確認する。
        with tempfile.TemporaryDirectory(prefix="kadocalcio-format-") as directory:
            path = Path(directory) / "整形 対象.py"
            original = 'def sample( value ):\n    return { "値":value }\n'
            path.write_text(original, encoding="utf-8")
            original_bytes = path.read_bytes()
            self.assertEqual(self.run_formatter(path, check=True).returncode, 1)
            self.assertEqual(path.read_bytes(), original_bytes)
            # 整形後はAST一致・check成功・再実行で内容不変を要求する。
            self.assertEqual(self.run_formatter(path).returncode, 0)
            formatted = path.read_text(encoding="utf-8")
            formatted_bytes = path.read_bytes()
            self.assertNotEqual(formatted, original)
            self.assertEqual(ast.dump(ast.parse(formatted)), ast.dump(ast.parse(original)))
            self.assertEqual(self.run_formatter(path, check=True).returncode, 0)
            self.assertEqual(self.run_formatter(path).returncode, 0)
            self.assertEqual(path.read_bytes(), formatted_bytes)

    # {
    #   責務: [test_explicit_generated_files_are_excluded: 明示指定されても生成物やvendor・仮想環境を変更しないことを確認する]
    #   処理: [1: 除外対象に不正構文の試験ファイルを作る; 2: format/checkが解析せず成功し内容を保持することを確認する]
    #   引数: []
    #   戻り値: [None: 除外対象の解析・変更は試験失敗。実データには触れない]
    # }
    def test_explicit_generated_files_are_excluded(self):
        # 不正構文は、除外が効かず実際に解析された場合を検出するために使う。
        with tempfile.TemporaryDirectory(prefix="kadocalcio-exclusions-") as directory:
            # 除外はプロジェクト相対なので、隔離した模擬プロジェクトへ同じ設定を置く。
            config = Path(directory) / "ruff.toml"
            config.write_bytes((Path(__file__).resolve().parents[1] / "ruff.toml").read_bytes())
            for folder in (
                "user_data",
                "vendor",
                ".venv",
                "static_analysis/reports",
                "runtime",
                "python_embed",
                "teams",
                "teameditor_templete",
                "godot",
            ):
                with self.subTest(folder=folder):
                    path = Path(directory) / folder / "generated.py"
                    path.parent.mkdir(parents=True)
                    original = "not valid python {"
                    path.write_text(original, encoding="utf-8")
                    self.assertEqual(self.run_formatter(path, config=config).returncode, 0)
                    self.assertEqual(self.run_formatter(path, check=True, config=config).returncode, 0)
                    self.assertEqual(path.read_text(encoding="utf-8"), original)

    # {
    #   責務: [test_ci_limits_check_to_changed_python: 実GitとCIのbash本文で差分限定・不整形拒否・空集合を確認する]
    #   処理: [1: 隔離Gitを準備する; 2: 日本語・空白名の追加を確認する; 3: 不整形・空集合・名前変更・削除を区別する]
    #   引数: []
    #   戻り値: [None: 範囲外検査・未検出・書換えは試験失敗。Git/Bash未導入や45秒無応答は試験エラー]
    # }
    def test_ci_limits_check_to_changed_python(self):
        # WindowsはWSLのbashではなく、開発用Gitに付属する実体を使う。
        git_executable = shutil.which("git")
        self.assertIsNotNone(git_executable, "開発試験にはGitが必要です")
        bash = self.find_windows_git_bash(git_executable) if os.name == "nt" else shutil.which("bash")
        self.assertTrue(bash and Path(bash).is_file(), "開発試験には実在するBashが必要です")
        root = Path(__file__).resolve().parents[1]
        script = self.load_ci_script()
        environment = self.clean_git_environment(os.environ)
        environment["PATH"] = str(Path(sys.executable).parent) + os.pathsep + environment.get("PATH", "")
        with tempfile.TemporaryDirectory(prefix="kadocalcio-ci-format-") as directory:
            repo = Path(directory) / "repo"
            hooks = Path(directory) / "empty-hooks"
            runner = Path(directory) / "runner"
            for folder in (repo, hooks, runner):
                folder.mkdir()

            # ユーザーのglobal/system設定も読まない。設定ファイルは一時領域だけに置く。
            config = Path(directory) / "empty.gitconfig"
            config.write_text("", encoding="utf-8")
            environment.update({"GIT_CONFIG_GLOBAL": str(config), "GIT_CONFIG_NOSYSTEM": "1"})
            git = partial(self.run_fixture_git, repo, hooks, environment)

            # 旧コードは未整形のまま残し、今回の追加ファイルだけを通す。
            git("init", f"--template={hooks}", "--initial-branch=kadoka/formatter-fixture")
            git("config", "core.fsmonitor", "false")
            (repo / "ruff.toml").write_bytes((root / "ruff.toml").read_bytes())
            (repo / "legacy.py").write_text("legacy=  1\n", encoding="utf-8")
            git("add", "--all")
            git("commit", "-qm", "baseline")
            base = git("rev-parse", "HEAD")
            path = repo / "日本語 team.py"
            path.write_text("result = 1\n", encoding="utf-8")
            git("add", "--all")
            git("commit", "-qm", "formatted addition")
            environment.update({"FORMAT_BASE": base, "RUNNER_TEMP": runner.as_posix()})
            with self.subTest(scenario="追加・空白・日本語名"):
                result = self.run_ci_script(bash, script, repo, environment)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual((repo / "legacy.py").read_text(encoding="utf-8"), "legacy=  1\n")
            # 不整形の変更は拒否するが、CIは修正せずそのまま残す。
            path.write_text("result=  2\n", encoding="utf-8")
            unformatted_bytes = path.read_bytes()
            git("add", "--all")
            git("commit", "-qm", "unformatted change")
            with self.subTest(scenario="不整形拒否・非更新"):
                result = self.run_ci_script(bash, script, repo, environment)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(path.read_bytes(), unformatted_bytes)
            # Python変更ゼロでは、既存の未整形ファイルへ検査を広げない。
            environment["FORMAT_BASE"] = git("rev-parse", "HEAD")
            (repo / "README.md").write_text("fixture\n", encoding="utf-8")
            git("add", "--all")
            git("commit", "-qm", "documentation only")
            with self.subTest(scenario="Python変更ゼロ"):
                result = self.run_ci_script(bash, script, repo, environment)
                self.assertEqual(result.returncode, 0, result.stderr)
            # 名前変更は追加として検出し、削除だけなら検査対象ゼロになる。
            environment["FORMAT_BASE"] = git("rev-parse", "HEAD")
            renamed = repo / "名前変更.py"
            path.rename(renamed)
            git("add", "--all")
            git("commit", "-qm", "rename")
            with self.subTest(scenario="名前変更"):
                self.assertNotEqual(self.run_ci_script(bash, script, repo, environment).returncode, 0)
            environment["FORMAT_BASE"] = git("rev-parse", "HEAD")
            renamed.unlink()
            git("add", "--all")
            git("commit", "-qm", "delete")
            with self.subTest(scenario="削除"):
                result = self.run_ci_script(bash, script, repo, environment)
                self.assertEqual(result.returncode, 0, result.stderr)

    # {
    #   責務: [test_parent_git_environment_is_not_inherited: フック由来のGit宛先・index注入を除外することを確認する]
    #   処理: [1: 危険な環境を模擬する; 2: Git変数の除去と元辞書の非更新を照合する]
    #   引数: []
    #   戻り値: [None: 宛先注入や呼出し元の変更は試験失敗。実Gitには危険な値を渡さない]
    # }
    def test_parent_git_environment_is_not_inherited(self):
        # パスの模擬値を実Gitへ渡さず、フィルタだけを検査する。
        source = {"GIT_DIR": "outside", "git_index_file": "outside", "GIT_WORK_TREE": "outside", "PATH": "keep"}
        original = dict(source)
        self.assertEqual(self.clean_git_environment(source), {"PATH": "keep"})
        self.assertEqual(source, original)

    # {
    #   責務: [test_windows_git_layouts_find_bundled_bash: 標準・mingw64配置とusr/binの実在確認を検査する]
    #   処理: [1: 模擬配置を作る; 2: 3種類のGit位置から同梱Bashを照合する; 3: 不在を説明付きで拒否する]
    #   引数: []
    #   戻り値: [None: 探索漏れや未存在の返却は試験失敗。模擬exeは実行しない]
    # }
    def test_windows_git_layouts_find_bundled_bash(self):
        # Windows以外でも配置解決だけを試験できるよう、通常ファイルを使う。
        with tempfile.TemporaryDirectory(prefix="kadocalcio-bash-layout-") as directory:
            root = Path(directory)
            bash = root / "usr/bin/bash.exe"
            bash.parent.mkdir(parents=True)
            bash.touch()
            for relative in ("cmd/git.exe", "bin/git.exe", "mingw64/bin/git.exe"):
                with self.subTest(layout=relative):
                    git = root / relative
                    git.parent.mkdir(parents=True, exist_ok=True)
                    git.touch()
                    self.assertEqual(self.find_windows_git_bash(git), bash)
            bash.unlink()
            with self.assertRaisesRegex(AssertionError, "Git同梱"):
                self.find_windows_git_bash(root / "cmd/git.exe")


if __name__ == "__main__":
    unittest.main()
