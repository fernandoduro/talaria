"""Testes da agenda de publicação (calendario.json)."""
import datetime as dt
import json
import os
import tempfile
import unittest

from talaria import calendario, layout, publicado


def _prepara(pd, momentos=None, posts=None, agenda=None):
    """Escreve as fontes e a agenda de um projeto de teste."""
    if momentos is not None:
        with open(layout.garante(layout.momentos(pd)), "w", encoding="utf-8") as f:
            json.dump(momentos, f)
    if posts is not None:
        with open(layout.garante(layout.posts(pd)), "w", encoding="utf-8") as f:
            json.dump({"posts": posts}, f)
    if agenda is not None:
        with open(layout.garante(layout.calendario(pd)), "w", encoding="utf-8") as f:
            json.dump({"agenda": agenda}, f)


MOMENTOS = [{"slug": "corte1", "start": 1.0, "end": 70.0, "titulo": "T"}]
POSTS = [{"slug": "citacao_x", "cards": ["frase"], "legenda": "leg"}]


class TestCarrega(unittest.TestCase):
    def setUp(self):
        self.pd = tempfile.mkdtemp()

    def test_agenda_valida_passa(self):
        _prepara(self.pd, MOMENTOS, POSTS, [
            {"data": "2026-08-24", "tipo": "corte", "slug": "corte1"},
            {"data": "2026-08-25", "tipo": "post", "slug": "citacao_x"},
        ])
        agenda = calendario.carrega(self.pd)
        self.assertEqual(len(agenda), 2)

    def test_sem_arquivo_explica_o_que_criar(self):
        with self.assertRaises(FileNotFoundError):
            calendario.carrega(self.pd)

    def test_slug_de_corte_inexistente_aborta(self):
        # Publicar o corte errado por slug digitado errado não tem correção.
        _prepara(self.pd, MOMENTOS, POSTS,
                 [{"data": "2026-08-24", "tipo": "corte", "slug": "corte99"}])
        with self.assertRaises(ValueError) as ctx:
            calendario.carrega(self.pd)
        self.assertIn("corte99", str(ctx.exception))

    def test_slug_de_post_inexistente_aborta(self):
        _prepara(self.pd, MOMENTOS, POSTS,
                 [{"data": "2026-08-24", "tipo": "post", "slug": "nao_existe"}])
        with self.assertRaises(ValueError):
            calendario.carrega(self.pd)

    def test_data_impossivel_aborta(self):
        # Valida a data REAL, não só o formato — 30 de fevereiro passa
        # num regex e publicaria nunca.
        _prepara(self.pd, MOMENTOS, POSTS,
                 [{"data": "2026-02-30", "tipo": "corte", "slug": "corte1"}])
        with self.assertRaises(ValueError) as ctx:
            calendario.carrega(self.pd)
        self.assertIn("2026-02-30", str(ctx.exception))

    def test_formato_de_data_errado_aborta(self):
        _prepara(self.pd, MOMENTOS, POSTS,
                 [{"data": "24/08/2026", "tipo": "corte", "slug": "corte1"}])
        with self.assertRaises(ValueError):
            calendario.carrega(self.pd)

    def test_slug_duplicado_aborta(self):
        # Reagendamento é editar a data do item, não repetir o slug.
        _prepara(self.pd, MOMENTOS, POSTS, [
            {"data": "2026-08-24", "tipo": "corte", "slug": "corte1"},
            {"data": "2026-08-26", "tipo": "corte", "slug": "corte1"},
        ])
        with self.assertRaises(ValueError) as ctx:
            calendario.carrega(self.pd)
        self.assertIn("duas vezes", str(ctx.exception))

    def test_corte_e_post_com_mesmo_slug_permitido(self):
        # O post de citação herda o slug do corte que cita; agendar os dois
        # não é repetição — são peças distintas, em plataformas distintas.
        posts = [{"slug": "corte1", "cards": ["frase"], "legenda": "leg"}]
        _prepara(self.pd, MOMENTOS, posts, [
            {"data": "2026-08-24", "tipo": "corte", "slug": "corte1"},
            {"data": "2026-08-25", "tipo": "post", "slug": "corte1"},
        ])
        self.assertEqual(len(calendario.carrega(self.pd)), 2)

    def test_dois_itens_no_mesmo_dia_permitido(self):
        _prepara(self.pd, MOMENTOS, POSTS, [
            {"data": "2026-08-24", "tipo": "corte", "slug": "corte1"},
            {"data": "2026-08-24", "tipo": "post", "slug": "citacao_x"},
        ])
        self.assertEqual(len(calendario.carrega(self.pd)), 2)

    def test_tipo_desconhecido_aborta(self):
        _prepara(self.pd, MOMENTOS, POSTS,
                 [{"data": "2026-08-24", "tipo": "reels", "slug": "corte1"}])
        with self.assertRaises(ValueError):
            calendario.carrega(self.pd)

    def test_slug_que_escapa_da_pasta_aborta(self):
        # O slug vira nome de arquivo em publicar/. Com barra ou `..` ele sai
        # da pasta do episódio: o publish acharia um mp4 de fora do projeto,
        # passaria na pré-checagem e publicaria a peça errada — com o texto
        # de fora virando descrição pública.
        mau = "../../../outro/corte"
        _prepara(self.pd,
                 [{"slug": mau, "start": 1.0, "end": 70.0, "titulo": "T"}],
                 POSTS,
                 [{"data": "2026-08-24", "tipo": "corte", "slug": mau}])
        with self.assertRaises(ValueError) as ctx:
            calendario.carrega(self.pd)
        self.assertIn("barra", str(ctx.exception))

    def test_slug_com_barra_simples_tambem_aborta(self):
        mau = "pasta/corte"
        _prepara(self.pd,
                 [{"slug": mau, "start": 1.0, "end": 70.0, "titulo": "T"}],
                 POSTS,
                 [{"data": "2026-08-24", "tipo": "corte", "slug": mau}])
        with self.assertRaises(ValueError):
            calendario.carrega(self.pd)

    def test_slug_normal_com_ponto_continua_valendo(self):
        # Sanear não pode ficar restritivo demais: ponto e hífen são comuns
        # em slug de corte ("corte1_faria-lima.v2") e não escapam de pasta.
        ok = "corte1_faria-lima.v2"
        _prepara(self.pd,
                 [{"slug": ok, "start": 1.0, "end": 70.0, "titulo": "T"}],
                 POSTS,
                 [{"data": "2026-08-24", "tipo": "corte", "slug": ok}])
        self.assertEqual(len(calendario.carrega(self.pd)), 1)

    def test_carrossel_acima_de_10_aborta(self):
        # Limite da Graph API é 10 imagens; a solução é editorial.
        posts = [{"slug": "longo", "cards": ["c"] * 11, "legenda": "x"}]
        _prepara(self.pd, MOMENTOS, posts,
                 [{"data": "2026-08-24", "tipo": "post", "slug": "longo"}])
        with self.assertRaises(ValueError) as ctx:
            calendario.carrega(self.pd)
        self.assertIn("quebre", str(ctx.exception))


