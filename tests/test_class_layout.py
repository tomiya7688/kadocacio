import ast
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_ROOT = PROJECT_ROOT / "scripts"
CLASS_CATALOG = PROJECT_ROOT / "doc" / "クラス一覧.md"


def production_classes() -> dict[Path, list[str]]:
    """Return every production class, including accidentally nested classes."""
    result: dict[Path, list[str]] = {}
    for path in sorted(SCRIPTS_ROOT.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        names = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
        if names:
            result[path] = names
    return result


class ClassLayoutTests(unittest.TestCase):
    def test_production_files_contain_at_most_one_class(self) -> None:
        violations = {
            str(path.relative_to(PROJECT_ROOT)): names
            for path, names in production_classes().items()
            if len(names) > 1
        }
        self.assertEqual({}, violations)

    def test_every_production_class_is_listed_once(self) -> None:
        catalog = CLASS_CATALOG.read_text(encoding="utf-8")
        missing: list[str] = []
        duplicated: list[str] = []
        for names in production_classes().values():
            for name in names:
                marker = f"| `{name}` |"
                count = catalog.count(marker)
                if count == 0:
                    missing.append(name)
                elif count > 1:
                    duplicated.append(name)
        self.assertEqual([], missing)
        self.assertEqual([], duplicated)


if __name__ == "__main__":
    unittest.main()
