# カドカルチョ 変更履歴

新しいバージョンを上へ追記します。バージョン番号、概要、追加ファイル、変更ファイルを省略せず記録します。対象がない区分には「なし」と記載します。

## 記入形式

ver num.num.num

一言で表す

追加したファイル

- ファイル名

  一言で表す

変更したファイル

- ファイル名

  一言で表す

---

ver 0.7.1

実試合結果でKリーグを自動再配置

追加したファイル

- `scripts/tools/reseed_k_league_teams.py`

  評価チェックポイントの昇降格後所属を検証し、チームJSONとリーグテンプレートを非破壊手順で再配置します。

- `tests/test_k_league_reseed.py`

  昇降格計画、ファイル移動、テンプレート更新、バックアップ、不完全評価と不一致・衝突の拒否を検証します。

変更したファイル

- `.gitignore`

  復旧用の`development_reseed_backup`を実行時データとして除外しました。

- `README.md`, `doc/Kリーグチーム生成機.md`

  実試合評価からプレビュー、適用、復旧までの手順を追加しました。

- `doc/開発予定.md`

  完了したKリーグチーム生成機の項目を削除しました。

- `AGENTS.md`

  再配置ツール、バックアップ場所、対応テスト、全テスト基準を追加しました。

- `doc/versions.md`

  ver 0.7.1の変更内容を追記しました。

---

ver 0.7.0

K1～K9の180チーム生成基盤

追加したファイル

- `scripts/tools/generate_k_league_teams.py`

  既存A・Bを保護しながら、可変リーグ数・可変チーム数でKリーグ用JSONとリーグテンプレートを生成します。

- `teameditor_templete/k_league_generation.json`

  リーグ能力差、フォルダ、表示色、チーム傾向、名前部品を編集可能な設定として分離しました。

- `tests/test_k_league_team_generator.py`

  180チーム計画、名前重複、既存チーム非変更、JSON妥当性、リーグ能力差、テンプレート配置を検証します。

- `doc/Kリーグチーム生成機.md`

  安全なプレビュー・書出し、可変指定、外部名前JSON、今後の評価連携を説明します。

変更したファイル

- `README.md`, `doc/開発予定.md`

  K1～K9生成機の概要、詳細文書への入口、残っている評価ベース再配置を記録しました。

- `AGENTS.md`

  実装場所、対応テスト、全テスト基準を更新しました。

- `doc/versions.md`

  ver 0.7.0の変更内容を追記しました。

---

ver 0.6.1

停止しないセットプレーと安全な評価結果

追加したファイル

- なし

  既存の試合エンジン、リーグ処理、評価ツールを修正しました。

変更したファイル

- `scripts/match/match_engine.py`

  タッチライン付近でもキッカーの待機位置を移動可能なコート内へ制限し、フリーキック停止を解消しました。

- `scripts/league/league_simulation_workers.py`

  ヘッドレス試合の実際の終了状態と、試合時間、停止中セットプレー、終了理由を返すようにしました。

- `scripts/league/league_manager.py`

  90分を完走していない途中スコアを順位表へ反映しないようにしました。

- `scripts/tools/league_evaluation_runner.py`

  未完走試合を上限2倍で一度再試行し、再失敗時は試合日を未処理のまま診断ログを保存します。

- `tests/test_restart_clock.py`, `tests/test_league_manager.py`, `tests/test_developer_league_evaluator.py`

  コート境界の待機位置、途中結果の拒否、評価の再試行と安全停止を検証します。

- `README.md`, `SPEC.md`, `AGENTS.md`, `doc/開発者用リーグ評価.md`, `doc/versions.md`

  新しい完走保証、診断、テスト基準を記録しました。

---

ver 0.6.0

5パーツのドットユニフォーム

追加したファイル

- `scripts/team/uniform_data.py`

  ユニフォームの標準生成、正規化、検証、色解決、読込・書出しを実装しました。

- `scripts/team/uniform_editor.py`

  胸、左右の腕、左右の脚を編集するチームエディタ用UIを追加しました。

- `scripts/app/uniform_rendering.py`

  投影済みの選手パーツへドット模様を描画します。

- `tests/test_uniforms.py`

  データ形式、色解決、ファイル交換、リーグスナップショット保持を検証します。

- `doc/ユニフォーム機能.md`

  データ形式と処理分離を説明します。

変更したファイル

- `scripts/team/team_editor.py`, `scripts/team/team_editor_config.py`, `teameditor_templete/editor_options.json`

  ユニフォームタブと編集色パレットを統合しました。

- `scripts/team/team_editor_data.py`, `scripts/team/team_data.py`

  チームJSONの検証、修復、リーグ開始時スナップショットへユニフォームを追加しました。

- `scripts/match/team.py`, `scripts/match/match_engine.py`

  試合色に合わせてユニフォームの色トークンを解決します。

