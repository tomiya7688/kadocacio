"""旧版・不正CA・配布形態と、実エントリーポイントの診断を検査する。"""

import hashlib
import io
import json
import os
import runpy
import ssl
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from scripts.tools.python_trust_check import PythonTrustCheck, main as trust_check_main


# {
#   責務: [PythonTrustCheckTests: 既知ルートとツール版の誤合格およびGUIの誤起動を検出する]
#   フィールド: []
# }
class PythonTrustCheckTests(unittest.TestCase):
    # {
    #   責務: [test_versions_fail_closed: 数値の順序と旧版・不明版・開発版の拒否を確認する]
    #   処理: [1: 下限の前後と不正表記を比較する]
    #   引数: []
    #   戻り値: [None: 不明な版や古い版の誤合格は試験失敗]
    # }
    def test_versions_fail_closed(self):
        # 文字列なら逆転する26.10も、数値として比較する。
        for version, expected in (
            ("26.2.2", True),
            ("26.10", True),
            ("26.2.1", False),
            ("unknown", False),
            ("26.2.2rc1", False),
        ):
            with self.subTest(version=version):
                self.assertEqual(PythonTrustCheck.version_is_supported(version, "26.2.2"), expected)

    # {
    #   責務: [test_ca_inventory_rejects_empty_and_removed_root: 空ストアと実DERの対象ハッシュを拒否する]
    #   処理: [1: 空のCAを拒否する; 2: 同じDERハッシュだけを除去対象と判定する]
    #   引数: []
    #   戻り値: [None: 空ストアの合格や対象DERの見逃しは試験失敗]
    # }
    def test_ca_inventory_rejects_empty_and_removed_root(self):
        checker = PythonTrustCheck()
        context = Mock()
        context.get_ca_certs.return_value = []
        self.assertFalse(checker.ca_summary(context)["ok"])
        # 証明書名・PEMコメントを使わず、SSLから得たDERを判定対象とする。
        context.get_ca_certs.return_value = [b"test removed certificate"]
        fingerprint = hashlib.sha256(context.get_ca_certs.return_value[0]).hexdigest()
        with patch.object(checker, "REMOVED_ROOT_SHA256", fingerprint):
            report = checker.ca_summary(context)
            self.assertTrue(report["removed_root_present"])
            self.assertFalse(report["ok"])
        context.get_ca_certs.assert_called_with(binary_form=True)

    # {
    #   責務: [test_missing_or_invalid_bundle_is_not_safe: 未導入・不在・不正CAを失敗として返す]
    #   処理: [1: import失敗を検査する; 2: 不正PEMと存在しない実パスを検査する]
    #   引数: []
    #   戻り値: [None: 読込失敗を合格に置き換えると試験失敗]
    # }
    def test_missing_or_invalid_bundle_is_not_safe(self):
        checker = PythonTrustCheck()
        with patch("scripts.tools.python_trust_check.importlib.import_module", side_effect=ModuleNotFoundError("certifi")):
            self.assertFalse(checker.bundle_report("certifi", "2026.10.19")["ok"])
        # 実SSLのPEM解析を使い、単なる文字列の存在確認にはしない。
        with tempfile.TemporaryDirectory(prefix="kadocalcio-trust-") as directory:
            bundle = Path(directory) / "cacert.pem"
            module = SimpleNamespace(__version__="2026.10.23", where=Mock(return_value=bundle))
            with patch("scripts.tools.python_trust_check.importlib.import_module", return_value=module):
                self.assertFalse(checker.bundle_report("certifi", "2026.10.19")["ok"])
                bundle.write_text("not a certificate", encoding="ascii")
                self.assertFalse(checker.bundle_report("certifi", "2026.10.19")["ok"])

    # {
    #   責務: [test_valid_bundle_still_requires_supported_version: 実CAの一致とCA配布版の下限を両方確認する]
    #   処理: [1: インストール済みCAを実SSLで読む; 2: 同じCAでも旧版メタデータなら拒否する]
    #   引数: []
    #   戻り値: [None: CAの存在だけによる旧版の誤合格やファイルSHAの誤記録は試験失敗]
    # }
    def test_valid_bundle_still_requires_supported_version(self):
        import certifi

        # 実データを利用し、SSLContextの解析成功経路も検証する。
        bundle = Path(certifi.where()).resolve()
        module = SimpleNamespace(__version__="2026.10.23", where=Mock(return_value=bundle))
        with patch("scripts.tools.python_trust_check.importlib.import_module", return_value=module):
            report = PythonTrustCheck().bundle_report("certifi", "2026.10.19")
            self.assertTrue(report["ok"])
            self.assertEqual(report["sha256"], hashlib.sha256(bundle.read_bytes()).hexdigest())
            module.__version__ = "2026.10.18"
            self.assertFalse(PythonTrustCheck().bundle_report("certifi", "2026.10.19")["ok"])

    # {
    #   責務: [test_lazy_capath_cannot_hide_a_removed_root: 読込済みCAが正常でも遅延CAの対象残存と列挙失敗を拒否する]
    #   処理: [1: 別の実証明書をハッシュ名ファイルへ置く; 2: 未読込の対象CAと読取失敗を検出する]
    #   引数: []
    #   戻り値: [None: SSLContextの既存一覧だけによる誤合格や列挙不能の合格は試験失敗]
    # }
    def test_lazy_capath_cannot_hide_a_removed_root(self):
        import certifi

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=certifi.where())
        first, second = context.get_ca_certs(binary_form=True)[:2]
        loaded = Mock()
        loaded.get_ca_certs.return_value = [first]
        checker = PythonTrustCheck()
        with tempfile.TemporaryDirectory(prefix="kadocalcio-capath-") as directory:
            paths = ssl.DefaultVerifyPaths(None, directory, "KADOCALCIO_TEST_CA_FILE", "", "KADOCALCIO_TEST_CA_DIR", directory)
            entry = Path(directory) / "1234abcd.0"
            # PEM外の日本語コメントも含め、実SSLで解析可能な証明書を使う。
            entry.write_text("# 日本語コメント\n" + ssl.DER_cert_to_PEM_cert(second), encoding="utf-8")
            with (
                patch.object(checker, "REMOVED_ROOT_SHA256", hashlib.sha256(second).hexdigest()),
                patch("scripts.tools.python_trust_check.ssl.create_default_context", return_value=loaded),
                patch("scripts.tools.python_trust_check.ssl.get_default_verify_paths", return_value=paths),
            ):
                report = checker.system_store_report()
                self.assertFalse(report["removed_root_present"])
                self.assertFalse(report["ok"])
                self.assertEqual(report["capath"]["directories"][0]["removed_root_files"], [str(entry)])
                # インデックス外のファイルは対象外で、正常な遅延CAは合格できる。
                (Path(directory) / "unhashed.pem").write_text("not an indexed CA", encoding="ascii")
                entry.write_text(ssl.DER_cert_to_PEM_cert(first), encoding="ascii")
                self.assertTrue(checker.system_store_report()["ok"])
                # 明示パスの不在・空要素は、既定ディレクトリ不在の適用外扱いに混ぜない。
                with patch.dict(os.environ, {paths.openssl_capath_env: str(Path(directory) / "missing")}):
                    self.assertFalse(checker.system_store_report()["ok"])
                with patch.dict(os.environ, {paths.openssl_capath_env: directory + os.pathsep}):
                    self.assertFalse(checker.system_store_report()["ok"])
                with patch.dict(os.environ, {paths.openssl_capath_env: ""}):
                    self.assertFalse(checker.system_store_report()["ok"])
                with patch.object(Path, "iterdir", side_effect=PermissionError("unreadable CA directory")):
                    self.assertFalse(checker.system_store_report()["ok"])

    # {
    #   責務: [test_pem_fingerprints_do_not_depend_on_ca_filter: CA一覧から除外される証明書も実DERで照合する]
    #   処理: [1: 実PEMと空のCA一覧を準備する; 2: 対象一致を拒否し非対象の有効ファイルを認める]
    #   引数: []
    #   戻り値: [None: 空ファイルとの混同・CA属性による対象見逃し・certifiの空CA許容は試験失敗]
    # }
    def test_pem_fingerprints_do_not_depend_on_ca_filter(self):
        import certifi

        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=certifi.where())
        certificate = context.get_ca_certs(binary_form=True)[0]
        filtered = Mock()
        filtered.get_ca_certs.return_value = []
        checker = PythonTrustCheck()
        with tempfile.TemporaryDirectory(prefix="kadocalcio-ca-filter-") as directory:
            entry = Path(directory) / "1234abcd.0"
            entry.write_text(ssl.DER_cert_to_PEM_cert(certificate), encoding="ascii")
            with patch("scripts.tools.python_trust_check.ssl.SSLContext", return_value=filtered):
                with patch.object(checker, "REMOVED_ROOT_SHA256", hashlib.sha256(certificate).hexdigest()):
                    self.assertFalse(checker.ca_file_report(entry)["ok"])
                report = checker.ca_file_report(entry)
                self.assertTrue(report["ok"])
                self.assertEqual((report["ca_count"], report["certificate_count"]), (0, 1))
                module = SimpleNamespace(__version__="2026.10.23", where=Mock(return_value=entry))
                with patch("scripts.tools.python_trust_check.importlib.import_module", return_value=module):
                    self.assertFalse(checker.bundle_report("certifi", "2026.10.19")["ok"])

    # {
    #   責務: [test_installed_optional_tool_must_be_current: 任意ツールも存在するなら旧版を拒否する]
    #   処理: [1: 不在の任意ツールを適用外とする; 2: 存在する旧版を拒否する]
    #   引数: []
    #   戻り値: [None: uv等の旧版の誤合格は試験失敗]
    # }
    def test_installed_optional_tool_must_be_current(self):
        from importlib.metadata import PackageNotFoundError

        checker = PythonTrustCheck()
        with patch("scripts.tools.python_trust_check.importlib.metadata.version", side_effect=PackageNotFoundError("uv")):
            self.assertTrue(checker.package_report("uv", "0.13.4", optional=True)["ok"])
            self.assertFalse(checker.package_report("pip", "26.2.2")["ok"])
        with patch("scripts.tools.python_trust_check.importlib.metadata.version", return_value="0.13.3"):
            self.assertFalse(checker.package_report("uv", "0.13.4", optional=True)["ok"])

    # {
    #   責務: [test_store_and_cli_failures_stay_failures: ストア読込とCLI集約の失敗を隠さない]
    #   処理: [1: 実ストア読込例外を失敗として受ける; 2: CLIのJSONと終了1を確認する]
    #   引数: []
    #   戻り値: [None: ストア未確認や診断失敗の誤合格は試験失敗]
    # }
    def test_store_and_cli_failures_stay_failures(self):

        with patch(
            "scripts.tools.python_trust_check.ssl.create_default_context", side_effect=ssl.SSLError("unreadable store")
        ):
            self.assertFalse(PythonTrustCheck().system_store_report()["ok"])
        # JSONを読む運用でも終了コードだけを使うCIでも、失敗を検出できる。
        output = io.StringIO()
        with patch.object(PythonTrustCheck, "collect_report", return_value={"ok": False}), redirect_stdout(output):
            self.assertEqual(trust_check_main([]), 1)
        self.assertFalse(json.loads(output.getvalue())["ok"])

    # {
    #   責務: [test_cli_json_preserves_unicode_without_locale_dependency: 日本語を失わず出力コードページへの依存を除く]
    #   処理: [1: 日本語パスの診断を出力する; 2: ASCIIだけで表現されJSON再読込で復元されることを確認する]
    #   引数: []
    #   戻り値: [None: Windowsの文字コードによるデータ損失や不正JSONは試験失敗]
    # }
    def test_cli_json_preserves_unicode_without_locale_dependency(self):
        report = {"ok": True, "executable": "E:/日本語/python.exe"}
        output = io.StringIO()
        with patch.object(PythonTrustCheck, "collect_report", return_value=report), redirect_stdout(output):
            self.assertEqual(trust_check_main([]), 0)
        self.assertTrue(output.getvalue().isascii())
        self.assertEqual(json.loads(output.getvalue()), report)

    # {
    #   責務: [test_frozen_runtime_does_not_require_installer: 配布物にpipを要求せず実certifiは検査する]
    #   処理: [1: 配布実行属性で検査器を作る; 2: インストーラーを参照せずCA失敗を集約する]
    #   引数: []
    #   戻り値: [None: pipの必須化または配布CAの失敗見逃しは試験失敗]
    # }
    def test_frozen_runtime_does_not_require_installer(self):
        with patch.object(sys, "frozen", True, create=True):
            checker = PythonTrustCheck()
        # 偽の配布状態はCLIへ露出せず、試験内でのみ注入する。
        with (
            patch.object(checker, "package_report", side_effect=AssertionError("installer must not be used")),
            patch.object(checker, "bundle_report", return_value={"ok": False}) as bundle,
            patch.object(checker, "system_store_report", return_value={"ok": True}),
        ):
            self.assertFalse(checker.collect_report()["ok"])
            bundle.assert_called_once_with("certifi", "2026.10.19")

    # {
    #   責務: [test_real_entrypoint_reports_without_gui: 実ゲーム入口の診断がJSONを返して終了する]
    #   処理: [1: 隔離cwdから実診断入口を起動する; 2: 実CAと終了状態・GUI非起動を確認する]
    #   引数: []
    #   戻り値: [None: GUI混入・旧版・実CA不在・30秒無応答は試験失敗]
    # }
    def test_real_entrypoint_reports_without_gui(self):
        root = Path(__file__).resolve().parents[1]
        # 集約の実成功経路も確認し、サブプロセスだけに検証を閉じ込めない。
        output = io.StringIO()
        with redirect_stdout(output):
            status = trust_check_main([])
        self.assertEqual(status, 0, output.getvalue())
        self.assertTrue(json.loads(output.getvalue())["checks"]["pip_certifi"]["ok"])
        # 保存先はcwdではなく実行時ルートなので、初期化関数自体の呼出しを拒否する。
        with (
            patch(
                "scripts.core.paths.ensure_user_data_layout", side_effect=AssertionError("unexpected user-data initialization")
            ),
            patch.object(sys, "argv", [str(root / "main.py"), "--check-python-trust"]),
            redirect_stdout(io.StringIO()),
            self.assertRaises(SystemExit) as diagnostic,
        ):
            runpy.run_path(str(root / "main.py"), run_name="__main__")
        self.assertEqual(diagnostic.exception.code, 0)
        with tempfile.TemporaryDirectory(prefix="kadocalcio-trust-cli-") as directory:
            result = subprocess.run(
                [sys.executable, str(root / "main.py"), "--check-python-trust"],
                cwd=directory,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )
            # Pygameのバナー等が混じれば、診断入口のJSON解析が失敗する。
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertTrue(report["ok"])
            self.assertTrue(Path(report["checks"]["certifi"]["path"]).is_file())
            self.assertTrue(report["checks"]["pip"]["ok"])
            self.assertFalse((Path(directory) / "user_data").exists())
            # 診断の引数ミスで通常のゲーム起動へ流れない。
            invalid = subprocess.run(
                [sys.executable, str(root / "main.py"), "--check-python-trust", "--unknown"],
                cwd=directory,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=30,
            )
            self.assertEqual(invalid.returncode, 2, invalid.stderr)
            self.assertFalse((Path(directory) / "user_data").exists())
