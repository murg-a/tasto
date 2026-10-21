import unittest
from tasto.formatting import format_edit


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
