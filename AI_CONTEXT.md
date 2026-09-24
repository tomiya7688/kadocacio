# Kadocalcio AI Context

AI/Codex が最初に読む最小入口です。詳細仕様はここへ複製せず、必要な原典へ移動してください。

## Project
- Name: Kadocalcio
- Purpose: サッカーゲーム本体、編集/評価ツール、将来の再利用可能なゲームエンジン層を開発する。
- Runtime: Python / Pygame

## Current State
- 現行構成は `main.py` を入口に、試合・リーグ・チーム編集・開発ツールを `scripts/` の役割別パッケージへ分けている。
- 直近の実装履歴は `doc/versions.md` の先頭、進行中の作業はGitHub Issues/PRを確認する。ここに固定のIssue件数やブランチ状態は書かない。
- フォルダ別の生成済み `CONTEXT.md` を入口にする。#27 の推奨entrypointレポートが整備されたら、その派生情報もここから案内する。

## Source of Truth
- AI作業ルール・コード地図: `AGENTS.md`
- 人間向け概要: `README.md`
- 詳細仕様: `SPEC.md`
- 実装: `main.py`, `scripts/`
- テスト: `tests/`
- タスク: GitHub Issues

## Read First
1. このファイル
2. 現在のIssue、または `start_task.bat`
3. `AGENTS.md` の該当するコード地図だけ
4. 対象sourceとmatching tests

README / SPEC / docs / 全Issueを最初から全読しない。

## Folder Context Index
対象フォルダへ入る前に、該当する短い生成済み説明書だけ読む。
- `scripts/app/CONTEXT.md`
- `scripts/core/CONTEXT.md`
- `scripts/match/CONTEXT.md`
- `scripts/league/CONTEXT.md`
- `scripts/team/CONTEXT.md`
- `scripts/tools/CONTEXT.md`
- `scripts/tools/static_analysis/CONTEXT.md`

これらは `python -m scripts.tools.context_docs` で生成し、手編集しない。コミット前チェックは `--check` で実コードとの乖離を検出する。

## Exploration Stop Condition
次が十分に分かったら追加探索を止め、実装へ進む。
- Goal
- Required
- Acceptance
- Working set
- Deferred（必要な場合）

次のread/searchが不足・矛盾・Acceptance確認のどれを埋めるか説明できない場合、探索停止を優先する。正確性が不足する場合は原典へ戻る。

## Ignore Normally
- `user_data/` (runtime saves, logs, exports, packaged-team edits)
- legacy root runtime dirs: `ai_evaluation/`, `performance_logs/`, `development_evaluation/`, `development_reseed_backup/`
- generated reports / caches
- unrelated Issues / docs / history

## Validation
検証結果は `VERIFIED` / `UNVERIFIED` / `BLOCKED` / `NOT_APPLICABLE` を区別する。`UNVERIFIED` をゼロにするためだけの全探索は行わず、Acceptance・安全性・互換性に必要な確認だけ必須へ昇格する。

## Task Capsule
`start_task.bat [issue-number]` で `context/<issue-number>/` に短い作業入口を生成する。`request.md` は「対象・目的・制約・読むべきファイル・完了条件」の5項目だけで渡せる作業指示、`task.md` は詳細、`files.txt` は推定された候補。Task CapsuleはSource of Truthではなく索引であり、必要なら原Issue・コード・テストへ戻る。
