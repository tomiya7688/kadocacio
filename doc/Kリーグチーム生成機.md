# Kリーグチーム生成機

## 目的

開発中の9階層リーグを評価できるように、K1～K9へ既定20チームずつ、合計180チームを再現可能な条件で生成します。既存の`kadoka_original_A`と`kadoka_original_B`は初期値として参照・コピーするだけで、元JSONは編集しません。

生成処理とゲーム本体は分離されています。通常起動時に自動生成せず、開発者がCLIを明示的に実行した時だけ書き出します。

## プレビュー

```bat
.venv\Scripts\python.exe -m scripts.tools.generate_k_league_teams
```

既定ではファイルを変更せず、リーグ数とチーム数だけを表示します。リーグ数、各リーグのチーム数、能力基準、フォルダ名、表示色、名前候補、チーム傾向は`teameditor_templete/k_league_generation.json`から変更できます。

## 書き出し

```bat
.venv\Scripts\python.exe -m scripts.tools.generate_k_league_teams --write
```

- `teams/KadokaOriginalK1`～`KadokaOriginalK9`へチームJSONを保存します。
- `league_templates/K1-K9.json`へ、生成チームを配置済みのリーグテンプレートを保存します。
- 同名ファイルが存在する場合は停止します。意図的に再生成する場合だけ`--overwrite`を指定します。
- 生成先を隔離して確認する場合は`--output-root`と`--template-path`を指定します。

例：3リーグ、各8チームを別フォルダへ生成します。

```bat
.venv\Scripts\python.exe -m scripts.tools.generate_k_league_teams --leagues 3 --teams 8 --write --output-root development_teams --template-path league_templates/K1-K3.json
```

## チームの個性

チーム能力はK1からK9へ段階的に低くなります。同じ平均付近でも、バランス、フィジカル、テクニック、スピード、持久力、攻撃、守備、知性、エース型を循環させます。

能力値は現行の0～5500で保存し、チームエディタと同じカテゴリ補正を使用します。エース型だけはチーム全体の能力予算を大きく変えず、中心選手へ能力を寄せます。ポジション別能力、フォーメーション、監督、戦術、スキルは既存の決定的生成器を再利用します。

## 外部で生成した名前

Ollamaなどでチーム名だけを作成した場合、配列または`チーム名`配列を持つUTF-8 JSONを渡せます。

```json
{
  "チーム名": ["旭川オーロラ", "青森ヴォルテックス"]
}
```

```bat
.venv\Scripts\python.exe -m scripts.tools.generate_k_league_teams --names-file team_names.json
```

候補数が不足する場合は生成前にエラーにし、中途半端なチーム構成を採用しません。

## 実試合評価

生成後の`K1-K9`テンプレートを使い、開発者評価を実行します。

```bat
run_developer_evaluation.bat --template K1-K9 --leagues all --seasons 5 --hours 0
```

評価は通常試合と同じ物理・AIでリーグ戦と入れ替え戦を処理します。少なくとも1年度を完走すると、`checkpoint.json`の`manager_state.competition_template`へ実際の昇降格後の所属が保存されます。

## 評価後の自動再配置

最初は必ずプレビューします。

```bat
.venv\Scripts\python.exe -m scripts.tools.reseed_k_league_teams development_evaluation\league_eval_日時\checkpoint.json
```

評価チェックポイントと`league_templates/K1-K9.json`について、Kリーグ数と全チームIDが完全一致する場合だけ移動計画を表示します。近似的な独自順位は使わず、実試合の入れ替え戦を経た所属をそのまま採用します。

内容を確認してから適用します。

```bat
.venv\Scripts\python.exe -m scripts.tools.reseed_k_league_teams development_evaluation\league_eval_日時\checkpoint.json --apply
```

- 昇降格したチームJSONを対応する`KadokaOriginalK*`フォルダへ移します。
- `league_templates/K1-K9.json`のチームIDも新しいパスへ更新します。
- 移動前の全チームとテンプレートを`development_reseed_backup/k_reseed_日時/`へ保存します。
- 1年度も完走していない評価、チーム不足、未登録チーム、重複所属、既存ファイルとの衝突は適用前に拒否します。
- 適用中に失敗した場合は、作成した移動先を除去し、バックアップから元ファイルとテンプレートを復旧します。
