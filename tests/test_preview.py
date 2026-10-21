import unittest
from tasto.preview import parse, active_lines


def visible(line):
    return ''.join(char for i, char in enumerate(line.text)
                   if not any(a <= i < b for a, b in line.hidden))


class PreviewTests(unittest.TestCase):
    def test_formatting_and_unicode_offsets(self):
        line = parse('# Caffè **caldo** e _buono_')[0]
        self.assertEqual(visible(line), 'Caffè caldo e buono')
        self.assertIn(('bold', 10, 15), line.spans)
        self.assertEqual(line.heading, (1, 'Caffè **caldo** e _buono_', 0))

    def test_html_is_a_small_literal_whitelist(self):
        self.assertEqual(visible(parse('<u>caffè</u> e <strong>forte</strong>')[0]), 'caffè e forte')
        text = '<script>alert(1)</script> <img src="x"> <b onclick="x">testo</b>'
        self.assertEqual(visible(parse(text)[0]), text)

    def test_code_and_escapes_protect_markdown(self):
        line = parse(r'`**letterale**` e \*testo\*')[0]
        self.assertEqual(visible(line), '**letterale** e *testo*')
        self.assertEqual([span[0] for span in line.spans], ['code'])
        self.assertEqual(visible(parse('    **letterale**')[0]), '    **letterale**')

    def test_link_nested_formatting_and_footnotes(self):
        line = parse('[**caffè**](https://example.com) e ~~via~~ <u>_qui_</u>[^1]')[0]
        self.assertEqual(visible(line), 'caffè e via qui[^1]')
        self.assertIn('footnote', [span[0] for span in line.spans])

    def test_fences_require_matching_marker_and_length(self):
        lines = parse('prima\n````md\n**letterale**\n```\n~~~~\n````\ndopo')
        self.assertEqual(active_lines(lines, 2, 2), set(range(1, 6)))
        self.assertEqual(visible(lines[2]), '**letterale**')
        self.assertEqual(visible(lines[3]), '```')
        self.assertEqual(visible(lines[1]), '')
        self.assertEqual(active_lines(lines, 0, 0), {0})

    def test_unclosed_fence_and_selection(self):
        lines = parse('prima\n~~~\n**codice**\nfine')
        self.assertEqual(active_lines(lines, 0, 2), {0, 1, 2, 3})
        self.assertEqual(lines[-1].block, (1, 3))

    def test_incomplete_syntax_images_and_intraword_underscores_stay_visible(self):
        for text in ('**aperto', '<u>aperto', '![foto](url)', 'nome_file_test', '**'):
            self.assertEqual(visible(parse(text)[0]), text)
