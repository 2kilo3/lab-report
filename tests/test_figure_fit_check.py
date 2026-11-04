"""Synthetic DOCX contracts for figure fit; no Word install or rendering required."""
import importlib.util
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import zlib

from docx import Document
from docx.enum.section import WD_SECTION
from docx.oxml import OxmlElement
from docx.shared import Mm

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts' / 'figure_fit_check.py'
spec = importlib.util.spec_from_file_location('figure_fit_check', SCRIPT)
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)

PAGE_WIDTH = Mm(210)
SIDE_MARGIN = Mm(30)
TEXT_WIDTH_MM = 150.0


def png_bytes(width, height):
    """Build a minimal valid 8-bit greyscale PNG of the requested pixel size."""
    def chunk(tag, data):
        return (struct.pack('>I', len(data)) + tag + data
                + struct.pack('>I', zlib.crc32(tag + data) & 0xffffffff))

    header = struct.pack('>IIBBBBB', width, height, 8, 0, 0, 0, 0)
    rows = b''.join(b'\x00' + b'\x00' * width for _ in range(height))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', header)
            + chunk(b'IDAT', zlib.compress(rows, 9)) + chunk(b'IEND', b''))


def set_page(section):
    section.page_width = PAGE_WIDTH
    section.page_height = Mm(297)
    section.left_margin = SIDE_MARGIN
    section.right_margin = SIDE_MARGIN
    section.top_margin = Mm(25)
    section.bottom_margin = Mm(25)


def body_width_image(path, image, width_mm):
    document = Document()
    set_page(document.sections[0])
    document.add_picture(str(image), width=Mm(width_mm))
    document.save(str(path))


