# Kadocalcio AI Context

AI/Codex が最初に読む最小入口です。詳細仕様はここへ複製せず、必要な原典へ移動してください。

## Project
- Name: Kadocalcio
- Purpose: サッカーゲーム本体、編集/評価ツール、将来の再利用可能なゲームエンジン層を開発する。
- Runtime: Python / Pygame

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

## Exploration Stop Condition
次が十分に分かったら追加探索を止め、実装へ進む。
- Goal
- Required
- Acceptance
- Working set
- Deferred（必要な場合）

次のread/searchが不足・矛盾・Acceptance確認のどれを埋めるか説明できない場合、探索停止を優先する。正確性が不足する場合は原典へ戻る。

## Ignore Normally
- `ai_evaluation/`
- `performance_logs/`
- `development_evaluation/`
- `development_reseed_backup/`
- runtime saves / backups
- generated reports / caches
- unrelated Issues / docs / history

## Validation
検証結果は `VERIFIED` / `UNVERIFIED` / `BLOCKED` / `NOT_APPLICABLE` を区別する。`UNVERIFIED` をゼロにするためだけの全探索は行わず、Acceptance・安全性・互換性に必要な確認だけ必須へ昇格する。

## Task Capsule
`start_task.bat [issue-number]` で `context/<issue-number>/` に短い作業入口を生成する。Task CapsuleはSource of Truthではなく索引であり、必要なら原Issue・コード・テストへ戻る。
