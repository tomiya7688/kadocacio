# UPD Commander 適用方針

Kadocalcio では `tomiya7688/upd-commander-base-design` の設計原則を、リアルタイムゲームの実行速度を損なわない範囲で段階導入する。

## 目的

UPD Commander の目的は、コードを形式的に三分割することではなく、UI・ゲーム処理・データ処理の責務と通信方向を明示し、巨大なクラスや境界越え依存を増やしにくくすることにある。

Kadocalcio では次の2つの軸を混同しない。

- **製品/配布の軸**: 汎用サッカーゲームエンジン / Kadocalcio専用エディタ / Kadocalcioゲーム本体
- **機能内部の責務軸**: UI / Process / Data

UPD Commander は後者へ適用する。エンジン境界そのものは既存の `architecture_boundary` でも検証する。

## 基本ルール

- UI は入力・表示・画面状態を扱い、ゲーム計算や永続化を直接抱え込まない。
- Process は試合・リーグ・編集処理などのルールと計算を担当し、表示方法を知らない。
- Data はJSON、設定、セーブ等の読込・保存・変換を担当し、UIを知らない。
- Commander は一連の処理の順序と呼び出しを指揮し、計算・ループ・直接I/Oを持たない。
- Messenger は層を越える通信を担当し、ゲームルールやデータ処理を持たない。
- 実処理は Processing / service / domain module 等の小さい責務単位へ置く。

## Kadocalcio の性能例外

UPDを理由に、リアルタイムのホットパスへ追加のdispatchや一時オブジェクト生成を入れない。

特に次は **Process内部の直接呼び出しを許容する**。

- `scripts/match/match_engine.py` の固定ステップ更新
- 選手ごとの移動・スタミナ・衝突・ボール判定
- AIの高頻度判断と候補評価
- 1フレーム内で大量に呼ばれる数学・座標処理
- 描画ループ内の高頻度処理
- ヘッドレス大量シミュレーションの内側ループ

たとえば「1フレームごとに Process Messenger を経由して選手を更新する」構造にはしない。試合開始、試合終了、設定反映、保存などの**低頻度境界**でUPDの通信経路を使い、試合中の内部計算はProcess内で閉じる。

性能上の例外は責務放棄を意味しない。ホットパスでも巨大化した処理は、関数・モジュール単位で分割しつつ、呼び出し回数や割り当てを増やさない方法を優先する。

## 新規機能で推奨する構成

新しい独立機能や、大きく作り直す低頻度機能では、checkerが認識できる構造を優先する。

```text
scripts/features/<feature>/
├─ ui/
│  ├─ commander.py
│  ├─ messenger.py
│  └─ processing.py
├─ process/
│  ├─ commander.py
│  ├─ messenger.py
│  └─ processing.py
└─ data/
   ├─ commander.py
   ├─ messenger.py
   └─ processing.py
```

すべての機能に9ファイルを作る必要はない。責務が存在するものだけ作り、薄い中継だけのファイルを増やさない。

既存の `scripts/app` / `scripts/match` / `scripts/league` / `scripts/team` / `scripts/core` は一括改名しない。変更対象になった責務から段階的に分割する。

## 初期checkerポリシー

Python版 UPD Commander Checker を `requirements-dev.txt` からのみ導入する。ゲーム用 `requirements.txt` には追加しないため、通常起動・試合実行・PyInstaller配布物のランタイム依存にはならない。

upstreamは予期しないルール変更を防ぐためcommit SHA固定とする。設定は `static_analysis/upd_commander.json`、Kadocalcio用アダプターは `scripts/tools/static_analysis/upd_commander.py` に置く。

初期段階で有効にするのは次のルール。

- `UPD001`, `UPD002`: 読込・構文エラー
- `UPD101`〜`UPD103`: 層・Application境界
- `UPD201`〜`UPD203`: Commanderへの実処理漏洩
- `UPD401`〜`UPD404`: 責務過大・型配置

`error` はCI失敗とする。既存コードに多数存在し得る `warning` / `attention` は、まずリファクタ候補としてJSONレポートへ残し、CIは失敗させない。

### 初期段階で無効にするルール

`UPD301`〜`UPD303` のContainer/Compresser候補は初期状態では無効にする。

複数引数をContainerへまとめることは可読性向上に有効な場合がある一方、試合ホットパスではpacking/unpackingや一時オブジェクト生成を増やす可能性がある。必要になった場合は、保存・設定・編集コマンド等の低頻度領域から限定的に有効化する。

## 実行

通常の統合入口から実行される。

```bat
run_static_analysis.bat
```

個別実行:

```bat
.venv\Scripts\python.exe -m scripts.tools.static_analysis.upd_commander
```

詳細結果は `static_analysis/reports/upd_commander.json` に生成される。コンソールは上位の指摘だけを表示し、大量ログをCodex等へ直接渡さない。

## 段階移行

1. checkerをCIへ導入し、既存の責務過大を可視化する。
2. 新規機能・大規模改修から明示的なUI/Process/Data境界を採用する。
3. `UPD401` 等で繰り返し検出される巨大責務を、機能変更のタイミングで分割する。
4. warning件数が十分減った領域のみ、必要に応じてwarningをブロックへ昇格する。
5. Container系ルールは実測で性能影響が無い低頻度領域に限って検討する。

「UPDに合わせるためだけの大規模移動」は行わず、テスト可能性・依存方向・保守性に実益がある変更を優先する。
