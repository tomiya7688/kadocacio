# データ境界

チームJSONの読み取り専用API。入口 `TeamJsonRepository` から、`StrictJsonReader` → `TeamPayloadValidator` → `TeamPayloadDecoder` → `TeamDefinition` へ渡す。UI/Nodeやファイル保存へ依存しない。

診断/成功結果/カタログ、チーム/選手/監督モデルはそれぞれ別ファイル。能力を正規化するが `original_payload` / 選手 `raw` も残す。`UniformDecoder` はユニフォームだけを担当する。APIとPythonとの検証手順は `godot/README.md`。元データとセーブ内スナップショットはまだ接続せず、旧セーブの互換実装は #136。
