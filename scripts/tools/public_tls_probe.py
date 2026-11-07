"""公開の証明書試験先で、実行中のTLSクライアントの判断を検証する。"""

import socket
import ssl

# Microsoftが案内したeMudhra試験サイトの正常対照とクロス署名経路。
CONTROL_HOST = "emudhra.we-have-a-problem.com"
AFFECTED_HOST = "dv-g3b-aaa-emudhra.we-have-a-problem.com"
CONNECTION_TIMEOUT = 8
CERT_REJECTED = 28
UNABLE_TO_GET_ISSUER = 20


# {
#   責務: [handshake: ホスト名を検証したTLS接続の結果を分類する]
#   処理: [1: 上限時間付きでTCP接続する; 2: 証明書を検証してTLSを開始する]
#   引数: [host: 試験ホスト名; context: 信頼経路を設定したクライアント]
#   戻り値: [dict: TLS版・証明書エラーコード・通信エラーのいずれか]
# }
def handshake(host: str, context: ssl.SSLContext) -> dict:
    # HTTP要求やアプリケーションデータは送らず、TLSの成立だけを確認する。
    try:
        with (
            socket.create_connection((host, 443), timeout=CONNECTION_TIMEOUT) as connection,
            context.wrap_socket(connection, server_hostname=host) as secure,
        ):
            return {"status": "accepted", "protocol": secure.version()}
    except ssl.SSLCertVerificationError as error:
        return {"status": "certificate_rejected", "verify_code": error.verify_code, "message": error.verify_message}
    except OSError as error:
        return {"status": "transport_error", "error": str(error)}


# {
#   責務: [probe_trust_source: 一つの信頼経路で正常対照と対象の拒否を判定する]
#   処理: [1: 指定した信頼経路のコンテキストを構成する; 2: 二つのホストで接続を試す; 3: 結果を照合する]
#   引数: [cafile: certifiの実ファイル、NoneはPython既定の信頼経路; expected_code: 対象の想定拒否コード]
#   戻り値: [dict: 2回の接続結果と合否。コンテキスト構成失敗は不合格]
# }
def probe_trust_source(cafile: str | None, expected_code: int) -> dict:
    # 明示したCAファイルの読込失敗を既定ストアで代用しない。
    try:
        context = ssl.create_default_context(cafile=cafile)
    except (OSError, ValueError) as error:
        return {"ok": False, "status": "context_error", "error": str(error)}

    # 期限切れやホスト名違い、通信不能は今回の拒否を証明しない。
    control = handshake(CONTROL_HOST, context)
    affected = handshake(AFFECTED_HOST, context)
    return {
        "control": control,
        "affected": affected,
        "expected_verify_code": expected_code,
        "ok": control["status"] == "accepted"
        and affected["status"] == "certificate_rejected"
        and affected["verify_code"] == expected_code,
    }


# {
#   責務: [public_tls_report: Python既定とcertifiで公開試験先への実接続を判定する]
#   処理: [1: 既定経路を検証する; 2: 診断で確認済みのCAファイルで検証する; 3: 合否をまとめる]
#   引数: [certifi_path: 診断で取得したcertifiのパス。取得できない場合はNone]
#   戻り値: [dict: 試験先、信頼経路ごとの結果、総合判定]
# }
def public_tls_report(certifi_path: str | None) -> dict:
    # 既定経路は中間CAの拒否、certifiは発行元CAに到達できないことを確認する。
    default = probe_trust_source(None, CERT_REJECTED)
    certifi = (
        probe_trust_source(certifi_path, UNABLE_TO_GET_ISSUER)
        if certifi_path
        else {"ok": False, "status": "bundle_unavailable"}
    )
    return {
        "control_host": CONTROL_HOST,
        "affected_host": AFFECTED_HOST,
        "default": default,
        "certifi": certifi,
        "ok": default["ok"] and certifi["ok"],
    }
