import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ScriptLayoutTests(unittest.TestCase):
    def test_root_keeps_only_the_minimal_python_entrypoint(self):
        self.assertEqual([path.name for path in ROOT.glob("*.py")], ["main.py"])

    def test_role_packages_exist(self):
        expected = {"app", "core", "match", "league", "team", "tools"}
        actual = {
            path.name for path in (ROOT / "scripts").iterdir()
            if path.is_dir() and (path / "__init__.py").is_file()
        }
        self.assertTrue(expected.issubset(actual))


if __name__ == "__main__":
    unittest.main()
