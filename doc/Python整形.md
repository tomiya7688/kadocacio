# Pythonの整形手順

## 背景と対象

既存コードを一括で書き換えると、担当外の変更や試合処理の差を確認しにくくなります。開発者は、今回変更したPythonファイルだけを実装後に整形してください。固定版Ruff 0.16.8をformatterとして使います。既存のflake8・試験・レビューは引き続き必要です。

`ruff.toml`はPython 3.10、127桁、元の改行形式を指定します。生成物・セーブ・チームデータ・vendor・仮想環境は対象外です。ドキュメント内のコード例も変更しません。Godot/GDScript・Markdown・JSONの整形はこの入口の対象ではありません。

## 開発者の操作

プロジェクトのGitルートで、開発用仮想環境を有効にした端末から準備してください。有効化していないWindows端末では、以下の`python`を`.\.venv\Scripts\python.exe`へ置き換えてください。グローバル環境への導入は不要です。

```powershell
python -m pip install -r requirements-dev.txt
python -m ruff --version
```

バージョンが`ruff 0.16.8`であることを確認してください。以下の対象を、今回変更したファイルの一覧へ置き換えて実行してください。複数指定もできます。対象なしや`.`で全体整形しないでください。

```powershell
python -m ruff format --no-cache -- tests/test_python_formatter.py
```

続けて、書換えない確認を実行してください。

```powershell
python -m ruff format --check --no-cache -- tests/test_python_formatter.py
```

整形後、関連テスト・自己レビュー・追加レビューを行ってください。指摘を修正した場合は再整形・再確認してください。checkは整形漏れで終了1になります。その場合は指定ファイルを整形して差分と再checkを確認してください。別バージョンは設定の`required-version`が拒否します。

## CIの確認範囲

既存のPython CIは、PRではbaseから検証対象HEADまで、mainへのpushでは更新前からHEADまでに追加・変更されたPythonだけを確認します。ファイル種別の変更も含め、削除は除き、名前変更は追加・削除として扱います。空白・日本語を含む名前はNUL区切りで渡し、対象ゼロの場合はformatterを起動しません。Pythonのシンボリックリンクや通常ファイルでない対象は拒否します。

手動実行は直前コミットとの差、親のない初回実行は全追跡Pythonが対象になります。既存ファイルを変更する作業では、そのファイルの整形差分も確認してください。未変更の旧コードが整形済みになったという意味ではありません。CIは`--check`のみで、保存されたソースを書き換えません。

既存PRでも、そのPRの差分に含まれる未整形Pythonは新しい確認で失敗します。対象を段階的に整形し、確認が成功するまではレビュー完了やマージ可能と扱わないでください。formatterを通すために既存のlint・試験を省略しないでください。

開発者は`python -m unittest discover -s tests -p test_python_formatter.py -v`で、実CLIの非更新チェック・整形の構文木一致・再実行性・全除外設定と、隔離GitでのCI本文を確認できます。試験は親の`GIT_*`設定を除き、使い捨てrepoだけを操作します。開発試験にはGitとBashが必要です。WindowsではPATH上のGitの近傍から`bin/bash.exe`または`usr/bin/bash.exe`を探し、WSLのbashは使いません。GitHub上の実行結果とシンボリックリンク拒否の実操作は別途確認してください。

設定と動作の正本は[Ruffのformatter](https://docs.astral.sh/ruff/formatter/)と[設定仕様](https://docs.astral.sh/ruff/configuration/)です。パッケージは[PyPIの固定版](https://pypi.org/project/ruff/0.16.8/)で確認できます。
