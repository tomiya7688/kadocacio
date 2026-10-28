# Python実行環境の更新

## 背景と今回の対象

Python 3.10はサポートが終了しています。証明書インシデントへの対応を継続するため、Linuxの主検証と分岐カバレッジを修正版Python 3.13.18へ移します。ゲームの演算・データ・依存ライブラリの種類は変更しません。

主検証の版はルートの `.python-version` が正本です。2つのLinuxジョブは `actions/setup-python` の `python-version-file` から読みます。分岐検査はこのファイルの変更時にも実行します。互換ジョブは修正を含む3.11.18と3.12.16を明示し、古いキャッシュが選ばれることを防ぎます。

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

CI設定を変更する開発者は、固定版Prettier 3.6.2で対象ファイルだけを整形してください。Gitルートで `npm exec --yes --package=prettier@3.6.2 -- prettier --write .github/workflows/python-app.yml .github/workflows/branch-coverage.yml .github/workflows/python-compat.yml` を実行し、`--write` を `--check` に変えて再確認してください。既存のPython整形にはRuffを使用します。

## Windows配布の残件

今回、Windows smokeとPyInstallerビルドは従来の3.10のままです。Linuxの更新をWindows配布の移行完了とは扱いません。

Python公式の3.13.18はソースのみで、Windowsインストーラーを提供していません。一方、現在のPygame 2.6.1の公開wheelは3.13までで、3.14以降への変更には依存のビルドや互換性の追加確認が必要です。Windowsでは修正版3.13のビルド、または別の対応版と依存の組合せを検証してから、配布ランタイムと既存venvを更新してください。

Issue #155は継続します。全チェーン・失効・別環境の確認、Windows実行環境の更新、署名（#156）は別の残件です。Ruffの構文対象 `py310` は参照コードの構文互換性を保つ指定であり、3.10のセキュリティサポートを表すものではありません。

## 根拠

- [Pythonの対応状況](https://www.python.org/downloads/)
- [Python 3.13.18](https://www.python.org/downloads/release/python-31318/)
- [Python 3.11.18](https://www.python.org/downloads/release/python-31118/)／[Python 3.12.16](https://www.python.org/downloads/release/python-31216/)
- [Pygameの公開ファイル](https://pypi.org/project/pygame/#files)
- [setup-pythonの版ファイル](https://github.com/actions/setup-python/blob/v5/docs/advanced-usage.md#using-the-python-version-file-input)
