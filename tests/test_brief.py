"""Testes da montagem dos pacotes de leitura."""
import json
import os
import tempfile
import unittest

from talaria import brief, layout


class TestBrief(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        with open(layout.ensure_dir(layout.episode(self.d)), "w", encoding="utf-8") as f:
            json.dump({
                "season": 2, "episode": 7, "company": "Zarvik",
                "cidade": "Ribeirão Açaí", "uf": "SP",
                "guests": [{"name": "Teresa", "role": "sócio",
                                "linkedin": "https://linkedin.com/in/x"}],
                "topics": ["biotech", "B2B para B2C"],
            }, f)
        with open(layout.ensure_dir(layout.transcript(self.d)), "w", encoding="utf-8") as f:
            json.dump({"segments": [
                {"start": 10.0, "end": 15.0, "text": "Primeira fala.", "turn": False},
                {"start": 15.0, "end": 80.0, "text": "Segunda fala.", "turn": True},
            ]}, f)

    def test_transcricao_formatada_tem_timestamps(self):
        txt = brief.readable_transcript(self.d)
        self.assertIn("00:10", txt)
        self.assertIn("Primeira fala.", txt)

    def test_metadados_formatados(self):
        m = brief.readable_metadata(self.d)
        self.assertIn("Zarvik", m)
        self.assertIn("T2E07", m)
        self.assertIn("Ribeirão Açaí", m)
        self.assertIn("Teresa", m)

    def test_substitui_placeholder_de_transcricao(self):
        tpl = "PROMPT AQUI\n\n{{TRANSCRICAO}}\n"
        out = brief.preencher(tpl, transcript="XPTO", metadados="")
        self.assertIn("XPTO", out)
        self.assertNotIn("{{TRANSCRICAO}}", out)

    def test_substitui_placeholder_de_metadados(self):
        tpl = "PROMPT\n{{METADADOS}}\n"
        out = brief.preencher(tpl, transcript="", metadados="DADOS")
        self.assertIn("DADOS", out)
        self.assertNotIn("{{METADADOS}}", out)

    def test_substitui_placeholder_de_curadoria(self):
        tpl = "PROMPT\n{{CURADORIA}}\n"
        out = brief.preencher(tpl, transcript="", metadados="", curation="ESTADO")
        self.assertIn("ESTADO", out)
        self.assertNotIn("{{CURADORIA}}", out)

    def test_placeholder_ausente_nao_quebra(self):
        out = brief.preencher("sem placeholder", transcript="X", metadados="Y")
        self.assertEqual(out, "sem placeholder")

    def test_estado_legivel_primeira_rodada(self):
        estado = {"meta": 5, "approved": [], "rejected": [], "rounds": 0}
        txt = brief.readable_curation(estado)
        self.assertIn("PRIMEIRA RODADA", txt)
        self.assertIn("10", txt)

    def test_estado_legivel_com_rejeitados(self):
        estado = {"meta": 5, "rounds": 1,
                  "approved": [{"slug": "a", "start": 100.0, "end": 170.0,
                                 "kind": "story"}],
                  "rejected": [{"start": 300.0, "end": 370.0,
                                  "reason": "gancho fraco", "summary": "trecho X"}]}
        txt = brief.readable_curation(estado)
        self.assertIn("gancho fraco", txt)
        self.assertIn("4", txt)          # slots_left restantes
        self.assertIn("05:00", txt)      # faixa queimada em mm:ss


class TestBriefPosts(unittest.TestCase):
    """Pacote de leitura da escolha de citações (comando `post --cortes`)."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        with open(layout.ensure_dir(layout.episode(self.d)), "w", encoding="utf-8") as f:
            json.dump({
                "season": 2, "episode": 8, "company": "Zarvik",
                "cidade": "Ribeirão Açaí", "uf": "SP", "topics": [],
                "guests": [{"name": "Marina Siqueira", "role": "Sócio"}],
            }, f, ensure_ascii=False)
        with open(layout.ensure_dir(layout.transcript(self.d)), "w", encoding="utf-8") as f:
            json.dump({"segments": [
                {"start": 10.0, "end": 14.0, "text": "A oportunidade estava do lado."},
                {"start": 14.0, "end": 18.0, "text": "E a gente não viu."},
                {"start": 900.0, "end": 904.0, "text": "Fala de outro trecho."},
            ]}, f, ensure_ascii=False)
        self.clip = {"slug": "corte1_mar_azul", "start": 10.0, "end": 18.0,
                      "kind": "thesis", "screen_text": "O mar azul",
                      "post_caption": "...", "trecho": "..."}

    def test_traz_a_fala_dentro_do_corte(self):
        out = brief.build_posts(self.d, [self.clip])
        with open(out, encoding="utf-8") as f:
            texto = f.read()
        self.assertIn("corte1_mar_azul", texto)
        self.assertIn("A oportunidade estava do lado.", texto)
        self.assertIn("E a gente não viu.", texto)

    def test_traz_a_fala_do_segmento_que_atravessa_a_fronteira(self):
        """Segmento cortado ao meio pela fronteira ainda é fala do clip.

        Exigir contenção total escondia a ÚLTIMA frase de todo clip —
        justamente onde costuma estar a frase de impacto. O vídeo mostra essa
        fala (render._segments_in_cut apara o texto), então o pacote de leitura
        precisa mostrá-la também.
        """
        clip = {"slug": "c", "start": 10.0, "end": 16.0, "kind": "thesis",
                 "screen_text": "", "post_caption": "", "trecho": ""}
        texto = brief.clip_speech(self.d, clip)
        self.assertIn("A oportunidade estava do lado.", texto)
        # O 2º segmento (14–18s) é aparado pela fronteira em 16s: entra a
        # metade que o clip alcança, não o bloco inteiro nem nada.
        self.assertIn("E a", texto)
        self.assertNotIn("não viu", texto)

    def test_nao_traz_fala_de_fora_do_corte(self):
        out = brief.build_posts(self.d, [self.clip])
        with open(out, encoding="utf-8") as f:
            texto = f.read()
        self.assertNotIn("Fala de outro trecho.", texto)

    def test_traz_metadados_e_limite_de_encaixe(self):
        out = brief.build_posts(self.d, [self.clip])
        with open(out, encoding="utf-8") as f:
            texto = f.read()
        self.assertIn("Marina Siqueira", texto)
        self.assertIn("100 caracteres", texto)
        # os placeholders do prompt têm que ter sido substituídos
        self.assertNotIn("{{", texto)

    def test_grava_em_brief_posts_md(self):
        out = brief.build_posts(self.d, [self.clip])
        self.assertEqual(out, layout.brief(self.d, "posts"))
        self.assertTrue(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
