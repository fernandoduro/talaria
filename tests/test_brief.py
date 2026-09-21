"""Testes da montagem dos pacotes de leitura."""
import json
import os
import tempfile
import unittest

from talaria import brief, layout


class TestBrief(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        with open(layout.garante(layout.episodio(self.d)), "w", encoding="utf-8") as f:
            json.dump({
                "temporada": 2, "episodio": 7, "empresa": "Zarvik",
                "cidade": "Ribeirão Açaí", "uf": "SP",
                "convidados": [{"nome": "Teresa", "cargo": "sócio",
                                "linkedin": "https://linkedin.com/in/x"}],
                "temas": ["biotech", "B2B para B2C"],
            }, f)
        with open(layout.garante(layout.transcricao(self.d)), "w", encoding="utf-8") as f:
            json.dump({"segments": [
                {"start": 10.0, "end": 15.0, "text": "Primeira fala.", "turn": False},
                {"start": 15.0, "end": 80.0, "text": "Segunda fala.", "turn": True},
            ]}, f)

    def test_transcricao_formatada_tem_timestamps(self):
        txt = brief.transcricao_legivel(self.d)
        self.assertIn("00:10", txt)
        self.assertIn("Primeira fala.", txt)

    def test_metadados_formatados(self):
        m = brief.metadados_legiveis(self.d)
        self.assertIn("Zarvik", m)
        self.assertIn("T2E07", m)
        self.assertIn("Ribeirão Açaí", m)
        self.assertIn("Teresa", m)

    def test_substitui_placeholder_de_transcricao(self):
        tpl = "PROMPT AQUI\n\n{{TRANSCRICAO}}\n"
        out = brief.preencher(tpl, transcricao="XPTO", metadados="")
        self.assertIn("XPTO", out)
        self.assertNotIn("{{TRANSCRICAO}}", out)

    def test_substitui_placeholder_de_metadados(self):
        tpl = "PROMPT\n{{METADADOS}}\n"
        out = brief.preencher(tpl, transcricao="", metadados="DADOS")
        self.assertIn("DADOS", out)
        self.assertNotIn("{{METADADOS}}", out)

    def test_substitui_placeholder_de_curadoria(self):
        tpl = "PROMPT\n{{CURADORIA}}\n"
        out = brief.preencher(tpl, transcricao="", metadados="", curadoria="ESTADO")
        self.assertIn("ESTADO", out)
        self.assertNotIn("{{CURADORIA}}", out)

    def test_placeholder_ausente_nao_quebra(self):
        out = brief.preencher("sem placeholder", transcricao="X", metadados="Y")
        self.assertEqual(out, "sem placeholder")

    def test_estado_legivel_primeira_rodada(self):
        estado = {"meta": 5, "aprovados": [], "rejeitados": [], "rodadas": 0}
        txt = brief.curadoria_legivel(estado)
        self.assertIn("PRIMEIRA RODADA", txt)
        self.assertIn("10", txt)

    def test_estado_legivel_com_rejeitados(self):
        estado = {"meta": 5, "rodadas": 1,
                  "aprovados": [{"slug": "a", "start": 100.0, "end": 170.0,
                                 "tipo": "historia"}],
                  "rejeitados": [{"start": 300.0, "end": 370.0,
                                  "motivo": "gancho fraco", "resumo": "trecho X"}]}
        txt = brief.curadoria_legivel(estado)
        self.assertIn("gancho fraco", txt)
        self.assertIn("4", txt)          # vagas restantes
        self.assertIn("05:00", txt)      # faixa queimada em mm:ss


class TestBriefPosts(unittest.TestCase):
    """Pacote de leitura da escolha de citações (comando `post --cortes`)."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        with open(layout.garante(layout.episodio(self.d)), "w", encoding="utf-8") as f:
            json.dump({
                "temporada": 2, "episodio": 8, "empresa": "Zarvik",
                "cidade": "Ribeirão Açaí", "uf": "SP", "temas": [],
                "convidados": [{"nome": "Marina Siqueira", "cargo": "Sócio"}],
            }, f, ensure_ascii=False)
        with open(layout.garante(layout.transcricao(self.d)), "w", encoding="utf-8") as f:
            json.dump({"segments": [
                {"start": 10.0, "end": 14.0, "text": "A oportunidade estava do lado."},
                {"start": 14.0, "end": 18.0, "text": "E a gente não viu."},
                {"start": 900.0, "end": 904.0, "text": "Fala de outro trecho."},
            ]}, f, ensure_ascii=False)
        self.corte = {"slug": "corte1_mar_azul", "start": 10.0, "end": 18.0,
                      "tipo": "tese", "texto_tela": "O mar azul",
                      "legenda_post": "...", "trecho": "..."}

    def test_traz_a_fala_dentro_do_corte(self):
        out = brief.montar_posts(self.d, [self.corte])
        with open(out, encoding="utf-8") as f:
            texto = f.read()
        self.assertIn("corte1_mar_azul", texto)
        self.assertIn("A oportunidade estava do lado.", texto)
        self.assertIn("E a gente não viu.", texto)

    def test_traz_a_fala_do_segmento_que_atravessa_a_fronteira(self):
        """Segmento cortado ao meio pela fronteira ainda é fala do corte.

        Exigir contenção total escondia a ÚLTIMA frase de todo corte —
        justamente onde costuma estar a frase de impacto. O vídeo mostra essa
        fala (render._segments_in_cut apara o texto), então o pacote de leitura
        precisa mostrá-la também.
        """
        corte = {"slug": "c", "start": 10.0, "end": 16.0, "tipo": "tese",
                 "texto_tela": "", "legenda_post": "", "trecho": ""}
        texto = brief.fala_do_corte(self.d, corte)
        self.assertIn("A oportunidade estava do lado.", texto)
        # O 2º segmento (14–18s) é aparado pela fronteira em 16s: entra a
        # metade que o corte alcança, não o bloco inteiro nem nada.
        self.assertIn("E a", texto)
        self.assertNotIn("não viu", texto)

    def test_nao_traz_fala_de_fora_do_corte(self):
        out = brief.montar_posts(self.d, [self.corte])
        with open(out, encoding="utf-8") as f:
            texto = f.read()
        self.assertNotIn("Fala de outro trecho.", texto)

    def test_traz_metadados_e_limite_de_encaixe(self):
        out = brief.montar_posts(self.d, [self.corte])
        with open(out, encoding="utf-8") as f:
            texto = f.read()
        self.assertIn("Marina Siqueira", texto)
        self.assertIn("100 caracteres", texto)
        # os placeholders do prompt têm que ter sido substituídos
        self.assertNotIn("{{", texto)

    def test_grava_em_brief_posts_md(self):
        out = brief.montar_posts(self.d, [self.corte])
        self.assertEqual(out, layout.brief(self.d, "posts"))
        self.assertTrue(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
