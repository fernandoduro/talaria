"""Testes de leitura e validação do episode.json."""
import json
import os
import tempfile
import unittest

from talaria import episode


class TestEpisodio(unittest.TestCase):
    def _write(self, data):
        d = tempfile.mkdtemp()
        p = os.path.join(d, "episode.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f)
        return d

    def test_le_episodio_valido(self):
        d = self._write({
            "season": 2, "episode": 7, "company": "Zarvik",
            "city": "Ribeirão Açaí", "uf": "SP",
            "guests": [{"name": "Teresa", "role": "CTO", "linkedin": "https://x"}],
        })
        ep = episode.load(d)
        self.assertEqual(ep["company"], "Zarvik")

    def test_codigo_com_dois_digitos(self):
        d = self._write({
            "season": 2, "episode": 7, "company": "Zarvik",
            "city": "Ribeirão Açaí", "uf": "SP", "guests": [],
        })
        ep = episode.load(d)
        self.assertEqual(episode.code(ep), "T2E07")

    def test_codigo_nao_trunca_episodio_grande(self):
        d = self._write({
            "season": 2, "episode": 12, "company": "X",
            "city": "Pedra Nova", "uf": "SP", "guests": [],
        })
        self.assertEqual(episode.code(episode.load(d)), "T2E12")

    def test_campo_faltando_da_erro_claro(self):
        d = self._write({"season": 2})
        with self.assertRaises(ValueError) as ctx:
            episode.load(d)
        msg = str(ctx.exception)
        for campo in ("company", "city", "uf", "guests"):
            self.assertIn(campo, msg)
        self.assertNotIn("season", msg)   # presente, não deve ser listado

    def test_arquivo_ausente_da_erro_claro(self):
        d = tempfile.mkdtemp()
        with self.assertRaises(FileNotFoundError):
            episode.load(d)

    def test_template_tem_todos_os_campos(self):
        t = episode.template()
        for campo in episode.REQUIRED_FIELDS:
            self.assertIn(campo, t)

    def test_campos_obrigatorios_nao_encolhe(self):
        self.assertEqual(
            set(episode.REQUIRED_FIELDS),
            {"season", "episode", "company", "city", "uf", "guests"},
        )

    def test_save_load_roundtrip_preserva_acento(self):
        d = tempfile.mkdtemp()
        dados = {"season": 2, "episode": 7, "company": "Zarvik",
                 "city": "Ribeirão Açaí", "uf": "SP", "guests": []}
        path = episode.save(d, dados)
        self.assertTrue(os.path.exists(path))
        with open(path, encoding="utf-8") as f:
            self.assertIn("Ribeirão Açaí", f.read())
        self.assertEqual(episode.load(d), dados)

    def test_template_em_branco_e_recusado(self):
        d = tempfile.mkdtemp()
        episode.save(d, episode.template())
        with self.assertRaises(ValueError) as ctx:
            episode.load(d)
        self.assertIn("branco", str(ctx.exception))

    def test_zero_conta_como_nao_preenchido(self):
        """Não existe season 0 nem episódio 0 — o template semeia ambos com 0."""
        d = self._write({
            "season": 0, "episode": 0, "company": "Zarvik",
            "city": "Pedra Nova", "uf": "SP", "guests": [],
        })
        with self.assertRaises(ValueError) as ctx:
            episode.load(d)
        msg = str(ctx.exception)
        self.assertIn("branco", msg)
        self.assertIn("season", msg)
        self.assertIn("episode", msg)

    def test_convidados_vazio_e_aceito(self):
        """Episódio só com os apresentadores é caso real do prompt de materiais."""
        d = self._write({
            "season": 2, "episode": 7, "company": "Zarvik",
            "city": "Pedra Nova", "uf": "SP", "guests": [],
        })
        self.assertEqual(episode.load(d)["guests"], [])

    def test_tipo_errado_da_erro_claro(self):
        d = self._write({
            "season": "dois", "episode": 7, "company": "Zarvik",
            "city": "Pedra Nova", "uf": "SP", "guests": [],
        })
        with self.assertRaises(ValueError) as ctx:
            episode.load(d)
        msg = str(ctx.exception)
        self.assertIn("season", msg)
        self.assertIn("inteiro", msg)

    def test_episodio_so_com_apresentadores_e_aceito(self):
        """Sem convidado externo, `company` pode ficar vazia."""
        d = self._write({
            "season": 3, "episode": 1, "company": "",
            "city": "Pedra Nova", "uf": "SP", "guests": [],
            "topics": ["ecossistema local de startups"],
        })
        ep = episode.load(d)
        self.assertEqual(ep["company"], "")

    def test_sem_convidado_e_sem_tema_e_recusado(self):
        """Sem company, o tema é a origem da linha 1 da thumb e da hashtag."""
        d = self._write({
            "season": 3, "episode": 1, "company": "",
            "city": "Pedra Nova", "uf": "SP", "guests": [], "topics": [],
        })
        with self.assertRaises(ValueError) as ctx:
            episode.load(d)
        self.assertIn("tema", str(ctx.exception).lower())

    def test_com_convidado_empresa_continua_obrigatoria(self):
        d = self._write({
            "season": 2, "episode": 7, "company": "",
            "city": "Pedra Nova", "uf": "SP",
            "guests": [{"name": "Teresa", "role": "sócio", "linkedin": ""}],
        })
        with self.assertRaises(ValueError):
            episode.load(d)


if __name__ == "__main__":
    unittest.main()
