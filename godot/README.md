# Godot移行基盤

#120 の起動/検証入口。**まだ試合をプレイできません**。通常入口 `run_game.bat` と Python/Pygame は変更していません。

## エンジンと起動

Godot **4.7.2 stable（標準版、非.NET）** を固定。正本は `engine_version.txt`。公式配布: <https://godotengine.org/download/windows/>。CIも同じ版を公式リリースから取得し、SHA-256を照合します。エンジン本体はGitへ入れません。

開発用ラッパーは既存 `.venv` のPythonを使用し、エンジン実行ファイルを `--engine` → 環境変数 `GODOT_BIN` → PATH (`godot_console`, `godot`, `godot4`) の順に解決します。明示したパスが無効なら停止し、別版へ勝手に切り替えません。版不一致・起動失敗・タイムアウトは終了コード2、検査失敗は非0。正常時0。標準出力に書かれたGodotのエラーも検査失敗として扱います。

PowerShell例（パスは手元の配置へ変更）:

```powershell
$env:GODOT_BIN = 'C:\tools\godot\Godot_v4.7.2-stable_win64_console.exe'
.\run_godot.bat
.\run_godot.bat check
.\run_godot.bat test
.\run_godot.bat smoke
.\run_godot.bat smoke --headless
```

- `run`: 動作確認画面。閉じるボタン・Enter・ウィンドウの×で終了。通常プレイではない。
- `check`: headless import と全 `.gd` の実エンジン構文/型検査。型安全警告もエラー化。
- `test`: 上記に加えてSceneTreeの検証、壊れた構文/型fixtureが拒否されること、headlessの起動/終了マーカーを確認。
- `smoke`: 通常描画で起動し、同じ閉じる処理を自動呼出して終了。音声デバイス不要の `Dummy` ドライバーを明示。`--headless`で描画なし。通常 `run` の音声設定は変更しない。
- 検査ごとのタイムアウトは `--timeout 60`（0より大きく300秒以下）。通常 `run` は時間制限なし。

Pythonを使わず直接起動することも可能: `& $env:GODOT_BIN --path godot`。配布入口の切替・exportは #143。

## 役割と移行対応

| 参照Python | Godot側 | 境界 |
|---|---|---|
| `main.py` / `scripts/app/game_app.py` | `project.godot` / `scenes/app/` / `scripts/app/bootstrap.gd` | 今回は起動/終了のみ。既存メニューは #122 |
| `scripts/core/` | `scripts/core/` | Node無しの共通契約。固定ステップ等は未移行 |
| `scripts/team/team_data.py` | `scripts/data/` | JSON互換は次の #121。ユーザーJSON/セーブへ書込まない |
| `scripts/match/` | `scripts/match/` | Node無しの同一演算核。まだ演算・3D試合表示なし |
| `tests/` | `tests/run_tests.gd` | Godot実行で検査。Python側テストはラッパーの失敗分岐を検査 |

`godot/.godot/` は生成キャッシュで非公開。`.gd.uid`はGodotの参照IDとして管理する。異常fixtureは `.gd.txt` で格納し、通常importへ混入させない。負の試験時だけ `user_data/logs/godot/` の一時 `.gd` にコピーして実行し、終了時に片付ける。

今回のウィンドウsmokeは起動/終了の自動検証。人間による操作、3D試合、JSON読込、セーブ互換、移行後の性能は未検証。順序/互換契約は `doc/Godot移行.md`、Issue #119〜#143を参照する。
