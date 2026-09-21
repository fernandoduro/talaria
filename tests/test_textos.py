"""Testes da leitura de textos.json para a thumbnail."""
import inspect
import json
import os
import tempfile
import unittest

from talaria import layout, textos, thumbnail


class TestTextos(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        with open(os.path.join(self.d, "episodio.json"), "w", encoding="utf-8") as f:
            json.dump({
                "temporada": 2, "episodio": 7, "empresa": "Norvik",
                "cidade": "São Gonçalo", "uf": "SP",
                "convidados": [{"nome": "Daniel", "cargo": "sócio", "linkedin": ""}],
            }, f)

    def test_thumb_args_a_partir_do_episodio(self):
        args = textos.thumb_args(self.d)
        self.assertEqual(args["l1"], "Norvik")
        self.assertEqual(args["l2"], "T2E07")
        self.assertIn("São Gonçalo", args["subtitulo"])
        self.assertIn("Daniel", args["creditos"])

    def test_textos_json_sobrescreve_episodio(self):
        with open(layout.garante(layout.textos(self.d)), "w", encoding="utf-8") as f:
            json.dump({"thumb": {"l1": "CUSTOMIZADO", "l2": "T2E07"}}, f)
        args = textos.thumb_args(self.d)
        self.assertEqual(args["l1"], "CUSTOMIZADO")

    def test_selo_tem_codigo_do_episodio(self):
        args = textos.thumb_args(self.d)
        self.assertIn("T2E07", args["selo"])

    def test_salvar_e_ler(self):
        textos.save(self.d, {"titulo": "X", "descricao": "Y"})
        t = textos.load(self.d)
        self.assertEqual(t["titulo"], "X")

    def test_load_sem_arquivo_retorna_vazio(self):
        self.assertEqual(textos.load(tempfile.mkdtemp()), {})

    def test_l1_cai_no_tema_quando_nao_ha_empresa(self):
        """Seção 5: sem convidado externo, a linha 1 recebe o tema do episódio."""
        d = tempfile.mkdtemp()
        with open(os.path.join(d, "episodio.json"), "w", encoding="utf-8") as f:
            json.dump({
                "temporada": 3, "episodio": 1, "empresa": "",
                "cidade": "Bauru", "uf": "SP", "convidados": [],
                "temas": ["ecossistema do interior", "outro"],
            }, f)
        args = textos.thumb_args(d)
        self.assertEqual(args["l1"], "ecossistema do interior")

    def test_build_kwargs_bate_com_a_assinatura_do_thumbnail(self):
        """Traduz l1/l2 -> chamada_l1/chamada_l2 sem perder campo em silêncio."""
        kwargs = textos.build_kwargs(self.d)
        sig = inspect.signature(thumbnail.build_thumbnail)
        esperados = {n for n, p in sig.parameters.items()
                     if p.kind is inspect.Parameter.KEYWORD_ONLY}
        self.assertEqual(set(kwargs), esperados)

    def test_build_kwargs_traduz_os_valores(self):
        kwargs = textos.build_kwargs(self.d)
        self.assertEqual(kwargs["chamada_l1"], "Norvik")
        self.assertEqual(kwargs["chamada_l2"], "T2E07")
        self.assertIn("Daniel", kwargs["creditos"])


if __name__ == "__main__":
    unittest.main()
