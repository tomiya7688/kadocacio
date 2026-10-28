# Python実行環境の更新

## 背景と今回の対象

Python 3.10はサポートが終了しています。証明書インシデントへの対応を継続するため、Linuxの主検証・分岐カバレッジとWindowsの配布ビルドを修正版Python 3.13.18へ移します。ゲームの演算・データ・依存ライブラリの種類は変更しません。

主検証の版はルートの `.python-version` が正本です。2つのLinuxジョブは `actions/setup-python` の `python-version-file` から読みます。Windowsジョブは `.github/windows-python.json` の配布版と一致することを確認します。分岐検査とWindows検査は版ファイルの変更時にも実行します。互換ジョブは修正を含む3.11.18と3.12.16を明示し、古いキャッシュが選ばれることを防ぎます。

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

Python公式の3.13.18はソースのみで、Windowsインストーラーを提供していません。Windows CIではAstralのpython-build-standaloneを使用します。配布URLと圧縮アーカイブのSHA-256は `.github/windows-python.json` で固定し、展開・実行前に照合します。CIは格納パスとファイル種別も確認し、通常のGILを使うPython版が `.python-version` と一致することを確認します。

開発者がローカルで検証する場合も、既存venvを削除せず、Eドライブの未使用フォルダーを指定してください。新しいPowerShellウィンドウを開き、Gitルートで次を実行してください。同じ保存先が既にある場合は別名に変え、検証後はそのPowerShellを閉じて環境変数を戻してください。照合するハッシュは圧縮アーカイブの値であり、`python.exe` 単体の値ではありません。

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $runtimeRoot = 'E:/tools/kadocacio-python-validation'
    New-Item -ItemType Directory -Path $runtimeRoot -ErrorAction Stop | Out-Null
    $temporary = Join-Path $runtimeRoot 'tmp'
    New-Item -ItemType Directory -Path $temporary -ErrorAction Stop | Out-Null
    $env:TEMP = $temporary
    $env:TMP = $temporary
    $version = (Get-Content .python-version -Raw).Trim()
    $runtime = Get-Content .github/windows-python.json -Raw | ConvertFrom-Json
    if ($runtime.version -ne $version) { throw 'Python archive version mismatch' }
    $archive = Join-Path $temporary 'python.tar.gz'
    Invoke-WebRequest -Uri $runtime.url -OutFile $archive -ErrorAction Stop
    $actual = (Get-FileHash $archive -Algorithm SHA256 -ErrorAction Stop).Hash.ToLowerInvariant()
    if ($actual -cne $runtime.sha256) { throw 'Python archive checksum mismatch' }
    & "$env:SystemRoot/System32/tar.exe" -xzf $archive -C $runtimeRoot
    if ($LASTEXITCODE -ne 0) { throw 'Python extraction failed' }
    $basePython = Join-Path $runtimeRoot 'python/python.exe'
    & $basePython -m venv (Join-Path $runtimeRoot 'venv')
    if ($LASTEXITCODE -ne 0) { throw 'venv creation failed' }
    $python = Join-Path $runtimeRoot 'venv/Scripts/python.exe'
    & $python -m pip --isolated --cache-dir (Join-Path $runtimeRoot 'pip-cache') install --upgrade --no-deps --require-hashes -r requirements-bootstrap.txt
    if ($LASTEXITCODE -ne 0) { throw 'Bootstrap failed' }
    & $python -m pip --isolated install -r requirements-dev.txt --cache-dir (Join-Path $runtimeRoot 'pip-cache')
    if ($LASTEXITCODE -ne 0) { throw 'Dependency install failed' }
    & $python -m scripts.tools.python_trust_check
    if ($LASTEXITCODE -ne 0) { throw 'Trust check failed' }
    & $python -m pytest -q
    if ($LASTEXITCODE -ne 0) { throw 'Tests failed' }
}
```

開発者は `& {` から最後の `}` までをまとめて実行してください。失敗するとブロック内の後続処理は止まります。ローカル例は固定ハッシュの照合を行う簡略手順で、CIの格納パス・種別検査は含みません。

この例の到達点は実行環境の導入とソースの試験です。配布exeはWindows CIでビルドし、`Kadocacio.exe --check-python-trust` のJSONで `python`・`frozen`・`ok` を確認してください。ビルドに使ったPythonの `LICENSE.txt` は `_internal/licenses/python/` へ同梱します。

CIもPythonを一時領域へ導入し、既存venv、ユーザーのbin、Pythonのレジストリ登録を変更しません。Python版を更新する開発者は、WindowsアーカイブのURL・SHA-256・配布版も更新し、全試験と実exeの確認を再実行してください。

Issue #155は継続します。既存ローカルvenvや他のPython環境の更新、全チェーン・失効・別環境の確認、署名（#156）は残件です。Ruffの構文対象 `py310` は参照コードの構文互換性を保つ指定であり、3.10のセキュリティサポートを表すものではありません。

## 根拠

- [Pythonの対応状況](https://www.python.org/downloads/)
- [Python 3.13.18](https://www.python.org/downloads/release/python-31318/)
- [Python 3.11.18](https://www.python.org/downloads/release/python-31118/)／[Python 3.12.16](https://www.python.org/downloads/release/python-31216/)
- [Pygameの公開ファイル](https://pypi.org/project/pygame/#files)
- [setup-pythonの版ファイル](https://github.com/actions/setup-python/blob/v5/docs/advanced-usage.md#using-the-python-version-file-input)
- [固定したWindows配布元](https://github.com/astral-sh/python-build-standalone/releases/tag/20261026)
