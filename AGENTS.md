# カドカルチョ AI開発チートシート

このファイルはAIエージェント向けの最短作業地図。ユーザーの最新指示が常に優先される。
README/SPECを最初から全読せず、まずこの地図と`rg`で対象だけを読むこと。

## 30秒セットアップ

- 正式プロジェクト: `C:\Users\tomiy\games\kadoka_calciobit`
- Python: `.venv\Scripts\python.exe`
- 起動: `run_game.bat` または `.venv\Scripts\python.exe main.py`
- ルートのPythonは`main.py`だけに保ち、実装は必ず`scripts/`の役割別パッケージへ置く。
- importは`from scripts.<role>...`の絶対importを使う。
- データパスを`__file__`から再計算せず、`scripts/core/paths.py`を使う。
- Git状態は作業開始時に確認する。全ファイルが未追跡に見える履歴があるため、`git diff`だけで変更範囲を判断しない。

## 変更してはいけない基本契約

- Pygame製。試合表示は遠近投影の3D表現で、2Dトップビューへ戻さない。
- ジャンプはAIの自動判断。Jキー等の手動ジャンプを追加しない。
- 試合時計は実時間1秒で試合内10秒、90分で終了。
- 倍速順は`1, 2, 3, 5, 10, 100`。
- 物理・AIの固定ステップは最大`0.05`秒。高速処理でも時計だけを飛ばさない。
- 描画あり、ヘッドレス、リーグ、チューナーは同じ`Match`判定を使う。簡易結果式へ置換しない。
- セットプレー準備中はその試合の試合時計だけ止める。他会場までは止めない。
- 試合演算へ新しい直接`pygame`依存を増やさない。座標型は`scripts/core/simulation_geometry.py`を交換点として使う。

## 能力値とJSON

- 現行能力値は`0..5500`。内部では`0..1`へ正規化する。
- 範囲、旧`50..1250`変換、ランクは`scripts/core/stat_scale.py`だけを正とする。
- ランク: `S 5000 / A+ 4500 / A- 4000 / B+ 3500 / B- 3000 / C+ 2500 / C- 2000 / D+ 1500 / D 1000 / E+ 500 / E- 0`。
- メタデータなしのチームJSONは旧スケールとして読む。既存互換を壊さない。
- `戦術への忠実さ`は能力値ではなく`0..100`。高いほど指示に忠実、低いほど柔軟。
- チームJSONの正式編集キーは日本語。旧英語キーも読める。
- 先発は7〜11人、GKは1人以上。FW/MF/DFは0人でも有効。
- チーム追加・変更時は`teams/**/*.json`と`teameditor_templete/*.json`の両方を確認する。

## コード地図

| 変更対象 | 主な場所 | 先に走らせるテスト |
|---|---|---|
| 起動、入力、画面遷移、ポーズ | `scripts/app/game_app.py` | `test_pause_menu.py`, `test_tournaments_and_ime.py` |
| 3D投影、選手・コート・UI描画 | `scripts/app/rendering.py` | 起動スモーク＋関連画面テスト |
| CPU上限・GPU/CPU表示 | `scripts/core/performance_settings.py`, `scripts/app/performance_backend.py` | `test_performance_settings.py`, ダミーSDL起動 |
| 共通定数、時計、コート | `scripts/core/settings.py` | `test_restart_clock.py` |
| 固定ステップ、ヘッドレス | `scripts/core/simulation_runtime.py`, `simulation_driver.py` | `test_simulation_runtime.py`, `test_simulation_driver.py` |
| 試合進行、パス、シュート、GK、反則 | `scripts/match/match_engine.py` | `test_pass_logic.py`, `test_goal_urgency.py`, `test_ai_tactical_lookahead.py` |
| 選手・チーム・ボール状態 | `scripts/match/entities.py` | `test_effective_stat_cache.py` |
| AI効用・判断差 | `scripts/match/intelligence_system.py` | `test_intelligence_scaling.py`, `test_ai_planning.py` |
| コマンド | `scripts/match/player_commands.py` | AI/パス系テスト |
| スタミナ、技術、ジャンプ、フィジカル | 各`scripts/match/*_system.py` | 同名・近接機能のテスト |
| 監督 | `scripts/match/manager_system.py`＋`match_engine.py` | `test_manager_system.py` |
| チーム読込・旧キー互換 | `scripts/team/team_data.py` | `test_stat_scale.py`, `test_flexible_formations.py` |
| チームエディタ | `scripts/team/team_editor.py`, `team_editor_data.py` | `test_team_file_organization.py`, `test_team_editor_tuner_scope.py` |
| チューナー | `scripts/team/team_tuner.py` | `test_team_tuner_means.py`, `test_team_tuner_optimizer.py` |
| リーグ・同時試合・保存 | `scripts/league/league_manager.py` | `test_league_manager.py`, `test_restart_clock.py` |
| リーグ一覧UI | `scripts/league/*_view.py`, `league_rendering.py` | `test_league_live_view.py`, `test_league_schedule_view.py`, `test_league_team_browser.py` |
| AI評価・負荷試験 | `scripts/tools/ai_evaluator.py`, `league_stress_test.py` | CLIヘルプ＋必要な実測 |

## データ地図

- `teams/`: 再帰的に読むチームJSON。フォルダ構成も機能の一部。
- `teameditor_templete/`: エディタ選択肢、能力カテゴリ、ランク、フォーメーション。
- `leagues.json`: リーグ・トーナメント定義とチーム配置。
- `performance_settings.json`: CPU演算枠の上限とGPU描画の有効設定。
- `league_save/`: 実行時セーブ。明示依頼なしにサンプル扱いで書き換えない。
- `assets/`: スタジアム、観客等。
- `ai_evaluation/`, `performance_logs/`: 実測出力。通常の実装変更へ混ぜない。
- `teams/カルチョビット/`: 参考データで公開対象外。削除・公開・一括変換は明示指示時のみ。

## 検証コマンド

Windows `cmd.exe`想定。PowerShellがエラー1920になる環境では無理に使わない。

```bat
set SDL_VIDEODRIVER=dummy& set SDL_AUDIODRIVER=dummy& set KADOKA_DISABLE_GPU=1& .venv\Scripts\python.exe -m unittest discover -s tests -v
.venv\Scripts\python.exe -m compileall -q main.py scripts tests
.venv\Scripts\python.exe -m scripts.tools.migrate_stat_scale --dry-run
.venv\Scripts\python.exe -m scripts.tools.ai_evaluator --help
```

- 小変更は対応表のテストを先に実行し、完了前に全テストを実行する。
- 2026-08-23時点の基準は全137テスト成功。件数より終了コードを信頼する。
- 高速化では、同じ乱数シード・固定ステップで結果傾向が維持されることも確認する。

## 作業ルール

- 調査は`rg`/`rg --files`から始め、巨大なREADMEや`match_engine.py`を丸ごと読まない。
- 一つの挙動に複数の実装を作らず、既存コマンド・能力・固定ステップへ接続する。
- マルチプロセスへ渡す関数とデータはpickle可能に保ち、ワーカー入口はモジュール直下に置く。
- JSONを機械変換する場合は再実行可能なツールにし、`--dry-run`と範囲検証を用意する。
- READMEは人間向け概要、SPECは深い仕様確認用。対象見出しだけ`rg -n`して読む。
- 最終報告には変更ファイル、互換性への影響、実行したテスト、未検証事項を短く記載する。
