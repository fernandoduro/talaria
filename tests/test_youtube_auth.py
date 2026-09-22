import importlib.util
import json
import os
import tempfile
import unittest

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SPEC = importlib.util.spec_from_file_location(
    "youtube_auth", os.path.join(_ROOT, "scripts", "youtube_auth.py"))
youtube_auth = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(youtube_auth)


def _write(d, content):
    path = os.path.join(d, "cs.json")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


class TestValidateClientSecret(unittest.TestCase):
    """publish reads client_secret["installed"]: a Web client passes the consent
    flow and only breaks on the first upload. Failing here is the point."""

    def test_accepts_a_desktop_client(self):
        with tempfile.TemporaryDirectory() as d:
            data = {"installed": {"client_id": "x", "client_secret": "y",
                                   "token_uri": "https://oauth2.example/token"}}
            path = _write(d, json.dumps(data))
            self.assertEqual(youtube_auth.validate_client_secret(path),
                             data["installed"])

    def test_refuses_a_web_client_saying_what_to_do(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, json.dumps({"web": {"client_id": "x"}}))
            with self.assertRaises(SystemExit) as ctx:
                youtube_auth.validate_client_secret(path)
            self.assertIn("Desktop", str(ctx.exception))

    def test_refuses_invalid_json(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, "nao e json {")
            with self.assertRaises(SystemExit) as ctx:
                youtube_auth.validate_client_secret(path)
            self.assertIn("Baixe", str(ctx.exception))

    def test_refuses_a_missing_file(self):
        with self.assertRaises(SystemExit) as ctx:
            youtube_auth.validate_client_secret("/nao/existe.json")
        self.assertIn("comando", str(ctx.exception))

    def test_refuses_a_truncated_installed_block(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, json.dumps({"installed": {"client_id": "x"}}))
            with self.assertRaises(SystemExit) as ctx:
                youtube_auth.validate_client_secret(path)
            msg = str(ctx.exception)
            self.assertIn("incompleto", msg)
            self.assertIn("client_secret", msg)
            self.assertIn("token_uri", msg)

    def test_refuses_json_that_is_not_an_object(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, "42")
            with self.assertRaises(SystemExit):
                youtube_auth.validate_client_secret(path)

    def test_the_scope_is_exactly_the_publish_one(self):
        from talaria import publish_youtube
        self.assertEqual(youtube_auth.SCOPES, publish_youtube.SCOPES)


class TestMain(unittest.TestCase):
    def test_a_wrong_number_of_arguments_explains_the_usage(self):
        for argv in ([], ["cs.json", "sobrando"]):
            with self.subTest(argv=argv):
                with self.assertRaises(SystemExit) as ctx:
                    youtube_auth.main(argv)
                self.assertIn("uso:", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