class TestPendente(unittest.TestCase):
    def setUp(self):
        self.pd = tempfile.mkdtemp()
        _prepara(self.pd, MOMENTOS, POSTS, [
            {"data": "2026-08-24", "tipo": "corte", "slug": "corte1"},
            {"data": "2026-08-25", "tipo": "post", "slug": "citacao_x"},
        ])

    def test_corte_pendente_vale_por_duas_plataformas(self):
        pares = calendario.pendente(self.pd, dia=dt.date(2026, 8, 24))
        self.assertEqual([(i["slug"], pl) for i, pl in pares],
                         [("corte1", "youtube_shorts"),
                          ("corte1", "instagram_reels")])

    def test_futuro_nao_entra(self):
        pares = calendario.pendente(self.pd, dia=dt.date(2026, 8, 23))
        self.assertEqual(pares, [])

    def test_atrasado_continua_pendente(self):
        # Esquecer de rodar ontem não perde a publicação.
        pares = calendario.pendente(self.pd, dia=dt.date(2026, 8, 30))
        self.assertEqual(len(pares), 3)  # corte (2 plataformas) + post

    def test_meio_publicado_retenta_so_o_que_faltou(self):
        # YouTube passou, Instagram falhou → amanhã só o Instagram.
        publicado.registra(self.pd, "youtube_shorts", "corte1", "a", "u")
        pares = calendario.pendente(self.pd, dia=dt.date(2026, 8, 24))
        self.assertEqual([(i["slug"], pl) for i, pl in pares],
                         [("corte1", "instagram_reels")])

    def test_tudo_publicado_devolve_vazio(self):
        publicado.registra(self.pd, "youtube_shorts", "corte1", "a", "u")
        publicado.registra(self.pd, "instagram_reels", "corte1", "b", "u")
        pares = calendario.pendente(self.pd, dia=dt.date(2026, 8, 24))
        self.assertEqual(pares, [])

    def test_only_ignora_data_mas_nao_a_trava(self):
        # Antecipar com --only funciona; republicar por --only NÃO.
        publicado.registra(self.pd, "instagram_posts", "citacao_x", "c", "u")
        pares = calendario.pendente(self.pd, dia=dt.date(2026, 8, 1),
                                    only=["corte1", "citacao_x"])
        self.assertEqual([(i["slug"], pl) for i, pl in pares],
                         [("corte1", "youtube_shorts"),
                          ("corte1", "instagram_reels")])

    def test_only_vazio_nao_vira_agenda_do_dia(self):
        # `only=[]` é "filtre para nada", não "sem filtro": o chamador que
        # monta a lista a partir de uma flag vazia pediria a agenda inteira
        # sem querer, e publicaria o dia inteiro achando que pediu um slug.
        self.assertEqual(
            calendario.pendente(self.pd, dia=dt.date(2026, 8, 30), only=[]), [])

    def test_plataformas_restringe_o_que_sai(self):
        # Enquanto o Instagram não está configurado, o corte inteiro ficaria
        # parado: a pré-checagem cobra as credenciais das DUAS plataformas.
        # Restringir deixa o YouTube sair e o Reels seguir pendente.
        pares = calendario.pendente(self.pd, dia=dt.date(2026, 8, 24),
                                    plataformas=["youtube_shorts"])
        self.assertEqual([(i["slug"], pl) for i, pl in pares],
                         [("corte1", "youtube_shorts")])

    def test_plataforma_restrita_nao_marca_a_outra_como_publicada(self):
        # O que não saiu continua pendente — a trava é por (slug, plataforma).
        publicado.registra(self.pd, "youtube_shorts", "corte1", "a", "u")
        pares = calendario.pendente(self.pd, dia=dt.date(2026, 8, 24))
        self.assertEqual([pl for _, pl in pares], ["instagram_reels"])

    def test_plataforma_desconhecida_aborta(self):
        with self.assertRaises(ValueError) as ctx:
            calendario.pendente(self.pd, dia=dt.date(2026, 8, 24),
                                plataformas=["tiktok"])
        self.assertIn("tiktok", str(ctx.exception))

    def test_only_com_slug_fora_da_agenda_aborta(self):
        with self.assertRaises(ValueError) as ctx:
            calendario.pendente(self.pd, dia=dt.date(2026, 8, 24),
                                only=["nao_agendado"])
        self.assertIn("nao_agendado", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
