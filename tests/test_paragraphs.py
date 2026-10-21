import unittest
from tasto.paragraphs import blocks, insert_block


class ParagraphTests(unittest.TestCase):
    def test_unicode_and_offsets(self):
        text = 'È il primo.\nAltra riga.\n\n\nSecondo.'
        result = blocks(text)
        self.assertEqual([b.text for b in result], ['È il primo.\nAltra riga.\n', 'Secondo.'])
        for b in result:
            self.assertEqual(text[b.start:b.end], b.text)

    def test_code_blank_lines_and_short_closing_fence(self):
        text = 'Prima\n\n````python\na\n\n```\nb\n````\n\nDopo'
        result = blocks(text)
        self.assertEqual(len(result), 3)
        self.assertIn('a\n\n```\nb', result[1].text)

    def test_insert_exact_position_creates_paragraphs(self):
        text, _ = insert_block('abcdef', 3, 'Card\n')
        self.assertEqual(text, 'abc\n\nCard\n\ndef')

    def test_insert_boundaries(self):
        self.assertEqual(insert_block('', 0, 'Card\n')[0], 'Card')
        self.assertEqual(insert_block('Testo\n\n', 7, 'Card')[0], 'Testo\n\nCard')
        self.assertEqual(blocks('\n \n'), [])


if __name__ == '__main__':
    unittest.main()
