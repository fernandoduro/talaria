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
    """O publish lê client_secret["installed"]: um client Web passa pelo
    consentimento e só quebra no primeiro upload. Falhar aqui é o ponto."""

    def test_aceita_client_desktop(self):
        with tempfile.TemporaryDirectory() as d:
            data = {"installed": {"client_id": "x", "client_secret": "y",
                                   "token_uri": "https://oauth2.example/token"}}
            path = _write(d, json.dumps(data))
            self.assertEqual(youtube_auth.validate_client_secret(path),
                             data["installed"])

    def test_recusa_client_web_dizendo_o_que_fazer(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, json.dumps({"web": {"client_id": "x"}}))
            with self.assertRaises(SystemExit) as ctx:
                youtube_auth.validate_client_secret(path)
            self.assertIn("Desktop", str(ctx.exception))

    def test_recusa_json_invalido(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, "nao e json {")
            with self.assertRaises(SystemExit) as ctx:
                youtube_auth.validate_client_secret(path)
            self.assertIn("Baixe", str(ctx.exception))

    def test_recusa_arquivo_ausente(self):
        with self.assertRaises(SystemExit) as ctx:
            youtube_auth.validate_client_secret("/nao/existe.json")
        self.assertIn("comando", str(ctx.exception))

    def test_recusa_installed_truncado(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, json.dumps({"installed": {"client_id": "x"}}))
            with self.assertRaises(SystemExit) as ctx:
                youtube_auth.validate_client_secret(path)
            msg = str(ctx.exception)
            self.assertIn("incompleto", msg)
            self.assertIn("client_secret", msg)
            self.assertIn("token_uri", msg)

    def test_recusa_json_nao_objeto(self):
        with tempfile.TemporaryDirectory() as d:
            path = _write(d, "42")
            with self.assertRaises(SystemExit):
                youtube_auth.validate_client_secret(path)

    def test_escopo_e_exatamente_o_do_publish(self):
        from talaria import publish_youtube
        self.assertEqual(youtube_auth.SCOPES, publish_youtube.SCOPES)


class TestMain(unittest.TestCase):
    def test_numero_errado_de_argumentos_explica_o_uso(self):
        for argv in ([], ["cs.json", "sobrando"]):
            with self.subTest(argv=argv):
                with self.assertRaises(SystemExit) as ctx:
                    youtube_auth.main(argv)
                self.assertIn("uso:", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
