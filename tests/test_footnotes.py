import unittest
from tasto.footnotes import add_note, notes, update_note, reference_offset, references, synchronize_notes, reconcile_notes


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


class SynchronizationTests(unittest.TestCase):
    def test_new_note_before_fifth_keeps_contents_associated(self):
        before = ' '.join(f'P{i}[^{i}]' for i in range(1, 6)) + '\n\n'
        before += ''.join(f'[^{i}]: nota {i}\n' for i in range(1, 6))
        added, cursor, temporary = add_note(before, before.index('P5'))
        updated, cursor, mapping = synchronize_notes(added, cursor)
        self.assertEqual(mapping[temporary], '5')
        self.assertEqual([r.number for r in references(updated)], ['1', '2', '3', '4', '5', '6'])
        self.assertEqual({n.number: n.content for n in notes(updated)}['6'], 'nota 5')
        self.assertEqual(updated[cursor-4:cursor], '[^5]')

    def test_reordering_renumbers_simultaneously(self):
        text = 'B[^2] A[^1]\n\n[^1]: alfa\n[^2]: beta\n'
        updated, _, _ = synchronize_notes(text)
        self.assertTrue(updated.startswith('B[^1] A[^2]'))
        self.assertEqual({n.number: n.content for n in notes(updated)}, {'2': 'alfa', '1': 'beta'})
        self.assertEqual(synchronize_notes(updated)[0], updated)

    def test_remove_last_reference_removes_definition_and_closes_gap(self):
        before = 'A[^1] B[^2] C[^3]\n\n[^1]: alfa\n[^2]: beta\n    seguito\n[^3]: gamma\n'
        updated, _, _ = reconcile_notes(before, before.replace('B[^2]', 'B'), 8)
        self.assertTrue(updated.startswith('A[^1] B C[^2]'))
        self.assertEqual({n.number: n.content for n in notes(updated)}, {'1': 'alfa', '2': 'gamma'})
        self.assertNotIn('seguito', updated)

    def test_reused_reference_keeps_note_until_last_removed(self):
        before = 'A[^1] B[^1]\n\n[^1]: stessa nota\n'
        updated, _, _ = reconcile_notes(before, before.replace('A[^1]', 'A'), 1)
        self.assertEqual(notes(updated)[0].content, 'stessa nota')
        self.assertEqual(len(references(updated)), 1)

    def test_imported_orphan_content_is_not_deleted(self):
        text = 'Testo\n\n[^8]: da recuperare\n'
        updated, _, _ = synchronize_notes(text)
        self.assertEqual(notes(updated)[0].content, 'da recuperare')

    def test_removing_complete_definition_removes_its_reference(self):
        before = 'A[^1] B[^2]\n\n[^1]: alfa\n[^2]: beta\n'
        after = before.replace('[^1]: alfa\n', '')
        updated, _, _ = reconcile_notes(before, after, 0)
        self.assertTrue(updated.startswith('A B[^1]'))
        self.assertEqual(notes(updated)[0].content, 'beta')

    def test_partial_marker_edit_does_not_destroy_or_reassign_notes(self):
        before = 'A[^1] B[^2]\n\n[^1]: alfa\n[^2]: beta\n'
        after = before.replace('A[^1]', 'A[^1')
        self.assertEqual(reconcile_notes(before, after, 4)[0], after)

    def test_code_examples_not_renumbered(self):
        text = '`[^9]` vero[^9]\n\n[^9]: nota\n'
        updated, _, _ = synchronize_notes(text)
        self.assertTrue(updated.startswith('`[^9]` vero[^1]'))

    def test_cursor_after_two_digit_reference_is_mapped(self):
        text = 'a[^12]b\n\n[^12]: caffè\n'
        updated, cursor, _ = synchronize_notes(text, text.index('b'))
        self.assertEqual(updated[cursor], 'b')
        self.assertTrue(updated.startswith('a[^1]b'))

    def test_duplicate_definitions_are_preserved(self):
        text = 'A[^2]\n\n[^2]: alfa\n[^2]: beta\n'
        self.assertEqual(synchronize_notes(text)[0], text)


    def test_adjacent_references_use_exact_deleted_token(self):
        before = 'A[^1][^2]\n\n[^1]: alfa\n[^2]: beta\n'
        after = before.replace('A[^1]', 'A')
        updated, _, _ = reconcile_notes(before, after, 1, deleted_references={'1'})
        self.assertTrue(updated.startswith('A[^1]'))
        self.assertEqual([n.content for n in notes(updated)], ['beta'])

    def test_replacing_selection_with_same_reference_keeps_content(self):
        text = 'A[^1]\n\n[^1]: alfa\n'
        self.assertEqual(reconcile_notes(text, text, 5, deleted_references={'1'})[0], text)