- `scripts/app/rendering.py`

  立ち姿と各モーションの胸、腕、脚へユニフォーム模様を反映しました。

- `scripts/core/paths.py`

  ユニフォーム交換フォルダの共通パスを追加しました。

- `tests/test_rendering_smoke.py`

  ユニフォームエディタと試合描画のスモークテストを追加しました。

- `README.md`, `SPEC.md`, `AGENTS.md`, `doc/クラス一覧.md`, `doc/開発予定.md`, `doc/versions.md`

  操作方法、仕様、開発地図、変更履歴を更新しました。

---

ver 0.5.1

UTF-8のまま確実に起動する評価ランチャー

追加したファイル

- なし

  既存の評価ランチャーとテストを修正しました。

変更したファイル

- `run_developer_evaluation.bat`

  コードページ設定前に日本語を解釈させず、Python入出力をUTF-8へ固定するASCII命令だけのランチャーへ変更しました。

- `tests/test_developer_league_evaluator.py`

  ランチャーがUTF-8として読め、cmd.exe安全な文字だけを使うことを検証します。

- `doc/開発者用リーグ評価.md`

  文字コード設計と引数を使った短時間の起動確認方法を追記しました。

- `AGENTS.md`

  全テスト基準を170件へ更新しました。

- `doc/versions.md`

  ver 0.5.1の変更内容を追記しました。

---

ver 0.5.0

平均を守るランク式チーム生成

追加したファイル

- `scripts/team/team_template_profile.py`

  ランクから基準値への変換と、全体平均を維持する分野別チーム補正を追加しました。

- `tests/test_team_template_profiles.py`

  ランク変換、補正後の平均、フィジカル型の能力差、UI切替を検証します。

- `doc/チーム生成基準値テンプレート.md`

  数値・ランク入力、能力予算の再配分、JSON拡張方法を説明します。

変更したファイル

- `scripts/team/team_editor.py`

  基準値の数値／ランク切替とチーム補正プリセット選択を追加しました。

- `scripts/team/team_editor_data.py`

  分野別の目標値で選手を生成し、最終的な全能力平均を基準値へ合わせます。

- `scripts/team/team_editor_config.py`

  古い設定ファイル向けにバランス補正のフォールバックを追加しました。

- `teameditor_templete/editor_options.json`

  10能力分野と8種類の編集可能なチーム補正を追加しました。

- `tests/test_rendering_smoke.py`

  基準値入力切替、補正選択、生成ボタンが同じ画面へ表示されることを検証します。

- `README.md`

  新しい基準値テンプレートの操作と平均維持仕様を追記しました。

- `doc/開発予定.md`

  完了した基準値テンプレート強化項目を削除しました。

- `AGENTS.md`

  チーム生成機能の実装場所と検証先を開発地図へ追加し、全テスト基準を169件へ更新しました。

- `doc/versions.md`

  ver 0.5.0の変更内容を追記しました。

---

ver 0.4.0

放置運転できるリーグ総合評価

追加したファイル

- `scripts/tools/developer_league_evaluator.py`

  長時間リーグ評価のコマンド、引数、再開処理を追加しました。

- `scripts/tools/league_evaluation_runner.py`

  実試合の年度進行、並列実行、ログ、チェックポイントを統括します。

- `scripts/tools/league_evaluation_report.py`

  JSONLの追記、集計、JSONとCSVの出力を担当します。

- `tests/test_developer_league_evaluator.py`

  既定設定、試合日進行、全ログ形式、集計を検証します。

- `run_developer_evaluation.bat`

  ダブルクリックで8時間の評価を開始します。

- `doc/開発者用リーグ評価.md`

  放置評価の起動、再開、ログの読み方を説明します。

変更したファイル

- `scripts/league/league_simulation_workers.py`

  評価ジョブでだけAIテレメトリ、残スタミナ、実行時間を収集できるようにしました。

- `scripts/core/paths.py`

  放置評価ログの共通保存先を追加しました。

- `.gitignore`

  実行時に生成される評価ログをGit管理対象から除外しました。

- `README.md`

  長時間リーグ評価の入口を追加しました。

- `AGENTS.md`

  評価ツールとログ保存場所を開発地図へ追加し、全テスト基準を166件へ更新しました。

- `doc/クラス一覧.md`

  リーグ評価実行クラスの役割を追加しました。

- `doc/versions.md`

  ver 0.4.0の変更内容を追記しました。

---

ver 0.3.0

全年度の順位・チーム戦績を永続保存

追加したファイル

- なし

  既存のリーグ保存・成績画面を拡張しました。

変更したファイル

- `scripts/league/league_manager.py`

  50年の保存上限を廃止し、全試合のチームID付き履歴とチーム別検索を追加しました。

- `scripts/league/league_rendering.py`

  過去の成績にチーム戦績画面を追加し、年度別順位と試合結果を表示します。

