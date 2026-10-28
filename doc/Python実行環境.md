# Python実行環境の更新

## 背景と今回の対象

Python 3.10はサポートが終了しています。証明書インシデントへの対応を継続するため、Linuxの主検証・分岐カバレッジとWindowsの配布ビルドを修正版Python 3.13.18へ移します。ゲームの演算・データ・依存ライブラリの種類は変更しません。

主検証の版はルートの `.python-version` が正本です。2つのLinuxジョブは `actions/setup-python` の `python-version-file` から読み、Windowsジョブは同じファイルをuvへ渡します。分岐検査とWindows検査はこのファイルの変更時にも実行します。互換ジョブは修正を含む3.11.18と3.12.16を明示し、古いキャッシュが選ばれることを防ぎます。

## 開発者の確認方法

開発者は、対応するPythonを別の場所へ用意し、既存venvを消さずに新しい検証環境を作成してください。作成した環境のPythonを指定して、Gitルートで次を実行してください。

```text
python -VV
python -m pip --isolated --disable-pip-version-check install --upgrade --no-deps --require-hashes -r requirements-bootstrap.txt
python -m scripts.tools.python_trust_check
python -m pip install -r requirements-dev.txt
python -m pip check
python -m pytest -q
```

`.python-version` はCIの選択に使用します。`run_game.bat` が既存venvやOSのPythonを更新する処理は追加していません。venv内のpip更新だけで、Python本体が更新されたとは扱わないでください。

GitHubでは主検証・分岐検査・Python互換ジョブのログから、実Python版と全試験の結果を確認してください。証明書の診断成功だけを、全チェーン・失効確認やゲームの互換試験の成功へ読み替えないでください。

CI設定を変更する開発者は、固定版Prettier 3.6.2で対象ファイルだけを整形してください。Gitルートで `npm exec --yes --package=prettier@3.6.2 -- prettier --write .github/workflows/windows-smoke.yml` を実行し、`--write` を `--check` に変えて再確認してください。Linux側の変更時も対象のYAMLだけを指定してください。既存のPython整形にはRuffを使用します。

## Windowsの修正版Python

Python公式の3.13.18はソースのみで、Windowsインストーラーを提供していません。Windows CIではAstralのpython-build-standaloneをuv 0.13.6で導入し、通常のGILを使うCPythonを選択します。setup-uvのコミットとuvバイナリのSHA-256を固定し、Pythonの版は `.python-version` と一致させます。

開発者がローカルで検証する場合も、既存venvを削除せず、Eドライブの未使用フォルダーを指定してください。SHA-256を照合した公式uv 0.13.6を別途用意し、GitルートのPowerShellで次を実行してください。例のuvパスは実際の配置へ変更してください。

```powershell
$uv = 'E:/tools/uv-0.13.6/uv.exe'
$runtimeRoot = 'E:/tools/kadocacio-python-validation'
$env:UV_CACHE_DIR = Join-Path $runtimeRoot 'uv-cache'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $runtimeRoot 'python'
$env:UV_NO_CONFIG = '1'
$env:TEMP = $runtimeRoot
$env:TMP = $runtimeRoot
New-Item -ItemType Directory -Path $runtimeRoot -ErrorAction Stop
$version = (Get-Content .python-version -Raw).Trim()
& $uv python install --no-bin --no-registry $version
if ($LASTEXITCODE -ne 0) { throw 'Python install failed' }
& $uv venv --managed-python --python $version (Join-Path $runtimeRoot 'venv')
if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
$python = Join-Path $runtimeRoot 'venv/Scripts/python.exe'
& $uv pip install --python $python --no-deps --require-hashes -r requirements-bootstrap.txt
if ($LASTEXITCODE -ne 0) { throw 'Bootstrap failed' }
& $python -m pip install -r requirements-dev.txt --cache-dir (Join-Path $runtimeRoot 'pip-cache')
if ($LASTEXITCODE -ne 0) { throw 'Dependency install failed' }
& $python -m scripts.tools.python_trust_check
if ($LASTEXITCODE -ne 0) { throw 'Trust check failed' }
& $python -m pytest -q
```

CIもPythonを一時領域へ導入し、ユーザーのbinやレジストリへ登録しません。依存は新しいvenvへ導入し、完成したexeの診断JSONからPython版とfrozen実行を確認します。ビルドに使ったPythonの `LICENSE.txt` は `_internal/licenses/python/` へ同梱します。

uvはCI用のネイティブCLIです。Pythonパッケージとしてuvが未導入でも、CIのuv版確認とは別です。Pygameの実装を別製品へ置き換える変更はしていません。

Issue #155は継続します。既存ローカルvenvや他のPython環境の更新、全チェーン・失効・別環境の確認、署名（#156）は残件です。Ruffの構文対象 `py310` は参照コードの構文互換性を保つ指定であり、3.10のセキュリティサポートを表すものではありません。

## 根拠

- [Pythonの対応状況](https://www.python.org/downloads/)
- [Python 3.13.18](https://www.python.org/downloads/release/python-31318/)
- [Python 3.11.18](https://www.python.org/downloads/release/python-31118/)／[Python 3.12.16](https://www.python.org/downloads/release/python-31216/)
- [Pygameの公開ファイル](https://pypi.org/project/pygame/#files)
- [setup-pythonの版ファイル](https://github.com/actions/setup-python/blob/v5/docs/advanced-usage.md#using-the-python-version-file-input)
- [uvのPython管理](https://docs.astral.sh/uv/guides/install-python/)／[uv 0.13.6の公開ファイル](https://github.com/astral-sh/uv/releases/tag/0.13.6)
