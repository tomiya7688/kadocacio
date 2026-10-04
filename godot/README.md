# Godot移行基盤

#120 の起動/検証入口、#121 のチームJSON読込、#122 のメニュー・設定・チーム/会場選択、#123 の操作/観測/差分境界、#124 の試合状態・時計・固定更新・乱数基盤、#125 の自由ボール物理/境界/接触候補。**まだ試合をプレイできません**。通常入口 `run_game.bat` と Python/Pygame は変更していません。

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
.\run_godot.bat ui-test
```

- `run`: 4つの入口と設定画面。Tab/Enter・マウスで選択、Escで設定の開閉、F11で全画面。閉じるボタン・ウィンドウの×で終了。通常プレイではない。
- `check`: headless import と全 `.gd` の実エンジン構文/型検査。型安全警告もエラー化。
- `test`: 上記に加えてヘッドレスUI操作、公開チーム・合成ケース・試合初期状態/時計/乱数・自由ボール物理/境界/接触候補のPython/Godot照合、固定更新検査、壊れた構文/型fixtureの拒否、headlessの起動/終了マーカーを確認。
- `ui-test`: 実ウィンドウでUI操作と960×540・非16:9・全画面の入力/配置を検査し、`user_data/logs/godot/ui_tests-windowed/`へ検査画像を保存。`--headless`では描画/全画面を除いた操作検査のみ。CIはWindowsとLinux仮想ディスプレイで実行する。
- `smoke`: 通常描画で起動し、同じ閉じる処理を自動呼出して終了。音声デバイス不要の `Dummy` ドライバーを明示。`--headless`で描画なし。通常 `run` の音声設定は変更しない。
- 検査ごとのタイムアウトは `--timeout 60`（0より大きく300秒以下）。通常 `run` は時間制限なし。

Pythonを使わず直接起動することも可能: `& $env:GODOT_BIN --path godot`。配布入口の切替・exportは #143。

## 役割と移行対応

| 参照Python | Godot側 | 境界 |
|---|---|---|
| `main.py` / `scripts/app/game_app.py` / `main_menu_view.py` | `project.godot` / `scenes/app/` / `scripts/app/bootstrap.gd` / `main_menu_view.gd` | 起動/終了と4ルート。未実装の本体は明示して停止 |
| `scripts/app/team_select_view.py` | `match_test_view.gd` / `team_picker.gd` | フォルダを含む検索、紹介閲覧、HOME/AWAY/中立会場。試合開始は未接続 |
| `scripts/app/settings_view.py` / `scripts/core/performance_settings.py` | `settings_overlay.gd` / `ui_preferences.gd` / `data/ui_contract.json` | 画面サイズ・全画面は実適用。CPU・モード・GPU希望は保存のみ |
| `scripts/core/paths.py` | `scripts/data/migration_paths.gd` / `ui_preferences_repository.gd` | 開発時データ位置とGodot専用設定保存。配布配置は #143 |
| `scripts/core/stat_scale.py` | `scripts/core/stat_scale.gd` / `data/team_contract.json` | Pythonから導出する範囲・既定値・ランク |
| `scripts/team/team_data.py` / `team_identity.py` | `scripts/data/team_json_repository.gd` / `team_payload_validator.gd` / `team_payload_decoder.gd` | 読込・診断・変換を分離。ユーザーJSON/セーブへ書込まない |
| `scripts/team/uniform_data.py` | `scripts/data/uniform_decoder.gd` | 画素パーツの正規化。元の未知項目は原本コピーで保持 |
| `scripts/match/player.py` / `player_style_system.py` / `skill_system.py` | `scripts/data/player_definition.gd` / `manager_definition.gd` | 能力・監督・タイプ・スキルの入力のみ。行動AIとスキル効果は未移行 |
| `player.py` / `team.py` / `ball.py` / `Match` の初期配置 | `player_state.gd` / `team_state.gd` / `ball_state.gd` / `match_setup.gd` | 型付きの試合内状態と初期配置。物理/AIの本体は未移行 |
| 固定更新・時計 / `random.Random` | `fixed_step_driver.gd` / `match_clock.gd` / `python_random_stream.gd` | 0.05秒tick、独立時計、整数seed互換の乱数サブセット |
| `Match.update_loose_ball` / ボール所有・こぼれ球 | `ball_flight_system.gd` / `ball_boundary_system.gd` / `ball_contact_query.gd` / `ball_possession_system.gd` / `ball_simulation_system.gd` | 弾道/境界/接触候補とボール状態変更。接触の成否・AI・再開は未移行 |
| `match_session.py` / `match_observation.py` / `match_trace_comparison.py` | `match_kernel.gd` / `match_snapshot.gd` / `match_trace_comparison.gd` | 共通操作・独立観測・差分。通常プレイは未接続処理があれば拒否 |
| `tests/` / `scripts/tools/godot_team_oracle.py` | `tests/run_tests.gd` / `tests/team_data_tests.gd` | 実Godotで検査。Python側テストは参照fixture生成とラッパーの失敗分岐を検査 |

`godot/.godot/` は生成キャッシュで非公開。`.gd.uid`はGodotの参照IDとして管理する。異常fixtureは `.gd.txt` で格納し、通常importへ混入させない。負の試験時だけ `user_data/logs/godot/` の一時 `.gd` にコピーして実行し、終了時に片付ける。

## チーム読込API（Node無し・読み取り専用）

`TeamJsonRepository.new().load_file(絶対パス, teamsフォルダ)` または `load_payload(Dictionary, 相対source)` は `TeamLoadResult` を返します。成功時 `team`、失敗時 `diagnostics`（code/source/field/message/line）を持ちます。失敗したチームの部分定義は返しません。呼び出し元は診断を画面/ログへ表示してください。相対sourceをID互換に使用し、読み込み時に新IDを生成しません。

`discover(PackedStringArray([ユーザーチームフォルダ, 同梱チームフォルダ]))` は `TeamCatalog` を返します。再帰フォルダ、先に指定したルートによるID/同名sourceの上書き、同一ルートのID重複診断を扱います。不正ファイルを診断に残し、正常チームは利用できます。リンクの再帰は行いません。root外の字句パスを拒否しますが、任意の第三者ファイルに対するセキュリティ用sandboxではありません。

`TeamDefinition` はチーム情報と `Array[PlayerDefinition]` の先発/控えを分離。`to_choice()` はPython選択データと同じ形の独立コピー、`PlayerDefinition.to_parameters()` は正規化能力/タイプ/スキル/忠実さを返します。全体の未知項目・未認識スキルを含む元JSONは `original_payload` に、選手の元項目と互換キーは `raw` に保持します。これらのモデルは編集可能ですが、まだ保存へは接続していません。試合核は独立した定義コピーを使います。

日本語キーを旧英語キーより優先。メタデータのない旧50..1250能力は0..5500へ変換し、Pythonと同じ偶数丸めを使用します。忠実さ0..100は能力換算しません。7～11人/1人以上GKの範囲ならFW/MF/DFは0人で構いません。

## Python参照契約と互換検査

範囲/ランク/キー別名/タイプ/スキル/ユニフォーム定義の正本は既存Python。Godot実行はPythonに依存せず、導出済み `data/team_contract.json` を読みます。正本変更時のみ明示再生成してください:

```powershell
.venv\Scripts\python.exe -m scripts.tools.godot_team_contract --write
.venv\Scripts\python.exe -m scripts.tools.godot_team_contract
.\run_godot.bat test
```

開発検査には `requirements.txt` の参照用依存が必要です。契約が古ければテストは停止し、黙って書き換えません。Git管理中の公開チームのみを照合し、`teams/カルチョビット/` と未追跡の個人チームは対象外。参照fixtureは `user_data/logs/godot/team_parity/` に生成し、終了・失敗・タイムアウト後にも元チームのSHA-256を照合します。数値比較の絶対許容差は1e-9。通常JSONの整数能力と原本項目も比較します。

#121の実機検査対象は公開41チームと合成107ケース（旧/新/小数境界スケール、能力既定値、別名優先、全スキル、長文紹介、ユニフォーム、自由フォーメーション、不正入力）、再帰/BOM/壊れたJSON/重複IDの診断。JSON数値はGodotの倍精度範囲を使用し、Pythonの任意精度整数までは保証しません。

ウィンドウsmokeは起動/終了の自動検証。人間による操作、3D試合、旧セーブ互換、移行後の性能は未検証。順序/互換契約は `doc/Godot移行.md`、Issue #119〜#143を参照する。

## メニュー・設定の適用範囲（#122）

リーグ開始/リーグエディタ/チームエディタ/試合テストは別々のControlシーン。前3つは本体の移行待ちを明示した画面で、戻るだけが可能です。試合テストは有効なJSONのチーム選択と紹介・読込診断（件数とツールチップ）、会場を表示し、まだ試合は開始しません。長い名前は一覧で省略しツールチップとスクロール可能な詳細で全文を読めます。長文紹介はリッチテキストのマークアップとして解釈しません。

設定を開く間は背面を非表示にして入力を遮断し、閉じたら直前のフォーカスへ戻します。16:9の1280×720論理画面を維持し、他比率では余白を使います。960×540/1280×720/1600×900/1920×1080、F11/全画面切替を実際のWindowへ適用します。

Godot専用の `user_data/config/godot_ui_settings.json` へ「保存して閉じる」またはEsc時に書き込みます。壊れた設定は既定値で起動し、自動上書きしません。ユーザーが設定を閉じて明示保存する際には上書きします。書込み失敗時は設定画面に留まり、再試行できます。Python設定・チーム・リーグセーブへは書き込みません。開発/試験の隔離には `KADOCALCIO_DATA_ROOT` でデータルートを指定できます。

CPU演算枠はOS全体への使用率制限ではありません。試合核は未移行なのでCPU上限と裏試合4モードは希望値保存のみ。Godot画面描画はGPUを使いますが、GPU希望のチェックでCPU描画へ切り替える処理やGPU試合演算はまだありません。これらの未適用範囲は画面内にも表示しています。UIの選択肢はPython正本から導出し、古い契約はテストを止めます:

```powershell
.venv\Scripts\python.exe -m scripts.tools.godot_ui_contract --write
.venv\Scripts\python.exe -m scripts.tools.godot_ui_contract
```

入力は独自の文字蓄積ではなくGodotのLineEdit/SpinBoxを使用します。IME合成中のEsc/F11を奪わないよう、[LineEditのhas_ime_text](https://docs.godotengine.org/en/stable/classes/class_lineedit.html#class-lineedit-method-has-ime-text)で判別します。確定日本語の挿入・カーソル・キーリピート削除、Tab/Enter/Escとクリック、設定保存は自動操作で検証します。OSの実IME変換候補ウィンドウ・未確定文字の操作は手動確認が必要で、これらの自動試験だけでIME全体の動作確認とはしません。

## 試合境界と差分検証（#123）

契約/API/精度/乱数の正本は [`doc/試合境界契約.md`](../doc/試合境界契約.md)。`MatchInputRecord` / `MatchTraceRecord` は検証済みの独立コピーを返し、`MatchTraceComparison` は最初の操作順・実更新step・状態/イベント/結果の差分を計算します。UIへ可変なMatch内部を渡すための仕組みではありません。

```powershell
.venv\Scripts\python.exe -m scripts.tools.godot_match_contract --write
.venv\Scripts\python.exe -m scripts.tools.godot_match_contract
.\run_godot.bat test
```

公開2チームの短いPython実試合を `user_data/logs/godot/match_contract/fixture.json` に生成し、実Godotの読み取り/再出力と差分期待値を照合します。旧repro入力・結果・イベントAPIを変更せず、teams原本を成功/失敗時にも照合します。不正入力/不正観測・時計/得点/所有者/再開/選手コマンド/位置許容差/イベントの差分を検査します。

この読込検査のGodot出力は `execution: contract_roundtrip`、差分レポートは `kernel_parity: not_evaluated`。今回の検査を試合結果・旧セーブ・90試合性能の互換試験として報告しないでください。

## 試合状態・固定更新・乱数基盤（#124）

API/対応表/検証境界は [`doc/Godot試合核.md`](../doc/Godot試合核.md)。`MatchKernel` の型付き状態・初期配置・独立時計と、`FixedStepDriver` の0.05秒tick/全倍速、CPython整数seed互換の `PythonRandomStream` を追加しています。通常プレイは必要な選手・判断・ボール更新が未接続なら、時計更新前に拒否します。仮の試合結果は返しません。

`run_godot.bat test` は公開2チームのPython実Matchの初期状態・キックオフ50tick、8seedの乱数API/用途/消費順、6時計ケースを実Godotと照合します。さらにテスト専用更新で30/60/120Hz・全倍速・停止・再開・準備待ち・未処理時間・90分の時計を検査。ログは `user_data/logs/godot/match_kernel/`。この短い実行出力は `execution: simulation` ですが、`kernel_parity: not_evaluated` は維持します。選手物理/AI/接触成否/得点確定・3D試合表示・旧セーブ・90試合性能は後続Issueで検証します。

## 自由ボール物理・境界・接触候補（#125）

対応表/接続/参照fixtureの隔離範囲は [`doc/Godotボール物理.md`](../doc/Godotボール物理.md)。`BallSimulationSystem` を試合核のball段階へ登録し、Node無しで減速・重力・バウンド・曲球/ナックル、ゴール/ポスト/場外、距離/高さ/拾い直し/回収順・GKの手の使用可否を処理します。保持中は自由弾道を更新せず、タックルこぼれ球は所有を解放します。

公開チーム由来の64ケースをPython実弾道から生成し、同じ固定tickの位置/速度・到達/着地・境界/接触候補を実Godotで照合。低速/高速/浮き球/曲球/ナックルは30/60/120Hz×全6倍速でも同じ演算結果を検査します。ログは `user_data/logs/godot/ball_physics/`。接触成功率/スキル/再開進行は隔離しており、未解決の接触/ゴール/場外は次STEPを拒否します。検出だけで得点/結果を返しません。全試合互換は引き続き `not_evaluated`。
