from pathlib import Path

from scripts.tools import context_docs


def make_package(root: Path, relative: str, modules=(), packages=()):
    folder = root / relative
    folder.mkdir(parents=True)
    (folder / "__init__.py").write_text("", encoding="utf-8")
    for module in modules:
        (folder / module).write_text("", encoding="utf-8")
    for package in packages:
        child = folder / package
        child.mkdir()
        (child / "__init__.py").write_text("", encoding="utf-8")
    return folder


def test_discover_modules_and_packages_are_sorted_and_ignore_nonpackages(tmp_path):
    folder = make_package(
        tmp_path,
        "scripts/sample",
        modules=("z.py", "a.py"),
        packages=("child",),
    )
    (folder / "notes.txt").write_text("", encoding="utf-8")
    (folder / "plain_dir").mkdir()

    assert context_docs.discover_modules("scripts/sample", root=tmp_path) == ["a.py", "z.py"]
    assert context_docs.discover_packages("scripts/sample", root=tmp_path) == ["child/"]


def test_discovery_returns_empty_for_missing_folder(tmp_path):
    assert context_docs.discover_modules("missing", root=tmp_path) == []
    assert context_docs.discover_packages("missing", root=tmp_path) == []


def test_bullet_and_quote_helpers_cover_items_and_empty():
    assert context_docs.bullet_lines(("a", "b")) == ["- a", "- b"]
    assert context_docs.bullet_lines(()) == ["- (none)"]
    tick = chr(96)
    assert context_docs.quoted(("a",)) == [f"{tick}a{tick}"]


def test_render_context_contains_contract_and_current_modules(tmp_path):
    make_package(tmp_path, "scripts/sample", modules=("main.py",), packages=("child",))
    spec = {
        "responsibility": "Sample responsibility.",
        "entrypoints": ("main.py",),
        "classes": ("Sample",),
        "data": ("sample data",),
        "allowed": ("core",),
        "forbidden": ("app",),
        "read_first": ("main.py",),
        "ignore": ("other.py",),
        "related": ("AGENTS.md",),
    }

    rendered = context_docs.render_context("scripts/sample", spec, root=tmp_path)

    assert "AUTO-GENERATED" in rendered
    assert "Sample responsibility." in rendered
    assert "main.py" in rendered
    assert "child/" in rendered
    assert "Forbidden / avoid:" in rendered


def test_generate_context_docs_writes_and_check_accepts_current_files(monkeypatch, tmp_path, capsys):
    make_package(tmp_path, "scripts/sample", modules=("main.py",))
    monkeypatch.setattr(
        context_docs,
        "CONTEXT_SPECS",
        {
            "scripts/sample": {
                "responsibility": "Sample.",
                "entrypoints": ("main.py",),
                "classes": (),
                "data": (),
                "allowed": (),
                "forbidden": (),
                "read_first": ("main.py",),
                "ignore": (),
                "related": (),
            }
        },
    )

    assert context_docs.generate_context_docs(root=tmp_path) == 0
    target = tmp_path / "scripts/sample/CONTEXT.md"
    assert target.is_file()
    assert "GENERATED (1)" in capsys.readouterr().out

    assert context_docs.generate_context_docs(root=tmp_path, check=True) == 0
    assert "CONTEXT DOCS: PASS" in capsys.readouterr().out


def test_check_reports_missing_and_stale_context_docs(monkeypatch, tmp_path, capsys):
    make_package(tmp_path, "scripts/one", modules=("a.py",))
    make_package(tmp_path, "scripts/two", modules=("b.py",))
    spec = {
        "responsibility": "Sample.",
        "entrypoints": (),
        "classes": (),
        "data": (),
        "allowed": (),
        "forbidden": (),
        "read_first": (),
        "ignore": (),
        "related": (),
    }
    monkeypatch.setattr(
        context_docs,
        "CONTEXT_SPECS",
        {"scripts/one": spec, "scripts/two": spec},
    )
    (tmp_path / "scripts/two/CONTEXT.md").write_text("stale", encoding="utf-8")

    assert context_docs.generate_context_docs(root=tmp_path, check=True) == 1
    output = capsys.readouterr().out
    assert "CONTEXT DOCS: STALE" in output
    assert "scripts/one/CONTEXT.md" in output
    assert "scripts/two/CONTEXT.md" in output
    assert "python -m scripts.tools.context_docs" in output


def test_parse_args_and_main_route_check_mode(monkeypatch):
    assert context_docs.parse_args([]).check is False
    assert context_docs.parse_args(["--check"]).check is True

    calls = []
    monkeypatch.setattr(
        context_docs,
        "generate_context_docs",
        lambda *, check=False: calls.append(check) or 0,
    )
    assert context_docs.main([]) == 0
    assert context_docs.main(["--check"]) == 0
    assert calls == [False, True]


def test_repository_specs_cover_major_source_folders():
    assert tuple(context_docs.CONTEXT_SPECS) == (
        "scripts/app",
        "scripts/core",
        "scripts/match",
        "scripts/league",
        "scripts/team",
        "scripts/tools",
        "scripts/tools/static_analysis",
    )
