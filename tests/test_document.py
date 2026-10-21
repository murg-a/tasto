import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from tasto.document import Document


class DocumentTests(unittest.TestCase):
    def test_unicode_counts_and_headings(self):
        doc = Document('# Caffè\n\nUna città.\n##### Fine\n###### Ignorato')
        self.assertEqual(doc.counts, (len(doc.text), 8))
        self.assertEqual([(h[0], h[1]) for h in doc.headings], [(1, 'Caffè'), (5, 'Fine')])
        self.assertEqual(doc.text[doc.headings[1][2]:].splitlines()[0], '##### Fine')

    def test_save_and_reopen(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'prova.md'
            doc = Document('Un caffè ☕\n')
            self.assertTrue(doc.modified)
            doc.save(path)
            self.assertFalse(doc.modified)
            other = Document()
            other.open(path)
            self.assertEqual(other.text, doc.text)
            self.assertFalse(other.modified)

    def test_failed_save_preserves_original(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'prova.md'
            path.write_text('originale', encoding='utf-8')
            doc = Document('nuovo')
            with patch('os.replace', side_effect=OSError('disco non disponibile')):
                with self.assertRaises(OSError):
                    doc.save(path)
            self.assertEqual(path.read_text(), 'originale')
            self.assertTrue(doc.modified)
            self.assertEqual(list(Path(folder).iterdir()), [path])

    def test_failed_open_preserves_document(self):
        doc = Document('testo da conservare')
        with self.assertRaises(OSError):
            doc.open('/directory-inesistente/documento.md')
        self.assertEqual(doc.text, 'testo da conservare')


if __name__ == '__main__':
    unittest.main()
