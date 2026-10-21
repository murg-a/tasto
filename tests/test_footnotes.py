import unittest
from tasto.footnotes import add_note, notes, update_note, reference_offset


class FootnoteTests(unittest.TestCase):
    def test_insert_at_cursor_with_unique_number(self):
        text = 'Caffè[^3].\n\n[^3]: prima nota\n'
        updated, cursor, number = add_note(text, 5)
        self.assertEqual(number, '4')
        self.assertTrue(updated.startswith('Caffè[^4][^3].'))
        self.assertEqual(cursor, 9)
        self.assertEqual([n.number for n in notes(updated)], ['3', '4'])

    def test_multiline_round_trip_preserves_other_text(self):
        text, _, number = add_note('Un testo.', 2)
        updated = update_note(text, number, 'Caffè\n\nSecondo paragrafo ☕')
        self.assertEqual(notes(updated)[0].content, 'Caffè\n\nSecondo paragrafo ☕')
        self.assertTrue(updated.startswith('Un[^1] testo.'))
        self.assertEqual(update_note(updated, number, 'Nuova'), 'Un[^1] testo.\n\n[^1]: Nuova\n')

    def test_empty_note_and_missing_definition(self):
        self.assertEqual(notes('[^1]: \n')[0].content, '')
        with self.assertRaises(ValueError):
            update_note('Testo senza note', '1', 'nuova')

    def test_code_blocks_are_not_notes(self):
        text = '```markdown\n[^1]: esempio\n```\n\n[^2]: nota vera\n'
        self.assertEqual([n.number for n in notes(text)], ['2'])

    def test_duplicate_definitions_do_not_overwrite(self):
        with self.assertRaises(ValueError):
            update_note('[^1]: prima\n[^1]: seconda\n', '1', 'nuova')

    def test_unresolved_references_reserve_number(self):
        self.assertEqual(add_note('Testo[^9]', 0)[2], '10')

    def test_edit_preserves_following_paragraph(self):
        original = '[^1]: nota\n    seconda riga\n\nAltro testo.\n'
        self.assertEqual(update_note(original, '1', 'nuova'), '[^1]: nuova\n\nAltro testo.\n')


class ReferenceTests(unittest.TestCase):
    def test_returns_body_reference_not_definition(self):
        text = "[^1]: definizione\n\nUn caffè[^1]."
        self.assertEqual(reference_offset(text, '1'), text.rindex('[^1]'))

    def test_ignores_code_and_escaped_references(self):
        text = "```\n[^2]\n```\n`[^2]` e \\[^2], poi testo[^2].\n\n[^2]: nota\n"
        self.assertEqual(reference_offset(text, '2'), text.index('testo') + 5)

    def test_ignores_references_inside_note_content(self):
        text = "[^1]: vedi [^2]\n    anche [^2]\n\nIl testo[^2].\n[^2]: due\n"
        self.assertEqual(reference_offset(text, '2'), text.index('testo') + 5)

    def test_missing_reference_is_explicit(self):
        self.assertIsNone(reference_offset('[^1]: sola definizione\n', '1'))

    def test_first_reference_is_selected_when_reused(self):
        self.assertEqual(reference_offset('A[^1] e B[^1]', '1'), 1)
