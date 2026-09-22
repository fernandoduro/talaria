"""Tests for loading .env into the environment."""
import os
import tempfile
import unittest
from unittest import mock

from talaria import environment


class TestLoad(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.env = os.path.join(self.d, ".env")

    def _write(self, text):
        with open(self.env, "w", encoding="utf-8") as f:
            f.write(text)

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_reads_simple_pair(self):
        self._write("IG_PAGE_TOKEN=abc123\n")
        environment.load(self.env)
        self.assertEqual(os.environ["IG_PAGE_TOKEN"], "abc123")

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_ignores_comment_and_blank_line(self):
        self._write("# comment\n\nA=1\n   # another\nB=2\n")
        environment.load(self.env)
        self.assertEqual((os.environ.get("A"), os.environ.get("B")), ("1", "2"))

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_empty_value_does_not_enter(self):
        # A variable declared but not filled in is "not configured" — entering
        # as "" would let the credential check pass and the API refuse later,
        # with a worse message.
        self._write("EMPTY=\nFILLED=x\n")
        environment.load(self.env)
        self.assertNotIn("EMPTY", os.environ)
        self.assertEqual(os.environ["FILLED"], "x")

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_strips_quotes_and_spaces(self):
        # Pasting from a console usually brings the quotes along.
        self._write('WITH_QUOTES="abc"\nWITH_SPACE=  def  \nSIMPLE=\'ghi\'\n')
        environment.load(self.env)
        self.assertEqual(os.environ["WITH_QUOTES"], "abc")
        self.assertEqual(os.environ["WITH_SPACE"], "def")
        self.assertEqual(os.environ["SIMPLE"], "ghi")

    @mock.patch.dict("os.environ", {"ALREADY_SET": "from_shell"}, clear=True)
    def test_shell_environment_wins_over_file(self):
        # `IG_PAGE_TOKEN=x python run.py ...` has to override the file, which
        # is how another credential gets tested without editing anything.
        self._write("ALREADY_SET=from_file\n")
        environment.load(self.env)
        self.assertEqual(os.environ["ALREADY_SET"], "from_shell")

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_value_with_equals_inside_stays_whole(self):
        # A base64 token ends in '=' and a URL carries '=' in its query.
        self._write("T=abc=def==\n")
        environment.load(self.env)
        self.assertEqual(os.environ["T"], "abc=def==")

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_missing_file_does_not_blow_up(self):
        # Someone who only renders clips never made a .env — not an error.
        environment.load(os.path.join(self.d, "does_not_exist"))

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_accepts_leading_export(self):
        self._write("export A=1\n")
        environment.load(self.env)
        self.assertEqual(os.environ.get("A"), "1")


if __name__ == "__main__":
    unittest.main()