class FigureFitCheckTests(unittest.TestCase):
    def setUp(self):
        self._temp = tempfile.TemporaryDirectory(prefix='图幅 检查 ')
        self.temp = Path(self._temp.name)

    def tearDown(self):
        self._temp.cleanup()

    def make_image(self, name, width, height):
        target = self.temp / name
        target.write_bytes(png_bytes(width, height))
        return target

    def make_doc(self, name='figure.docx'):
        target = self.temp / name
        return target, Document()

    def test_body_image_wider_than_text_column_is_reported(self):
        image = self.make_image('wide.png', 1200, 800)
        target, document = self.make_doc()
        set_page(document.sections[0])
        document.add_picture(str(image), width=Mm(170))
        document.save(str(target))

        report = checker.inspect_document(target, glyph_px=20, min_font_mm=2.0)

        record = report['images'][0]
        self.assertEqual(record['container'], 'body')
        self.assertAlmostEqual(record['container_width_mm'], TEXT_WIDTH_MM, delta=0.1)
        self.assertAlmostEqual(record['display_width_mm'], 170.0, delta=0.1)
        self.assertEqual(record['status'], 'overwide')
        self.assertFalse(report['ok'])
        self.assertEqual(report['overwide'], 1)
        self.assertEqual(checker.main([str(target)]), 1)

    def test_image_that_fits_but_shrinks_text_is_a_warning_only(self):
        image = self.make_image('dense.png', 2400, 1600)
        target, document = self.make_doc()
        set_page(document.sections[0])
        document.add_picture(str(image), width=Mm(150))
        document.save(str(target))

        report = checker.inspect_document(target, glyph_px=20, min_font_mm=2.0)

        record = report['images'][0]
        self.assertEqual(record['status'], 'small_text')
        self.assertAlmostEqual(record['glyph_height_mm'], 1.25, delta=0.01)
        self.assertIn('font_height_below_threshold', record['warnings'])
        self.assertTrue(report['ok'])
        self.assertEqual(checker.main([str(target)]), 0)

    def test_threshold_parameter_can_accept_the_same_image(self):
        image = self.make_image('dense.png', 2400, 1600)
        target, document = self.make_doc()
        set_page(document.sections[0])
        document.add_picture(str(image), width=Mm(150))
        document.save(str(target))

        report = checker.inspect_document(target, glyph_px=20, min_font_mm=1.0)

        self.assertEqual(report['images'][0]['status'], 'ok')

    def test_readable_image_is_clean(self):
        image = self.make_image('clear.png', 600, 400)
        target, document = self.make_doc()
        set_page(document.sections[0])
        document.add_picture(str(image), width=Mm(120))
        document.save(str(target))

        report = checker.inspect_document(target)

        self.assertEqual(report['images'][0]['status'], 'ok')
        self.assertEqual(report['images'][0]['warnings'], [])
        self.assertEqual(checker.main([str(target)]), 0)

    def test_table_cell_uses_cell_width_and_padding(self):
        image = self.make_image('cell.png', 800, 600)
        target, document = self.make_doc()
        set_page(document.sections[0])
        table = document.add_table(rows=1, cols=1)
        table.autofit = False
        cell = table.cell(0, 0)
        cell.width = Mm(60)
        cell.paragraphs[0].add_run().add_picture(str(image), width=Mm(80))
        document.save(str(target))

        report = checker.inspect_document(target)

        record = report['images'][0]
        self.assertEqual(record['container'], 'table_cell')
        self.assertEqual(record['container_width_source'], 'tcW')
        self.assertAlmostEqual(record['container_width_mm'], 56.2, delta=0.2)
        self.assertEqual(record['status'], 'overwide')

    def test_image_inside_table_cell_within_cell_width_is_clean(self):
        image = self.make_image('cell-ok.png', 300, 200)
        target, document = self.make_doc()
        set_page(document.sections[0])
        table = document.add_table(rows=1, cols=1)
        table.autofit = False
        cell = table.cell(0, 0)
        cell.width = Mm(60)
        cell.paragraphs[0].add_run().add_picture(str(image), width=Mm(40))
        document.save(str(target))

        report = checker.inspect_document(target)

        self.assertEqual(report['images'][0]['status'], 'ok')
        self.assertTrue(report['ok'])

    def test_column_layout_reduces_available_width(self):
        image = self.make_image('columns.png', 800, 600)
        target, document = self.make_doc()
        section = document.sections[0]
        set_page(section)
        cols = section._sectPr.find(checker.qn('w:cols'))
        if cols is None:
            cols = OxmlElement('w:cols')
            section._sectPr.append(cols)
        cols.set(checker.qn('w:num'), '2')
        cols.set(checker.qn('w:space'), '425')
        document.add_picture(str(image), width=Mm(80))
        document.save(str(target))

        report = checker.inspect_document(target)

        record = report['images'][0]
        self.assertAlmostEqual(record['container_width_mm'], 71.3, delta=0.2)
        self.assertEqual(record['status'], 'overwide')

    def test_image_uses_its_own_section_margins(self):
        image = self.make_image('section.png', 800, 600)
        target, document = self.make_doc()
        set_page(document.sections[0])
        document.add_paragraph('第一节')
        second = document.add_section(WD_SECTION.NEW_PAGE)
        second.left_margin = Mm(60)
        second.right_margin = Mm(60)
        document.add_picture(str(image), width=Mm(120))
        document.save(str(target))

        report = checker.inspect_document(target)

        self.assertEqual(len(report['sections']), 2)
        self.assertAlmostEqual(report['sections'][1]['text_width_mm'], 90.0, delta=0.1)
        self.assertAlmostEqual(report['images'][0]['container_width_mm'], 90.0, delta=0.1)
        self.assertEqual(report['images'][0]['status'], 'overwide')

    def test_summary_and_json_cli(self):
        image = self.make_image('wide.png', 1200, 800)
        target, document = self.make_doc()
        set_page(document.sections[0])
        document.add_picture(str(image), width=Mm(170))
        document.save(str(target))

        result = subprocess.run([sys.executable, '-B', str(SCRIPT), str(target)],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        self.assertIn('OVERWIDE', result.stdout)
        self.assertIn('共 1 张图', result.stdout)

        result = subprocess.run([sys.executable, '-B', str(SCRIPT), str(target), '--json'],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
        payload = json.loads(result.stdout)
        self.assertFalse(payload['ok'])
        self.assertEqual(payload['images'][0]['px_width'], 1200)
        self.assertEqual(payload['images'][0]['status'], 'overwide')

    def test_missing_file_is_an_input_error(self):
        result = subprocess.run([sys.executable, '-B', str(SCRIPT), str(self.temp / 'none.docx'), '--json'],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 2)
        self.assertFalse(json.loads(result.stdout)['ok'])


if __name__ == '__main__':
    unittest.main()
