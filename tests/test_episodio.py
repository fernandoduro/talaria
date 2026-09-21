"""Testes de leitura e validação do episodio.json."""
import json
import os
import tempfile
import unittest

from talaria import episodio


class TestEpisodio(unittest.TestCase):
    def _escreve(self, data):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "episodio.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return d

    def test_le_episodio_valido(self):
        d = self._escreve({
            "temporada": 2, "episodio": 7, "empresa": "Norvik",
            "cidade": "São Gonçalo", "uf": "SP",
            "convidados": [{"nome": "Daniel", "cargo": "CTO", "linkedin": "https://x"}],
        })
        ep = episodio.load(d)
        self.assertEqual(ep["empresa"], "Norvik")

    def test_codigo_com_dois_digitos(self):
        d = self._escreve({
            "temporada": 2, "episodio": 7, "empresa": "Norvik",
            "cidade": "São Gonçalo", "uf": "SP", "convidados": [],
        })
        ep = episodio.load(d)
        self.assertEqual(episodio.codigo(ep), "T2E07")

    def test_codigo_nao_trunca_episodio_grande(self):
        d = self._escreve({
            "temporada": 2, "episodio": 12, "empresa": "X",
            "cidade": "Bauru", "uf": "SP", "convidados": [],
        })
        self.assertEqual(episodio.codigo(episodio.load(d)), "T2E12")

    def test_campo_faltando_da_erro_claro(self):
        d = self._escreve({"temporada": 2})
        with self.assertRaises(ValueError) as ctx:
            episodio.load(d)
        msg = str(ctx.exception)
        for campo in ("empresa", "cidade", "uf", "convidados"):
            self.assertIn(campo, msg)
        self.assertNotIn("temporada", msg)   # presente, não deve ser listado

    def test_arquivo_ausente_da_erro_claro(self):
        d = tempfile.mkdtemp()
        with self.assertRaises(FileNotFoundError):
            episodio.load(d)

    def test_template_tem_todos_os_campos(self):
        t = episodio.template()
        for campo in episodio.CAMPOS_OBRIGATORIOS:
            self.assertIn(campo, t)

    def test_campos_obrigatorios_nao_encolhe(self):
        self.assertEqual(
            set(episodio.CAMPOS_OBRIGATORIOS),
            {"temporada", "episodio", "empresa", "cidade", "uf", "convidados"},
        )

    def test_save_load_roundtrip_preserva_acento(self):
        d = tempfile.mkdtemp()
        dados = {"temporada": 2, "episodio": 7, "empresa": "Norvik",
                 "cidade": "São Gonçalo", "uf": "SP", "convidados": []}
        path = episodio.save(d, dados)
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as f:
            self.assertIn("São Gonçalo", f.read())
        self.assertEqual(episodio.load(d), dados)

    def test_template_em_branco_e_recusado(self):
        d = tempfile.mkdtemp()
        episodio.save(d, episodio.template())
        with self.assertRaises(ValueError) as ctx:
            episodio.load(d)
        self.assertIn("branco", str(ctx.exception))

    def test_zero_conta_como_nao_preenchido(self):
        """Não existe temporada 0 nem episódio 0 — o template semeia ambos com 0."""
        d = self._escreve({
            "temporada": 0, "episodio": 0, "empresa": "Norvik",
            "cidade": "Bauru", "uf": "SP", "convidados": [],
        })
        with self.assertRaises(ValueError) as ctx:
            episodio.load(d)
        msg = str(ctx.exception)
        self.assertIn("branco", msg)
        self.assertIn("temporada", msg)
        self.assertIn("episodio", msg)

    def test_convidados_vazio_e_aceito(self):
        """Episódio só com os apresentadores é caso real do prompt da casa."""
        d = self._escreve({
            "temporada": 2, "episodio": 7, "empresa": "Norvik",
            "cidade": "Bauru", "uf": "SP", "convidados": [],
        })
        self.assertEqual(episodio.load(d)["convidados"], [])

    def test_tipo_errado_da_erro_claro(self):
        d = self._escreve({
            "temporada": "dois", "episodio": 7, "empresa": "Norvik",
            "cidade": "Bauru", "uf": "SP", "convidados": [],
        })
        with self.assertRaises(ValueError) as ctx:
            episodio.load(d)
        msg = str(ctx.exception)
        self.assertIn("temporada", msg)
        self.assertIn("inteiro", msg)

    def test_episodio_so_com_apresentadores_e_aceito(self):
        """Sem convidado externo, `empresa` pode ficar vazia (seção 1 do prompt)."""
        d = self._escreve({
            "temporada": 3, "episodio": 1, "empresa": "",
            "cidade": "Bauru", "uf": "SP", "convidados": [],
            "temas": ["ecossistema do interior"],
        })
        ep = episodio.load(d)
        self.assertEqual(ep["empresa"], "")

    def test_sem_convidado_e_sem_tema_e_recusado(self):
        """Sem empresa, o tema é a origem da linha 1 da thumb e da hashtag."""
        d = self._escreve({
            "temporada": 3, "episodio": 1, "empresa": "",
            "cidade": "Bauru", "uf": "SP", "convidados": [], "temas": [],
        })
        with self.assertRaises(ValueError) as ctx:
            episodio.load(d)
        self.assertIn("tema", str(ctx.exception).lower())

    def test_com_convidado_empresa_continua_obrigatoria(self):
        d = self._escreve({
            "temporada": 2, "episodio": 7, "empresa": "",
            "cidade": "Bauru", "uf": "SP",
            "convidados": [{"nome": "Daniel", "cargo": "sócio", "linkedin": ""}],
        })
        with self.assertRaises(ValueError):
            episodio.load(d)


if __name__ == "__main__":
    unittest.main()
