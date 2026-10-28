"""実行中Pythonのバージョンと実CAの既知ルートを読取専用で検査する。"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import importlib.metadata
import json
import os
import re
import ssl
import sys
from pathlib import Path


# {
#   責務: [PythonTrustCheck: 現在のPythonが使うpip・certifiとCAの既知ルートを検査する]
#   フィールド: [frozen: 配布実行ファイルではインストーラーpipを検査対象にしない]
# }
class PythonTrustCheck:
    # certifiが除去したemSign ECC Root CA - G3のDER SHA-256。CAの名前では照合しない。
    REMOVED_ROOT_SHA256 = "86a1ecba089c4a8d3bbe2734c612ba341d813e043cf9e8a862cd5c57a36bbe6b"

    # {
    #   責務: [__init__: 実行中の配布形態を保持する]
    #   処理: [1: PyInstallerの実行属性を読み取る]
    #   引数: []
    #   戻り値: [None: 設定・証明書・インストール状態は変更しない]
    # }
    def __init__(self):
        # CLIから配布形態を偽装するオプションは提供しない。
        self.frozen = bool(getattr(sys, "frozen", False))

    # {
    #   責務: [version_is_supported: 数値の安定版だけを下限と比較する]
    #   処理: [1: バージョン表記を検証する; 2: 数値の各桁を比較する]
    #   引数: [version: 実際の配布版; minimum: 必須の安定版]
    #   戻り値: [bool: 不明・開発版・古い版はFalse]
    # }
    @staticmethod
    def version_is_supported(version: str, minimum: str) -> bool:
        # 文字列比較による26.10と26.2の逆転や、開発版の合格を防ぐ。
        if not isinstance(version, str) or not re.fullmatch(r"\d+(?:\.\d+)*", version):
            return False
        return tuple(map(int, version.split("."))) >= tuple(map(int, minimum.split(".")))

    # {
    #   責務: [ca_summary: SSLContextに実際に読み込まれたCAを照合する]
    #   処理: [1: 信頼アンカーのDERを取得する; 2: 既知の除去対象をハッシュで探す]
    #   引数: [context: 検査する信頼ストアを読み込み済みのコンテキスト]
    #   戻り値: [dict: CA数と既知ルートの有無。チェーン全体や失効確認の証明ではない]
    # }
    def ca_summary(self, context: ssl.SSLContext) -> dict:
        # subjectの文字列やPEMのコメントに依存せず、実証明書を検査する。
        certificates = context.get_ca_certs(binary_form=True)
        affected = any(hashlib.sha256(certificate).hexdigest() == self.REMOVED_ROOT_SHA256 for certificate in certificates)
        return {"ca_count": len(certificates), "removed_root_present": affected, "ok": bool(certificates) and not affected}

    # {
    #   責務: [ca_file_report: 同じ読込データから証明書とファイルSHAを確認する]
    #   処理: [1: 実ファイルと全PEMブロックを読み込む; 2: SSL解析と既知ルートの照合を行う]
    #   引数: [path: 検査するCAファイルまたはハッシュ名リンク]
    #   戻り値: [dict: 実パス・SHA・CA数と合否。不完全なPEMや読込失敗は例外]
    # }
    def ca_file_report(self, path: Path) -> dict:
        bundle = Path(path).resolve()
        bundle_bytes = bundle.read_bytes()
        # PEM外の国際化コメントを許し、途中で壊れた証明書は黙って省略しない。
        blocks = re.findall(rb"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", bundle_bytes, re.DOTALL)
        if not blocks or len(blocks) != bundle_bytes.count(b"-----BEGIN CERTIFICATE-----"):
            raise ValueError(f"Incomplete or missing certificate PEM: {bundle}")
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cadata=b"\n".join(blocks).decode("ascii"))
        # get_ca_certsはCA属性を持たない証明書を除くため、照合は全PEMのDERで行う。
        affected = any(
            hashlib.sha256(ssl.PEM_cert_to_DER_cert(block.decode("ascii"))).hexdigest() == self.REMOVED_ROOT_SHA256
            for block in blocks
        )
        return {
            "ca_count": len(context.get_ca_certs(binary_form=True)),
            "certificate_count": len(blocks),
            "removed_root_present": affected,
            "ok": not affected,
            "path": str(bundle),
            "sha256": hashlib.sha256(bundle_bytes).hexdigest(),
        }

    # {
    #   責務: [bundle_report: 指定パッケージの実バージョンと実CAファイルを検査する]
    #   処理: [1: 使用モジュールと実パスを解決する; 2: CAを読み込み照合する]
    #   引数: [module_name: certifiまたはpip内のcertifi; minimum: 必須のCA配布版]
    #   戻り値: [dict: バージョン・参照先・ファイルSHA256・照合結果。欠落や不正CAは失敗]
    # }
    def bundle_report(self, module_name: str, minimum: str) -> dict:
        # 経路の指定・CAの差替えはせず、現在のモジュールが返すwhere()を使う。
        try:
            module = importlib.import_module(module_name)
            version = getattr(module, "__version__", "unknown")
            result = self.ca_file_report(Path(module.where()))
            result.update(version=version, minimum=minimum)
            result["ok"] = result["ok"] and bool(result["ca_count"]) and self.version_is_supported(version, minimum)
            return result
        except (ImportError, OSError, ValueError, TypeError) as error:
            # 読めないCAや未導入を、安全だったという結果へ置き換えない。
            return {"ok": False, "error": f"{type(error).__name__}: {error}"}

    # {
    #   責務: [package_report: インストーラー類の実バージョンを検査する]
    #   処理: [1: 配布メタデータを取得する; 2: 必須版または任意依存の不在を判定する]
    #   引数: [name: 配布名; minimum: 必須版; optional: 未導入を適用外にできるか]
    #   戻り値: [dict: 実バージョンと合否。任意依存も存在するなら下限を守る]
    # }
    def package_report(self, name: str, minimum: str, *, optional: bool = False) -> dict:
        # uv/sigstoreを検査のために新規導入しない。
        try:
            version = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            return {"version": None, "ok": optional, "status": "not_installed"}
        return {"version": version, "minimum": minimum, "ok": self.version_is_supported(version, minimum)}

    # {
    #   責務: [capath_report: TLS接続時に遅延読込されるハッシュ名CAを検査する]
    #   処理: [1: 既定または環境指定のCAディレクトリを列挙する; 2: 全ハッシュ名ファイルを解析する]
    #   引数: [paths: 実行中OpenSSLが示す既定パスと環境変数名]
    #   戻り値: [dict: ディレクトリ・検査数・対象ファイルと合否。列挙不能や不正CAは失敗]
    # }
    def capath_report(self, paths: ssl.DefaultVerifyPaths) -> dict:
        explicit = paths.openssl_capath_env in os.environ
        specification = os.environ.get(paths.openssl_capath_env, paths.openssl_capath)
        directories = []
        # Windowsの存在しない既定capathは適用外。明示した不在パスは未確認として拒否する。
        for directory in specification.split(os.pathsep) if specification else []:
            item = {"path": directory, "checked_files": 0, "removed_root_files": [], "ok": True}
            directories.append(item)
            try:
                if not directory:
                    raise ValueError("Empty CA directory component")
                for entry in Path(directory).iterdir():
                    # OpenSSLのハッシュ名だけを対象にし、CRLやサブディレクトリはCAと混同しない。
                    if not re.fullmatch(r"[0-9a-fA-F]{8}\.[0-9]+", entry.name):
                        continue
                    report = self.ca_file_report(entry)
                    item["checked_files"] += 1
                    item["ok"] = item["ok"] and report["ok"]
                    if report["removed_root_present"]:
                        item["removed_root_files"].append(str(entry))
            except FileNotFoundError as error:
                # デフォルト自体が不在の場合だけ適用外で、壊れたハッシュリンクは拒否する。
                absent_default = not explicit and item["checked_files"] == 0 and not Path(directory).exists()
                item.update(ok=item["ok"] and absent_default, status="not_present" if absent_default else str(error))
            except (OSError, ValueError) as error:
                item.update(ok=False, error=f"{type(error).__name__}: {error}")
        return {"directories": directories, "ok": all(item["ok"] for item in directories)}

    # {
    #   責務: [system_store_report: Pythonの既定TLSコンテキストの信頼アンカーを観測する]
    #   処理: [1: 既定の検証コンテキストを構築する; 2: 実CAと既定パスを記録する]
    #   引数: []
    #   戻り値: [dict: 現在のPythonから見た既知ルートの照合結果。OSの失効処理は未検証]
    # }
    def system_store_report(self) -> dict:
        # WindowsのROOTを編集せず、利用中PythonのSSLContextだけを読む。
        try:
            result = self.ca_summary(ssl.create_default_context())
            paths = ssl.get_default_verify_paths()
            result["default_verify_paths"] = paths._asdict()
            result["capath"] = self.capath_report(paths)
            result["ok"] = result["ok"] and result["capath"]["ok"]
            return result
        except (OSError, ValueError) as error:
            return {"ok": False, "error": f"{type(error).__name__}: {error}"}

    # {
    #   責務: [collect_report: 現在の実行形態に必要な検査を一つの診断へ集約する]
    #   処理: [1: 実行環境と実CAを検査する; 2: ソース実行時のツール版を検査する; 3: 合否を集約する]
    #   引数: []
    #   戻り値: [dict: 読取専用の診断。通信・証明書変更・パッケージ更新は行わない]
    # }
    def collect_report(self) -> dict:
        checks = {"certifi": self.bundle_report("certifi", "2026.10.19"), "system_store": self.system_store_report()}
        # 配布物内で存在しないpipを必須にせず、ソース実行では同梱CAも必ず調べる。
        if not self.frozen:
            checks.update(
                pip=self.package_report("pip", "26.2.2"),
                pip_certifi=self.bundle_report("pip._vendor.certifi", "2026.10.19"),
                uv=self.package_report("uv", "0.13.4", optional=True),
                sigstore=self.package_report("sigstore", "4.5.1", optional=True),
            )
        return {
            "executable": sys.executable,
            "python": sys.version.split()[0],
            "openssl": ssl.OPENSSL_VERSION,
            "frozen": self.frozen,
            "scope": "Installed versions and known removed root only; not all chains, OS revocation or other TLS clients.",
            "checks": checks,
            "ok": all(check["ok"] for check in checks.values()),
        }


# {
#   責務: [main: 実行中Pythonの信頼診断を標準出力へ返す]
#   処理: [1: CLIの引数を確認する; 2: 実環境を検査してJSONと終了コードを返す]
#   引数: [argv: 省略時はプロセス引数。ゲーム入口からは診断フラグ以降の引数を渡す]
#   戻り値: [int: 検査範囲の合格は0、欠落・旧版・既知ルート残存は1]
# }
def main(argv: list[str] | None = None) -> int:
    # 保存先を暗黙に作らず、利用者が必要なら標準出力をログへ保存する。
    argparse.ArgumentParser(description=__doc__).parse_args(argv)
    report = PythonTrustCheck().collect_report()
    # ASCII表現のJSONなら日本語パスも保持し、Windowsの出力コードページに依存しない。
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
