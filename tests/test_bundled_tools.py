"""Bundled tool references and helpers survive a relocated installation."""
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class BundledToolsTests(unittest.TestCase):
    def test_relative_skill_links_resolve_after_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            installed = Path(tmp) / "迁移安装 with spaces" / "lab-report"
            shutil.copytree(ROOT / "skills", installed / "skills")
            shutil.copy2(ROOT / "SKILL.md", installed / "SKILL.md")
            entry = installed / "SKILL.md"
            links = re.findall(r"\]\((skills/[^)]+/SKILL\.md)\)", entry.read_text(encoding="utf-8"))
            self.assertEqual(set(links), {
                "skills/vmware-lab-pair/SKILL.md",
                "skills/postman-local-lab/SKILL.md",
            })
            for link in links:
                skill = entry.parent / link
                self.assertTrue(skill.is_file(), str(skill))
                for target in re.findall(r"\]\(([^)]+)\)", skill.read_text(encoding="utf-8")):
                    if "://" not in target:
                        self.assertTrue((skill.parent / target).is_file(), target)

    def test_relocated_helpers_run_from_another_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            installed = Path(tmp) / "迁移安装 with spaces"
            shutil.copytree(ROOT / "skills", installed)
            for helper, flag in (
                ("vmware-lab-pair/scripts/lab_probe.py", "--help"),
                ("postman-local-lab/scripts/run_fixture.py", "--self-test"),
            ):
                result = subprocess.run(
                    [sys.executable, "-X", "utf8", "-B", str(installed / helper), flag],
                    cwd=tmp, capture_output=True, text=True, encoding="utf-8", timeout=30,
                )
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
