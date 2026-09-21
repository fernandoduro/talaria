import importlib.util
import json
import os
import tempfile
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SPEC = importlib.util.spec_from_file_location(
    "youtube_auth", os.path.join(_RAIZ, "scripts", "youtube_auth.py"))
youtube_auth = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(youtube_auth)


def _escreve(d, conteudo):
    caminho = os.path.join(d, "cs.json")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(conteudo)
    return caminho


class TestValidaClientSecret(unittest.TestCase):
    """O publish lê client_secret["installed"]: um client Web passa pelo
    consentimento e só quebra no primeiro upload. Falhar aqui é o ponto."""

    def test_aceita_client_desktop(self):
        with tempfile.TemporaryDirectory() as d:
            dados = {"installed": {"client_id": "x", "client_secret": "y",
                                   "token_uri": "https://oauth2.example/token"}}
            caminho = _escreve(d, json.dumps(dados))
            self.assertEqual(youtube_auth.valida_client_secret(caminho),
                             dados["installed"])

    def test_recusa_client_web_dizendo_o_que_fazer(self):
        with tempfile.TemporaryDirectory() as d:
            caminho = _escreve(d, json.dumps({"web": {"client_id": "x"}}))
            with self.assertRaises(SystemExit) as ctx:
                youtube_auth.valida_client_secret(caminho)
            self.assertIn("Desktop", str(ctx.exception))

    def test_recusa_json_invalido(self):
        with tempfile.TemporaryDirectory() as d:
            caminho = _escreve(d, "nao e json {")
            with self.assertRaises(SystemExit) as ctx:
                youtube_auth.valida_client_secret(caminho)
            self.assertIn("Console", str(ctx.exception))

    def test_recusa_arquivo_ausente(self):
        with self.assertRaises(SystemExit) as ctx:
            youtube_auth.valida_client_secret("/nao/existe.json")
        self.assertIn("comando", str(ctx.exception))

    def test_recusa_json_nao_objeto(self):
        with tempfile.TemporaryDirectory() as d:
            caminho = _escreve(d, "42")
            with self.assertRaises(SystemExit):
                youtube_auth.valida_client_secret(caminho)

    def test_escopo_e_exatamente_o_do_publish(self):
        from talaria import publish_youtube
        self.assertEqual(youtube_auth.ESCOPO, publish_youtube.ESCOPO)


class TestMain(unittest.TestCase):
    def test_sem_argumento_explica_o_uso(self):
        with self.assertRaises(SystemExit):
            youtube_auth.main([])


if __name__ == "__main__":
    unittest.main()
