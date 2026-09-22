"""Testes do upload de Shorts (YouTube Data API mockada)."""
import json
import os
import tempfile
import unittest
from unittest import mock

from talaria import publish_youtube


def _client_secret(d):
    path = os.path.join(d, "client_secret.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"installed": {
            "client_id": "cid", "client_secret": "cs",
            "token_uri": "https://oauth2.googleapis.com/token"}}, f)
    return path


class TestCredentials(unittest.TestCase):
    @mock.patch.dict("os.environ", {}, clear=True)
    def test_sem_credencial_diz_qual_variavel_e_o_script(self):
        with self.assertRaises(RuntimeError) as ctx:
            publish_youtube.upload("/tmp/v.mp4", "t", "d")
        self.assertIn("YT_CLIENT_SECRET_PATH", str(ctx.exception))
        self.assertIn("youtube_auth", str(ctx.exception))


class TestUpload(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.env = {"YT_CLIENT_SECRET_PATH": _client_secret(self.d),
                    "YT_REFRESH_TOKEN": "rt"}

    @mock.patch("talaria.publish_youtube.MediaFileUpload")
    @mock.patch("talaria.publish_youtube.build")
    def test_upload_devolve_id_e_url_de_short(self, build_mock, media_mock):
        with mock.patch.dict("os.environ", self.env):
            insert = build_mock.return_value.videos.return_value.insert
            insert.return_value.next_chunk.return_value = (None, {"id": "V1D"})
            r = publish_youtube.upload("/tmp/v.mp4", "Titulo", "Descricao")
        self.assertEqual(r, {"id": "V1D",
                             "url": "https://www.youtube.com/shorts/V1D"})
        body = insert.call_args.kwargs["body"]
        self.assertEqual(body["snippet"]["title"], "Titulo")
        self.assertEqual(body["snippet"]["description"], "Descricao")
        self.assertEqual(body["status"]["privacyStatus"], "public")


class TestPrivacy(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.env = {"YT_CLIENT_SECRET_PATH": _client_secret(self.d),
                    "YT_REFRESH_TOKEN": "rt"}

    def _put(self, extra_env):
        with mock.patch.dict("os.environ", {**self.env, **extra_env}):
            with mock.patch("talaria.publish_youtube.MediaFileUpload"), \
                 mock.patch("talaria.publish_youtube.build") as build_mock:
                insert = build_mock.return_value.videos.return_value.insert
                insert.return_value.next_chunk.return_value = (None, {"id": "V"})
                publish_youtube.upload("/tmp/v.mp4", "T", "D")
                return insert.call_args.kwargs["body"]["status"]

    def test_sem_a_variavel_continua_publico(self):
        # O default não muda: quem não configurou nada publica como sempre.
        self.assertEqual(self._put({})["privacyStatus"], "public")

    def test_unlisted_permite_conferir_antes_de_abrir(self):
        self.assertEqual(self._put({"YT_PRIVACY": "unlisted"})["privacyStatus"],
                         "unlisted")

    def test_private_tambem_vale(self):
        self.assertEqual(self._put({"YT_PRIVACY": "private"})["privacyStatus"],
                         "private")

    def test_valor_invalido_aborta_em_vez_de_publicar_publico(self):
        # Um typo ("unlised", "publico") não pode virar publicação pública
        # em silêncio: o vídeo iria ao ar aberto quando se pediu o contrário.
        with self.assertRaises(ValueError) as ctx:
            self._put({"YT_PRIVACY": "unlised"})
        self.assertIn("unlised", str(ctx.exception))

    def test_espaco_e_caixa_nao_atrapalham(self):
        self.assertEqual(self._put({"YT_PRIVACY": " Unlisted "})["privacyStatus"],
                         "unlisted")


if __name__ == "__main__":
    unittest.main()
