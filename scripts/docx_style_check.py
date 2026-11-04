#!/usr/bin/env python3
"""Heuristic check for heading font/size upgrades in OOXML (standard library only).

Flags paragraphs that look like headings when a run sets an eastAsia font naming
黑体/SimHei or a size larger than the declared body baseline. This reads XML only;
it does not render pages, inspect every inherited style, or certify Word output.
"""
import argparse
import json
from pathlib import Path
import sys
import zipfile
import xml.etree.ElementTree as ET

WORD = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
W = '{' + WORD + '}'
DOCUMENT_PART = 'word/document.xml'


def is_heading(paragraph):
    properties = paragraph.find(W + 'pPr')
    if properties is None:
        return False
    style = properties.find(W + 'pStyle')
    if style is not None:
        value = style.get(W + 'val') or ''
        if 'heading' in value.lower() or '标题' in value:
            return True
    return properties.find(W + 'outlineLvl') is not None


def run_violations(run, baseline_half_points):
    results = []
    properties = run.find(W + 'rPr')
    if properties is None:
        return results
    fonts = properties.find(W + 'rFonts')
    if fonts is not None:
        east_asia = fonts.get(W + 'eastAsia') or fonts.get(W + 'ascii')
        if east_asia and ('黑体' in east_asia or 'simhei' in east_asia.lower()):
            results.append({'kind': 'eastAsia_font', 'value': east_asia})
    size = properties.find(W + 'sz')
    if size is not None:
        try:
            half_points = int(size.get(W + 'val'))
        except (TypeError, ValueError):
            half_points = None
        if half_points is not None and half_points > baseline_half_points:
            results.append({'kind': 'size_upgrade', 'value': half_points / 2})
    return results


def find_violations(xml_bytes, baseline_half_points=24):
    """Return one record per heading run with a black-font or oversized run."""
    root = ET.fromstring(xml_bytes)
    records = []
    for paragraph in root.iter(W + 'p'):
        if not is_heading(paragraph):
            continue
        text = ''.join(node.text or '' for node in paragraph.iter(W + 't'))
        for run in paragraph.iter(W + 'r'):
            for violation in run_violations(run, baseline_half_points):
                records.append(dict(paragraph=text, **violation))
    return records


def read_document_xml(source):
    if zipfile.is_zipfile(source):
        with zipfile.ZipFile(source) as archive:
            return archive.read(DOCUMENT_PART)
    return source.read_bytes()


def main(argv=None):
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'):
            stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='DOCX file or raw word/document.xml')
    parser.add_argument('--baseline-pt', type=float, default=12.0, help='Declared body size in points (default 12)')
    parser.add_argument('--json', action='store_true', help='Print the violation list as JSON')
    args = parser.parse_args(argv)
    try:
        records = find_violations(read_document_xml(args.source), round(args.baseline_pt * 2))
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as error:
        print(json.dumps({'ok': False, 'error': str(error)}, ensure_ascii=False))
        return 2
    if args.json:
        print(json.dumps({'ok': not records, 'violations': records}, ensure_ascii=False))
    else:
        for record in records:
            print('VIOLATION ' + record['paragraph'] + ': ' + record['kind'] + '=' + str(record['value']))
    return 1 if records else 0


if __name__ == '__main__':
    sys.exit(main())