- `scripts/app/game_app.py`

  成績表示モード、チーム選択、年度・試合結果ページ操作を追加しました。

- `tests/test_league_manager.py`

  50年超の保存、年度別順位、チーム別結果、旧セーブ互換を検証します。

- `tests/test_rendering_smoke.py`

  チーム戦績画面の描画と操作項目を検証します。

- `SPEC.md`

  全年度履歴の保存契約と成績画面の仕様を明記しました。

- `AGENTS.md`

  全テスト成功の基準件数を162件へ更新しました。

- `doc/versions.md`

  ver 0.3.0の変更内容を追記しました。

---

ver 0.2.0

クラス責務とファイル配置の整理

追加したファイル

- `scripts/core/performance_settings_model.py`

  パフォーマンス設定値クラスを独立させました。

- `scripts/core/cpu_usage_limiter.py`

  CPU使用率制御クラスを独立させました。

- `scripts/core/simulation_limits.py`

  ヘッドレス試合の制限値クラスを独立させました。

- `scripts/core/team_telemetry.py`

  チーム統計クラスを独立させました。

- `scripts/core/match_telemetry.py`

  試合観測クラスを独立させました。

- `scripts/core/simulation_result.py`

  シミュレーション結果クラスを独立させました。

- `scripts/core/step_match.py`

  固定ステップ試合インターフェースを独立させました。

- `scripts/core/realtime_simulation_driver.py`

  描画あり試合の実時間実行クラスを独立させました。

- `scripts/match/player.py`

  選手状態クラスを独立させました。

- `scripts/match/team.py`

  チーム状態クラスを独立させました。

- `scripts/match/ball.py`

  ボール状態クラスを独立させました。

- `scripts/match/player_command.py`

  選手コマンド列挙を独立させました。

- `scripts/match/command_spec.py`

  コマンド仕様値クラスを独立させました。

- `scripts/match/pending_kick.py`

  保留中キック情報クラスを独立させました。

- `scripts/match/pass_route.py`

  パス経路評価クラスを独立させました。

- `scripts/league/league_simulation_session.py`

  リーグ裏試合の実行セッションを日程管理から分離しました。

- `scripts/league/league_simulation_workers.py`

  マルチプロセスへ渡す試合実行関数を独立させました。

- `scripts/league/league_worker_budget.py`

  裏試合のCPU数とメモリ予算の計算を独立させました。

- `scripts/league/windows_memory_status.py`

  Windowsメモリ取得構造を独立させました。

- `tests/test_class_layout.py`

  一ファイル一クラスとクラス一覧の同期を検査します。

- `doc/クラス一覧.md`

  全クラスと単一の役割を一覧化しました。

変更したファイル

- `scripts/core/performance_settings.py`

  設定の正規化と保存処理だけを担う互換窓口に整理しました。

- `scripts/core/simulation_runtime.py`

  固定ステップ実行処理と分離済みデータ型の公開窓口に整理しました。

- `scripts/core/simulation_driver.py`

  旧importを維持する互換窓口に変更しました。

- `scripts/match/entities.py`

  選手、チーム、ボールの旧importを維持する互換窓口に変更しました。

- `scripts/match/player_commands.py`

  コマンド値と仕様値を分離し、対応表と速度計算へ責務を絞りました。

- `scripts/match/match_engine.py`

  試合データ型を個別モジュールから参照するように変更しました。

- `scripts/match/prediction_system.py`

  選手とチームを個別モジュールから参照するように変更しました。

- `scripts/league/league_manager.py`

  裏試合セッション、ワーカー処理、資源予算、Windowsメモリ構造を分離しました。

- `scripts/app/game_app.py`

  実時間実行器とリーグセッションを個別モジュールから参照するように変更しました。

- `scripts/app/rendering.py`

  選手クラスを個別モジュールから参照するように変更しました。

- `scripts/team/team_tuner.py`

  CPU制御クラスを個別モジュールから参照するように変更しました。

- `scripts/tools/ai_evaluator.py`

  観測値と制限値を個別モジュールから参照するように変更しました。

- `tests/test_league_manager.py`

  資源予算の分離後の参照先を検証するように変更しました。

- `tests/test_league_simulation_session.py`

  分離したワーカー関数とセッションを直接検証するように変更しました。

- `AGENTS.md`

  クラス、責務、関数分割と速度維持の開発原則を追加しました。

- `doc/versions.md`

  ver 0.2.0の変更内容を追記しました。

---

ver 0.1.0

プロジェクト整合性確認と変更履歴の開始

追加したファイル

- `doc/versions.md`

  バージョンごとの変更を一定の形式で残す変更履歴を追加しました。

変更したファイル

- `AGENTS.md`

  今後の実装・データ変更時に変更履歴を更新する作業規約を追加しました。
