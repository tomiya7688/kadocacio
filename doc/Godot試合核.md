# Godot試合核の基盤（#124）

対象は [#124](https://github.com/tomiya7688/kadocacio/issues/124)。入力と観測の正本は [`試合境界契約.md`](試合境界契約.md)。今回移したのは初期状態・時計・固定更新の接続・乱数であり、**サッカーの試合全体ではない**。Pythonの通常入口・試合判定・teams・リーグセーブを変更しない。Godotメニューからの試合開始もまだ接続しない。

## 責務と参照対応

| Python参照 | Node無しのGodot | 今回の範囲 |
|---|---|---|
| `player.py`, `team.py`, `ball.py` | `PlayerState`, `TeamState`, `BallState` | 位置・速度・所有者・ロスター・定義・集計の試合内状態 |
| `simulation_geometry.py` | `SimulationCoordinate` | x/y/zを倍精度スカラーで保持。描画用Vectorへ変換するのは表示側 |
| `Match.__init__`, `start_new`, `reset_positions` | `MatchSetup` | 初期能力/配置・ロスター・キックオフ・初期乱数の順番 |
| `Match.update_step` の時計/フェーズ | `MatchClock` | 演算/試合時計、準備待ち、バナー、前後半、90分終了 |
| `MatchSession` | `MatchKernel` | 操作の適用と更新処理の接続。演算/AIの本体は後続Issue |
| `MatchObservation`, ログAPI | `MatchSnapshot`, `MatchEventLog` | 明示取得時のみ独立JSON値へ複製。観測は乱数を消費しない |
| `simulation_runtime`, `RealtimeSimulationDriver` | `FixedStepDriver` | 最大0.05秒の固定tickと未処理時間。Pythonホストの時間制限等はまだ移さない |
| `random.Random` | `PythonRandomStream` | 整数seedを使ったMT19937の互換サブセット |
| 開発用 `MatchRandomAudit` | `ObservedMatchRandom` | オプトインの原始乱数監査 |

`MatchState` は演算核が所有する状態の集合。UIへ渡すのは `observe()` の値だけとし、内部状態・定義・乱数を画面から書き換えない。状態クラスはRefCountedでNode、Pygame、描画・ファイル保存を持たない。JSON能力変換は既存 `TeamPayloadDecoder` を再利用し、別の能力スケールを作らない。先発7〜11人・GK1人以上を要求し、FW/MF/DFは0人でも有効。

## 接続と未実装の拒否

```gdscript
var kernel: MatchKernel = MatchKernel.from_input(contract_input)
if not kernel.error.is_empty():
    # 呼出し元へ診断を返す。
    return
kernel.apply({"kind": "START"})
var snapshot: Dictionary = kernel.observe()
# 実際の選手/判断/ボール処理を登録した後に固定更新を供給する。
var driver: FixedStepDriver = FixedStepDriver.new(kernel)
```

`from_input` は既存v1読込に加えて、先発の名前/背番号/raw/slot・有限な配置0..1・GK・チーム選択値を検査し、独立した試合状態を作る。`apply` はbool、失敗時 `error` を返す。STARTは一度だけ、停止中/終了後のSTEPは更新しない。上限を超えるdt・不正操作・予算超過を時計の更新前に拒否する。

選手・判断・ボールの3段階を `register_system("players"|"decisions"|"ball", callable)` で接続する。シグネチャは `(state: MatchState, dt: float, rng: ObservedMatchRandom) -> void`。受信側はRefCountedでNode不可、カーネルが強参照を保持する。更新順序は3段階の順に固定。後続の演算クラスをここへ接続し、別の簡易試合エンジンを作らない。

現在はキックオフの表示待ちだけ実行可能。通常プレイまたは再開準備のSTEPには3段階すべてを要求し、欠ければ**状態・時計を変更せず拒否**する。テスト専用 `KernelStepProbe` は規定の座標/判断を更新して呼出回数を検査するもので、本番の物理/AI代用品ではない。得点・反則・結果集計が未移行なので、基盤テストがFULLTIMEに到達しても `result` はnull。偽の0-0完走を返さない。

## 固定更新と時計

- ドライバーは実時間×倍率を蓄積し、0.05秒tickのみ供給。1秒の演算で試合時計は10秒、90分は5400秒。倍速1/2/3/5/10/100はtick数だけに作用する。
- 1回の `advance(real_dt, max_steps=256)` の回数制限を超えた分は `pending_time` に残す。`advance(0)` で残りを処理できる。失敗時も未処理時間を捨てない。停止/終了時は蓄積を消し、再開後に停止時間を追いつき処理しない。
- 観測要求・描画回数は更新数にしない。毎tickの全ロスターJSON化も行わない。ホストは `is_ready/is_playing/is_paused/speed` を読む。
- `STEP` のdtには倍率を掛けない。会場ごとに別カーネル/ドライバーを持ち、スロー/セットプレー準備はその試合時計だけ止める。準備中も演算経過と接続した配置更新は進む。
- キックオフ/ハーフタイムのバナー判定はPython参照の更新前フラグと順番を維持する。前後半の切替時は配置を戻し、90分で時計を止める。

これはPythonのホストと同じ演算回数を供給するための交換点であり、既存ホストの可変な余りdt・リアルタイム予算を全移植した主張ではない。並列会場・CPU上限・裏試合モードは #137、性能実測は #142。

## 乱数の互換範囲

Godot標準RNGは使わず、一試合につき独立した `PythonRandomStream` を持つ。最大4096桁の符号付き10進seedを整数へ丸めず32bitリムへ変換し、Pythonの整数seedと同じabs・初期化・MT19937・53bit `random()` を実装する。負seedも正seedの絶対値と同じ列。参照仕様は [CPython 3.10.11 `_randommodule.c`](https://github.com/python/cpython/blob/v3.10.11/Modules/_randommodule.c) と [同版 `random.py`](https://github.com/python/cpython/blob/v3.10.11/Lib/random.py)。数学的手順を独立したGDScriptに実装し、Python oracleの値・内部状態・呼出順と照合する。

対応APIは `random`, `getrandbits(0..53)`, `uniform`, `randint`, `choice`, `gauss`。整数区間幅は正で9e15未満、各端点の絶対値も9e15未満。空配列や不正区間は内部APIの前提違反。`randint/choice` は棄却サンプリング、`gauss` は次回分のキャッシュを持ち、消費順もPythonに合わせる。文字列/float seed、全Random API、RNG状態からの復元/永続化は今回対象外。後続で必要なAPIを参照検査付きで増やす。

監査は既定無効。有効時は原始 `random/getrandbits` のsequence・実更新step・purpose・引数・値・32bit語の消費前後を記録する。整数ビット値とMT語・index・消費数は許容差なしで比較する。Gaussianの超越関数等はv1数値許容差で比較し、OSをまたいだ全ての浮動小数点ビット一致を保証しない。

Python側は `MatchSession(..., rng_factory=MatchRandomAudit)` で開発用監査を注入可能。通常の呼出しは従来の `random.Random(seed)` のままで、既存試合の乱数消費を追加しない。観測/ログ取得が乱数を進めないことも検査する。

## 検証入口と限界

```powershell
.venv\Scripts\python.exe -m scripts.tools.godot_match_contract
.venv\Scripts\python.exe -m scripts.tools.godot_kernel_fixture
.\run_godot.bat test
```

公開2チームでPythonの実 `Match` から初期状態とキックオフ50tick・監査列を捕捉。別に8seed（負・int64超過・4096桁を含む）、複数MT更新、全対応API、6時計/フェーズケースを参照側で検証しfixtureへ出す。元チームは成功/失敗/タイムアウト時にもSHA-256照合する。私有チーム・セーブは対象外。

実Godotでは初期状態/乱数の差分と、テスト専用更新を接続した20tickの再現性・30/60/120Hz・全倍速・停止・再開・残り時間・準備待ち・予算・無効入力・観測の独立コピーを検査する。90分の時計検査にも全段階を接続するが、実際のサッカー完走試験ではない。

保存出力は `user_data/logs/godot/match_kernel/{fixture,diff}.json`。ネイティブtraceは毎回新しい一時出力を使い、照合後に片付ける。`execution: simulation` は基盤を実行した意味、`scope: simulation_observations` はこの短い観測の一致。**`kernel_parity: not_evaluated` は維持**し、50tickの一致を全試合・AI・セーブ・90会場性能の互換認定にしない。Windows/Linux CIは同じ実エンジン入口を使用する。

次は #125 の弾道/境界/ゴールと #126 の移動/スタミナ/ジャンプ/フィジカルを、この状態/固定更新/乱数へ接続する。
