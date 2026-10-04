import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import grok_inbox


def stat_line(comm, start="12345"):
    tail = " ".join(
        [
            "S", "1", "1", "1", "0", "-1",
            "0", "0", "0", "0", "0",
            "0", "0", "0", "0",
            "20", "0", "1", "0",
            start,
        ]
    )
    return f"42 ({comm}) {tail}"


class ParseProcStartTest(unittest.TestCase):
    def test_normal_line(self):
        self.assertEqual(grok_inbox.parse_proc_start(stat_line("python", "976344")), "976344")

    def test_comm_with_spaces_and_parentheses(self):
        line = stat_line("grok (review) helper", "22499698")
        self.assertEqual(grok_inbox.parse_proc_start(line), "22499698")

    def test_short_line(self):
        with self.assertRaises(SystemExit):
            grok_inbox.parse_proc_start("42 (python) S 1")

    def test_live_proc_stat(self):
        start = grok_inbox.parse_proc_start(Path("/proc/self/stat").read_text())
        self.assertTrue(start.isdigit())


class DisplayNameTest(unittest.TestCase):
    def test_manual_title_is_used(self):
        summary = {"title_is_manual": True, "generated_title": "  Ada  "}
        self.assertEqual(grok_inbox.name_from_summary(summary, None), "Ada")

    def test_auto_title_is_ignored(self):
        summary = {"title_is_manual": False, "generated_title": "Auto title"}
        self.assertIsNone(grok_inbox.name_from_summary(summary, None))

    def test_missing_summary_is_ignored(self):
        self.assertIsNone(grok_inbox.name_from_summary(None, None))
        self.assertIsNone(grok_inbox.name_from_summary({"generated_title": "Auto"}, None))

    def test_explicit_name_wins(self):
        summary = {"title_is_manual": True, "generated_title": "Other"}
        self.assertEqual(grok_inbox.name_from_summary(summary, "  Chosen  "), "Chosen")

    def test_unsafe_titles_are_refused(self):
        for name in ['say "hi"', "a&b", "a<b", "a>b", "line\nbreak", "tab\there"]:
            with self.subTest(name=name):
                with self.assertRaises(SystemExit) as caught:
                    grok_inbox.validate_display_name(name)
                self.assertIn("cannot contain", str(caught.exception))

    def test_blank_name_is_refused(self):
        with self.assertRaises(SystemExit) as caught:
            grok_inbox.validate_display_name("  ")
        self.assertIn("no display name", str(caught.exception))


class NoteTest(unittest.TestCase):
    def test_prepends_greeting(self):
        out = grok_inbox.note("Ada", "hello", "/tmp/ada.sock")
        self.assertIn('from-name="Ada"', out)
        self.assertIn("Ada here.\n\nhello", out)

    def test_does_not_prepend_twice(self):
        out = grok_inbox.note("Ada", "Ada here.\n\nalready", "/tmp/ada.sock")
        self.assertEqual(out.count("Ada here."), 1)

    def test_empty_text_is_only_the_greeting(self):
        expected = (
            '<cross-session-message from="uds:/tmp/ada.sock" from-name="Ada" '
            'from-mode="prompting">\nAda here.\n</cross-session-message>\n'
        )
        self.assertEqual(grok_inbox.note("Ada", "", "/tmp/ada.sock"), expected)
        self.assertEqual(grok_inbox.note("Ada", "\n\n", "/tmp/ada.sock"), expected)

    def test_attribute_is_the_raw_name(self):
        out = grok_inbox.note("Ada Smith", "a < b & c", "/tmp/ada.sock")
        self.assertIn('from-name="Ada Smith"', out)
        self.assertIn("a < b & c", out)


class RequireOneTest(unittest.TestCase):
    def test_zero_hits(self):
        with self.assertRaises(SystemExit) as caught:
            grok_inbox.require_one("bluey", [], "Claude session")
        self.assertIn("no live Claude session named bluey", str(caught.exception))

    def test_one_hit(self):
        hit = {"pid": 7, "version": "grok"}
        self.assertIs(grok_inbox.require_one("bluey", [hit], "inbox"), hit)

    def test_two_hits_differ_from_zero(self):
        hits = [
            {"pid": 7, "version": "grok"},
            {"pid": 8, "version": "2.1.287"},
        ]
        with self.assertRaises(SystemExit) as caught:
            grok_inbox.require_one("bluey", hits, "inbox")
        message = str(caught.exception)
        self.assertIn("more than one live inbox named bluey", message)
        self.assertIn("7 (grok)", message)
        self.assertIn("8 (2.1.287)", message)
        self.assertNotIn("no live", message)


class GrokInboxTest(unittest.TestCase):
    def test_grok_version_is_accepted(self):
        meta = {"pid": 5, "version": "grok"}
        self.assertIs(grok_inbox.require_grok_inbox(meta, "Ada"), meta)

    def test_other_version_is_refused(self):
        meta = {"pid": 5, "version": "2.1.287"}
        with self.assertRaises(SystemExit) as caught:
            grok_inbox.require_grok_inbox(meta, "Ada")
        message = str(caught.exception)
        self.assertIn("pid 5", message)
        self.assertIn("2.1.287", message)
        self.assertIn("already a live session", message)


class WritePrivateTest(unittest.TestCase):
    def test_file_is_mode_600(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "key"
            grok_inbox.write_private(path, "secret")
            self.assertEqual(path.read_text(), "secret")
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


if __name__ == "__main__":
    unittest.main()
