"""Synthetic validator regressions; no real secrets or private source data."""
import tempfile
import unittest
from pathlib import Path

from validate_docs import anchors, links, prose_and_fences, validate


class DocumentationChecks(unittest.TestCase):
    def check_files(self, files):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name, text in files.items():
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text)
            return validate(root, [Path(name) for name in files])

    def test_valid_link(self):
        self.assertEqual(self.check_files({'README.md': '[Page](page.md#hello)', 'page.md': '# Hello'}), [])

    def test_missing_link(self):
        self.assertTrue(self.check_files({'README.md': '[Missing](missing.md)'}))

    def test_escape(self):
        self.assertTrue(self.check_files({'README.md': '[Escape](../outside.md)'}))

    def test_missing_anchor(self):
        self.assertTrue(self.check_files({'README.md': '[Page](page.md#missing)', 'page.md': '# Hello'}))

    def test_fences(self):
        self.assertTrue(prose_and_fences('```text\nunclosed')[2])
        self.assertFalse(prose_and_fences('~~~~text\n```\n~~~~')[2])
        self.assertEqual(prose_and_fences('```mermaid\nflowchart LR\n```')[1], ['flowchart LR'])

    def test_reference_and_image(self):
        self.assertEqual(links('![image](a.png)\n[ref]: b.md'), ['a.png', 'b.md'])

    def test_duplicate_headings(self):
        self.assertEqual(anchors('# Hello\n## Hello'), {'hello', 'hello-1'})

    def test_safety(self):
        value = '/' + 'Users' + '/example/private'
        self.assertTrue(self.check_files({'README.md': value}))

    def test_python_syntax(self):
        self.assertTrue(self.check_files({'invalid.py': 'def broken('}))

    def test_yaml_syntax(self):
        self.assertTrue(self.check_files({'invalid.yaml': 'value: [unfinished'}))

    def test_fenced_yaml(self):
        self.assertTrue(self.check_files({"README.md": "```yaml\nvalue: [unfinished\n```"}))

    def test_valid_yaml(self):
        self.assertEqual(self.check_files({"valid.yaml": "value: [one, two]"}), [])

    def test_svg_syntax(self):
        self.assertTrue(self.check_files({"invalid.svg": "<svg>"}))

    def test_token_detection(self):
        self.assertTrue(self.check_files({"README.md": "gh" + "p_" + "a" * 30}))

    def test_navigation(self):
        self.assertTrue(self.check_files({'docs/design/new.md': '# New', 'docs/README.md': '# Index'}))

    def test_unpublished_target(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'README.md').write_text('[Hidden](hidden.md)')
            (root / 'hidden.md').write_text('# Hidden')
            self.assertTrue(validate(root, [Path('README.md')]))


if __name__ == '__main__':
    unittest.main()
