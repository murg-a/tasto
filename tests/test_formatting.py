import unittest
from tasto.formatting import format_edit, list_newline_edit


def apply(text, start, end, command):
    a, b, replacement, x, y = format_edit(text, start, end, command)
    return text[:a] + replacement + text[b:], (a+x, a+y)


class FormattingTests(unittest.TestCase):
    def test_inline_preserves_surroundings_and_selection(self):
        result, selection = apply('Un caffè caldo', 3, 8, 'bold')
        self.assertEqual(result, 'Un **caffè** caldo')
        self.assertEqual(result[slice(*selection)], 'caffè')

    def test_empty_selection_positions_cursor_inside_markers(self):
        for command, expected, position in [('bold', '****', 2), ('italic', '__', 1),
                                            ('underline', '<u></u>', 3), ('strike', '~~~~', 2)]:
            self.assertEqual(apply('', 0, 0, command), (expected, (position, position)))

    def test_remove_selected_wrappers(self):
        self.assertEqual(apply('**ciao**', 0, 8, 'bold'), ('ciao', (0, 4)))

    def test_numbered_list_excludes_next_unselected_line(self):
        self.assertEqual(apply('uno\ndue\ntre', 0, 8, 'number'),
                         ('1. uno\n2. due\ntre', (0, 13)))

    def test_list_converts_existing_prefixes(self):
        self.assertEqual(apply('  - uno\n  - due', 0, 15, 'number')[0],
                         '  1. uno\n  2. due')

    def test_indent_and_outdent_preserve_following_line(self):
        text = 'uno\ndue\ntre'
        indented, bounds = apply(text, 0, 8, 'indent')
        self.assertEqual(indented, '    uno\n    due\ntre')
        self.assertEqual(apply(indented, *bounds, 'outdent')[0], text)

    def test_list_at_cursor_leaves_other_lines_untouched(self):
        self.assertEqual(apply('uno\ndue', 5, 5, 'bullet'), ('uno\n- due', (7, 7)))

    def test_last_empty_line_can_start_list(self):
        self.assertEqual(apply('uno\n', 4, 4, 'bullet'), ('uno\n- ', (6, 6)))


class ListNewlineTests(unittest.TestCase):
    def enter(self, text, start=None, end=None):
        start = len(text) if start is None else start
        end = start if end is None else end
        edit = list_newline_edit(text, start, end)
        if edit is None:
            return None
        a, b, replacement = edit
        return text[:a] + replacement + text[b:], a + len(replacement)

    def test_bullet_preserves_marker_and_indentation(self):
        for prefix in ('- ', '+ ', '* ', '  - ', '  *  '):
            text = prefix + 'caffè'
            self.assertEqual(self.enter(text), (text + '\n' + prefix, len(text) + 1 + len(prefix)))

    def test_number_increments_and_preserves_delimiter(self):
        for text, next_prefix in [('9. voce', '10. '), ('19) voce', '20) '),
                                  ('  2. voce', '  3. '), ('009. voce', '010. ')]:
            self.assertEqual(self.enter(text)[0], text + '\n' + next_prefix)

    def test_empty_item_exits_without_adding_a_blank_item(self):
        for prefix, expected in [('- ', ''), ('12. ', ''), ('  +  ', '  '), ('3)', '')]:
            self.assertEqual(self.enter('prima\n' + prefix), ('prima\n' + expected, 6 + len(expected)))

    def test_enter_splits_a_list_item_at_the_cursor(self):
        self.assertEqual(self.enter('3. caffè caldo', 8), ('3. caffè\n4.  caldo', 12))

    def test_single_line_selection_is_replaced(self):
        self.assertEqual(self.enter('- uno due tre', 5, 9), ('- uno\n-  tre', 8))

    def test_selection_touching_marker_or_other_lines_uses_native_enter(self):
        for text, start, end in [('- voce', 0, 3), ('- voce\n- altra', 3, 10)]:
            self.assertIsNone(self.enter(text, start, end))

    def test_code_fences_and_indented_code_do_not_continue_lists(self):
        for text, cursor in [('```md\n- codice\n```', 14), ('~~~\n1. codice', 13),
                             ('    - codice', 12), ('\t1. codice', 10)]:
            self.assertIsNone(self.enter(text, cursor))

    def test_plain_text_quotes_and_thematic_breaks_are_unchanged(self):
        for text in ('testo', '> citazione', '---', '* * *', '- - -', r'\- letterale'):
            self.assertIsNone(self.enter(text))

    def test_following_paragraph_is_preserved(self):
        self.assertEqual(self.enter('- voce\nseguito', 6), ('- voce\n- \nseguito', 9))
