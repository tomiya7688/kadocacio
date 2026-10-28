# Pythonの証明書対応

Issue #155のeMudhra/emSign対応として、古いpipに同梱されたCAを更新します。
pipは独自のcertifiを持つため、通常のcertifiだけを更新してもpipの対策にはなりません。
ゲームの物理・AI・試合データは変更しません。

## 更新方法

GitルートのPowerShellで、使用するPythonを指定して実行してください。
仮想環境を作り直した場合も、依存をインストールする前に実行してください。

```powershell
python -m pip --isolated --disable-pip-version-check install --upgrade --no-deps --require-hashes -r requirements-bootstrap.txt
python -m scripts.tools.python_trust_check
python -m pip install -r requirements-dev.txt
python -m pip check
```

`requirements-bootstrap.txt`は、公式案内のpip 26.2.2とPyPIのcertifi 2026.10.23をURLとSHA-256で固定します。
更新前のpipで取得する場合も、ハッシュが一致しないwheelはインストールしません。TLS検証は無効にしません。
`run_game.bat`は診断に失敗した環境を更新して再確認し、CIも依存導入前に同じ固定ファイルを使用します。

## 実環境・配布物の確認

開発者は、検査するPythonで `python -m scripts.tools.python_trust_check` を実行してください。
アプリは実行Python、OpenSSL、pip・certifiの版、実CAパス・SHA-256・CA数、既知の除去ルートの有無をJSONで返します。
OpenSSLが遅延読込するcapathのハッシュ名CAファイルも確認し、列挙不能・読取失敗・対象ルート残存を失敗にします。
ファイル単位の読取・解析エラーは一覧へ記録し、後続ファイルの検査を続けます。ディレクトリの列挙自体が失敗した場合も診断を失敗にします。
開発者が `SSL_CERT_DIR` を明示する場合、空文字・空のパス要素・不在のパスは診断失敗になります。
ファイル内の全証明書をDERで照合するため、OpenSSLのCA一覧に含まれない証明書も見落としません。certifi自体にはCAの存在も要求します。
JSONはASCII表現で出力し、日本語パスもJSONの再読込で復元できます。Windowsの出力コードページには依存しません。
未導入、不正CA、必要版未満、既知ルート残存は終了コード1です。結果を保存する場合は標準出力をログへ転送してください。
uvとsigstoreのPython配布パッケージは存在する場合のみ版を確認し、検査のための新規導入は行いません。Windows CIのuv CLIは固定版を別に確認します。

Windows配布物では `Kadocacio.exe --check-python-trust` を実行してください。
GUIを生成せず、展開先の実certifiと既定TLSストアを検査します。配布物にpipは要求しません。
Windows smokeはクリーンビルドにcertifiの実データを含め、完成した実行ファイルでこの診断を実行します。
古いexeを、このソース変更だけで更新済みとは扱わないでください。

## 検査の範囲

この診断の合格は、バージョンと既知の除去ルートの照合に限ります。
すべての証明書チェーン、OSの失効リスト、カスタムTLSクライアント、他フォルダのPython環境を検証した結果ではありません。
Windowsの証明書ストアを変更せず、問題が残る場合は診断を失敗として返します。
UbuntuのCIでは、システムCAに対象ルートが残った実例があるため、`ca-certificates`を更新してから診断します。
この更新はCIの一時環境に対して行い、ローカルのOS証明書をアプリから自動変更する処理ではありません。
Windowsの一時CI環境でも残存を確認したため、LocalMachine/CurrentUserのRoot・CAストアから実DERのSHA-256が一致する既知ルートだけを除去します。
この処理をローカル環境へ適用するコマンドは提供しません。各ネイティブコマンドの失敗は後続処理で打ち消さずCIを終了します。
Python 3.10はサポート終了済みです。Linux主検証とWindows配布ビルドは修正版へ更新します。既存ローカルvenvの自動更新は行いません。[実行環境の更新手順](Python実行環境.md)で対象と確認方法を確認してください。
Issue全体を完了する前に、OS・使用中の別ランタイム・既存成果物の信頼経路も確認してください。
署名とArtifact Attestationは別のIssue #156で扱います。

根拠は[Python公式の案内](https://discuss.python.org/t/information-for-python-users-regarding-emudhra-emsign-ca-certificate-security-incident/109576)、[pipの変更履歴](https://pip.pypa.io/en/stable/news/#v26-2-2)、[certifiの公開ファイル](https://pypi.org/project/certifi/2026.10.23/#files)です。
