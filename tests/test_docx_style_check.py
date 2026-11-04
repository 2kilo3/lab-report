"""Synthetic OOXML style contracts for B19; no Word install or rendering required."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import zipfile

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'docx_style_check.py'
spec = importlib.util.spec_from_file_location('docx_style_check', SCRIPT)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
DOCUMENT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="{namespace}">
  <w:body>
    <w:p><w:r><w:rPr><w:rFonts w:eastAsia="宋体"/><w:sz w:val="24"/></w:rPr><w:t>正文段落</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="黑体"/><w:sz w:val="32"/></w:rPr><w:t>2.1 实验步骤</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Heading3"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="SimHei"/></w:rPr><w:t>2.2 子标题</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="Heading2"/></w:pPr><w:r><w:rPr><w:rFonts w:eastAsia="宋体"/><w:sz w:val="24"/><w:b/></w:rPr><w:t>2.3 合规标题</w:t></w:r></w:p>
    <w:p><w:r><w:rPr><w:rFonts w:eastAsia="黑体"/><w:sz w:val="36"/></w:rPr><w:t>正文中的黑体却非标题</w:t></w:r></w:p>
  </w:body>
</w:document>
""".format(namespace=W)


class DocxStyleCheckTests(unittest.TestCase):
    def test_heading_font_and_size_upgrades_are_flagged(self):
        records = checker.find_violations(DOCUMENT.encode('utf-8'), 24)
        self.assertEqual([record['paragraph'] for record in records],
                         ['2.1 实验步骤', '2.1 实验步骤', '2.2 子标题'])
        self.assertEqual([record['kind'] for record in records],
                         ['eastAsia_font', 'size_upgrade', 'eastAsia_font'])
        self.assertEqual(records[1]['value'], 16.0)

    def test_heading_with_matching_body_font_and_bold_is_accepted(self):
        records = checker.find_violations(DOCUMENT.encode('utf-8'), 24)
        self.assertFalse(any(record['paragraph'] == '2.3 合规标题' for record in records))

    def test_non_heading_black_font_is_ignored(self):
        records = checker.find_violations(DOCUMENT.encode('utf-8'), 24)
        self.assertFalse(any(record['paragraph'] == '正文中的黑体却非标题' for record in records))

    def test_docx_zip_and_cli_return_nonzero_on_violation(self):
        with tempfile.TemporaryDirectory(prefix='样式 抽检 ') as temp:
            target = Path(temp) / 'synthetic.docx'
            with zipfile.ZipFile(target, 'w') as archive:
                archive.writestr('word/document.xml', DOCUMENT)
            self.assertIn(b'2.1', checker.read_document_xml(target))
            result = subprocess.run([sys.executable, '-B', str(SCRIPT), str(target), '--json'],
                                    capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            payload = json.loads(result.stdout)
            self.assertFalse(payload['ok'])
            self.assertEqual(len(payload['violations']), 3)


if __name__ == '__main__':
    unittest.main()
