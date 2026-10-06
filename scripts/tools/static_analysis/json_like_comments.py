"""Audit declaration comment structure, not the truth of its prose."""

import argparse
import ast
import json
import re
import subprocess
from pathlib import Path

from scripts.core.paths import PROJECT_ROOT


# {
#   責務: [python_declarations: Python宣言を修飾名・位置・意味構造へ分解する]
#   処理: [1: ASTを解析; 2: 入れ子宣言を巡回してデコレータ直前と宣言種別を記録]
#   引数: [source: Pythonソース]
#   戻り値: [dict: 修飾名ごとの種別・開始行・コメントを除いた構造]
# }
def python_declarations(source: str) -> dict:
    declarations = {}
    visit_python(ast.parse(source), "", declarations)
    return declarations


# {
#   責務: [visit_python: ASTの入れ子関係を維持して宣言を収集する]
#   処理: [1: 子ノードを順に巡回; 2: 宣言情報を記録して修飾名を更新; 3: 子の宣言を再帰収集]
#   引数: [node: 現在のAST; prefix: 所属宣言の接頭辞; declarations: 収集先辞書]
#   戻り値: [None: 収集先へ宣言情報を追記する]
# }
def visit_python(node: ast.AST, prefix: str, declarations: dict) -> None:
    for child in ast.iter_child_nodes(node):
        name = prefix
        if isinstance(child, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            name = prefix + child.name
            start = min([child.lineno] + [decorator.lineno for decorator in child.decorator_list])
            kind = "class" if isinstance(child, ast.ClassDef) else "function"
            declarations[name] = (kind, start, ast.dump(child, include_attributes=False))
            name += "."
        visit_python(child, name, declarations)


# {
#   責務: [gdscript_declarations: 型付きGDScriptのクラスと関数の宣言位置を抽出する]
#   処理: [1: 明示クラスまたはextendsによるスクリプトクラスを検出; 2: 関数の字下げ範囲を収集して比較形を作る]
#   引数: [source: GDScriptソース]
#   戻り値: [dict: クラスと関数の種別・開始行・比較用トークン列]
# }
def gdscript_declarations(source: str) -> dict:
    lines = source.splitlines()
    declarations = {}
    classes = [(i, match.group(1)) for i, line in enumerate(lines)
               if (match := re.match(r"^class_name\s+(\w+)", line))]
    if not classes:
        classes = [(i, "<script>") for i, line in enumerate(lines) if re.match(r"^extends\s+", line)][:1]
    for index, name in classes:
        declarations[name] = ("class", index + 1, gdscript_code(lines))
    for index, line in enumerate(lines):
        match = re.match(r"^(\s*)(?:static\s+)?func\s+(\w+)\s*\(", line)
        if not match:
            continue
        indent = len(match.group(1).expandtabs(4))
        end = index + 1
        while end < len(lines):
            content = lines[end].strip()
            leading = len(lines[end]) - len(lines[end].lstrip())
            if content and not content.startswith("#") and len(lines[end][:leading].expandtabs(4)) <= indent:
                break
            end += 1
        declarations[match.group(2)] = ("function", index + 1, gdscript_code(lines[index:end]))
    return declarations


# {
#   責務: [gdscript_code: GDScript比較からコメントと空行を除く]
#   処理: [1: 文字列内のハッシュを保護して行コメントを除去; 2: 有効行を連結]
#   引数: [lines: 比較対象のソース行]
#   戻り値: [str: 演算・宣言の変更を比較するソース表現]
# }
def gdscript_code(lines: list[str]) -> str:
    pattern = r'''(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|(#.*)'''
    return "\n".join(value for line in lines if (value := re.sub(pattern, lambda match: "" if match.group(1) else match.group(0), line).rstrip()))


# {
#   責務: [declaration_comment: 宣言直前のコメント群だけを構造検査へ渡す]
#   処理: [1: 直前の空行を飛ばす; 2: 連続コメントを逆順に収集して元順へ戻す]
#   引数: [lines: ソース行; start: デコレータを含む一始まり宣言行]
#   戻り値: [str: 隣接コメント本文。無ければ空文字]
# }
def declaration_comment(lines: list[str], start: int) -> str:
    index = start - 2
    while index >= 0 and not lines[index].strip():
        index -= 1
    comments = []
    while index >= 0 and lines[index].lstrip().startswith("#"):
        comments.append(lines[index].lstrip()[1:].lstrip())
        index -= 1
    return "\n".join(reversed(comments))


# {
#   責務: [missing_sections: 宣言コメントの最低構造と必須項目の欠落を検出する]
#   処理: [1: 波括弧の構造ブロックを取り出す; 2: 種別ごとの配列項目と必須説明を検査]
#   引数: [comment: 宣言直前のコメント本文; kind: classまたはfunction]
#   戻り値: [list: 不足項目名。文章の意味や処理順の正しさまでは認定しない]
# }
def missing_sections(comment: str, kind: str) -> list[str]:
    required = ("責務", "フィールド") if kind == "class" else ("責務", "処理", "引数", "戻り値")
    block = re.search(r"(?:^|\n)\s*\{\s*\n(.*?)\n\s*\}\s*(?:$|\n)", comment, re.S)
    if block is None:
        return ["構造ブロック", *required]
    fields = dict(re.findall(r"(?:^|\n)\s*([^\s:]+)\s*:\s*\[(.*?)\]", block.group(1), re.S))
    return [key for key in required if key not in fields or (key not in ("フィールド", "引数") and not fields[key].strip())]


# {
#   責務: [audit_source: 追加・変更宣言のコメント不足を一ファイル単位で報告する]
#   処理: [1: 新旧宣言を抽出; 2: 追加または構造変更の宣言に絞る; 3: 隣接コメントの必須項目を検査]
#   引数: [path: 相対ソース名; source: 検査ソース; before: 基準ソース。Noneなら全宣言]
#   戻り値: [dict: 検査した宣言数と不足の位置・修飾名・項目]
# }
def audit_source(path: str, source: str, before: str | None = None) -> dict:
    extract = python_declarations if path.endswith(".py") else gdscript_declarations
    current = extract(source)
    previous = extract(before) if before is not None else {}
    lines = source.splitlines()
    checked = 0
    violations = []
    for name, (kind, start, structure) in current.items():
        if name in previous and previous[name][2] == structure:
            continue
        checked += 1
        missing = missing_sections(declaration_comment(lines, start), kind)
        if missing:
            violations.append({"path": path, "line": start, "declaration": name, "kind": kind, "missing": missing})
    return {"checked": checked, "violations": violations}


# {
#   責務: [git_text: シェル展開を使わず読取専用Git操作の結果を取得する]
#   処理: [1: 正式ルートで引数列を実行; 2: UTF-8として結果を復元]
#   引数: [arguments: Gitの読取操作と対象]
#   戻り値: [str: 実行結果。Git失敗はCalledProcessError]
# }
def git_text(*arguments: str) -> str:
    return subprocess.check_output(["git", *arguments], cwd=PROJECT_ROOT, stderr=subprocess.PIPE).decode("utf-8-sig")


# {
#   責務: [audit_revisions: PRの実baseとheadの間で変更宣言のコメントを検査する]
#   処理: [1: 追加・変更されたPythonとGDScriptだけを列挙; 2: 両revisionのソースを取得; 3: ファイル検査を集約]
#   引数: [base: PRの基準revision; head: PRの提出revision]
#   戻り値: [dict: revision・検査数・欠落宣言。依存PRの既存宣言は重複検査しない]
# }
def audit_revisions(base: str, head: str) -> dict:
    paths = git_text("diff", "--name-only", "--diff-filter=ACMRT", "-z", base, head).split("\0")
    report = {"base": base, "head": head, "checked": 0, "violations": []}
    for path in paths:
        if not path.endswith((".py", ".gd")):
            continue
        source = git_text("show", f"{head}:{path}")
        try:
            before = git_text("show", f"{base}:{path}")
        except subprocess.CalledProcessError:
            before = ""
        result = audit_source(path, source, before)
        report["checked"] += result["checked"]
        report["violations"].extend(result["violations"])
    return report


# {
#   責務: [main: revision差分または指定ソースのコメント構造検査をCLIで提供する]
#   処理: [1: 互いに排他的な検査対象を解析; 2: 欠落を集計し任意のJSONログへ保存; 3: 成否を終了コードへ変換]
#   引数: [argv: CLI引数。Noneならプロセスの引数]
#   戻り値: [int: 構造不足なし0、不足1、対象不正・読込失敗2]
# }
def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", type=Path, help="Inspect every declaration in these working files")
    parser.add_argument("--base", help="Actual PR base revision")
    parser.add_argument("--head", default="HEAD", help="Submitted PR revision")
    parser.add_argument("--output", type=Path, help="Optional JSON audit output")
    args = parser.parse_args(argv)
    if bool(args.paths) == bool(args.base):
        parser.error("specify working source paths OR --base")
    try:
        report = {"checked": 0, "violations": []}
        if args.base:
            report = audit_revisions(args.base, args.head)
        else:
            for path in args.paths:
                if path.suffix not in (".py", ".gd"):
                    raise ValueError("only .py and .gd sources are supported")
                result = audit_source(str(path), path.read_text(encoding="utf-8-sig"))
                report["checked"] += result["checked"]
                report["violations"].extend(result["violations"])
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        for row in report["violations"]:
            print(f"{row['path']}:{row['line']} {row['declaration']}: {', '.join(row['missing'])}")
        print(f"COMMENT STRUCTURE: {report['checked']} declarations, {len(report['violations'])} violations; semantic review required")
        return 1 if report["violations"] else 0
    except (OSError, ValueError, SyntaxError, subprocess.CalledProcessError) as error:
        print(f"COMMENT AUDIT FAILED: {error}")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
