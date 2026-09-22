"""Testes do estado da curation iterativa."""
import unittest

from talaria import curation


class TestSobreposicao(unittest.TestCase):
    def test_sobreposicao_total(self):
        self.assertTrue(curation.overlaps((10, 70), (10, 70)))

    def test_sem_sobreposicao(self):
        self.assertFalse(curation.overlaps((10, 70), (100, 160)))

    def test_encosta_nao_sobrepoe(self):
        self.assertFalse(curation.overlaps((10, 70), (70, 130)))

    def test_sobreposicao_pequena_abaixo_do_limiar(self):
        # 5s de 60s = 8% — abaixo do limiar de 30%, não conta
        self.assertFalse(curation.overlaps((10, 70), (65, 125)))

    def test_sobreposicao_grande_acima_do_limiar(self):
        # clip 10s adiante do rejeitado — mesmo trecho disfarçado
        self.assertTrue(curation.overlaps((10, 70), (20, 80)))


class TestQueimados(unittest.TestCase):
    def setUp(self):
        self.estado = {
            "meta": 5,
            "approved": [{"slug": "a", "start": 100.0, "end": 170.0}],
            "rejected": [{"start": 300.0, "end": 370.0, "reason": "gancho fraco"}],
            "rounds": 1,
        }

    def test_faixas_incluem_aprovados_e_rejeitados(self):
        faixas = curation.burned_spans(self.estado)
        self.assertIn((100.0, 170.0), faixas)
        self.assertIn((300.0, 370.0), faixas)

    def test_proposta_sobre_rejeitado_e_queimada(self):
        self.assertTrue(curation.is_burned((310.0, 380.0), self.estado))

    def test_proposta_livre_nao_e_queimada(self):
        self.assertFalse(curation.is_burned((500.0, 570.0), self.estado))

    def test_vagas_restantes(self):
        self.assertEqual(curation.slots_left(self.estado), 4)

    def test_vagas_nunca_negativa(self):
        e = dict(self.estado, approved=[{"slug": str(i)} for i in range(7)])
        self.assertEqual(curation.slots_left(e), 0)


class TestEstadoInicial(unittest.TestCase):
    def test_novo_estado_tem_meta(self):
        e = curation.new_state(meta=5)
        self.assertEqual(e["meta"], 5)
        self.assertEqual(e["approved"], [])
        self.assertEqual(e["rejected"], [])
        self.assertEqual(e["rounds"], 0)


class TestValidacoes(unittest.TestCase):
    def setUp(self):
        self.segs = [
            {"start": 0.0, "end": 30.0, "text": "Pergunta do host?", "turn": False},
            {"start": 30.0, "end": 95.0, "text": "Resposta longa do convidado.", "turn": True},
            {"start": 95.0, "end": 120.0, "text": "Continua a resposta.", "turn": False},
        ]

    def test_duracao_dentro_da_faixa(self):
        ok, msgs = curation.validate_clip((0.0, 75.0), self.segs, {})
        self.assertTrue(ok, msgs)

    def test_duracao_curta_demais(self):
        ok, msgs = curation.validate_clip((0.0, 30.0), self.segs, {})
        self.assertFalse(ok)
        self.assertTrue(any("duração" in m for m in msgs))

    def test_duracao_longa_demais(self):
        ok, msgs = curation.validate_clip((0.0, 120.0), self.segs, {})
        self.assertFalse(ok)
        self.assertTrue(any("duração" in m for m in msgs))

    def test_fronteira_fora_de_segmento(self):
        ok, msgs = curation.validate_clip((12.0, 87.0), self.segs, {})
        self.assertFalse(ok)
        self.assertTrue(any("fronteira" in m for m in msgs))

    def test_corte_sobre_faixa_queimada(self):
        estado = {"meta": 5, "approved": [], "rounds": 0,
                  "rejected": [{"start": 0.0, "end": 75.0}]}
        ok, msgs = curation.validate_clip((0.0, 75.0), self.segs, estado)
        self.assertFalse(ok)
        self.assertTrue(any("queimad" in m for m in msgs))


class TestFimEmFraseCompleta(unittest.TestCase):
    """O fim do clip tem que fechar frase, não só coincidir com fim de bloco.

    A transcrição do YouTube quebra os blocos por TEMPO, não por pontuação:
    um bloco pode terminar no meio de uma frase. Conferir apenas o limite do
    bloco deixava passar clip que termina em palavra solta — foi o que
    aconteceu (bloco 1655-1663 fecha em "...transferência de tecnologia
    o dos", frase que só termina no bloco seguinte).
    """

    def setUp(self):
        self.segs = [
            {"start": 0.0, "end": 30.0, "text": "Abertura da conversa.", "turn": False},
            # termina em frase completa
            {"start": 30.0, "end": 95.0, "text": "Você não vai conseguir reproduzir.", "turn": True},
            # NÃO termina em frase: emenda no bloco seguinte
            {"start": 95.0, "end": 160.0, "text": "Acho que isso é um primeiro ponto que", "turn": False},
            {"start": 160.0, "end": 200.0, "text": "foi importante para nós.", "turn": False},
        ]

    def test_fim_em_frase_completa_passa(self):
        ok, msgs = curation.validate_clip((30.0, 95.0), self.segs, {})
        self.assertTrue(ok, msgs)

    def test_fim_no_meio_de_frase_reprova(self):
        """Bloco 95-160 acaba sem pontuação final: o clip fica pela metade."""
        ok, msgs = curation.validate_clip((95.0, 160.0), self.segs, {})
        self.assertFalse(ok)
        self.assertTrue(any("fim" in m.lower() for m in msgs), msgs)

    def test_fim_com_reticencias_e_aceito(self):
        segs = [{"start": 0.0, "end": 65.0, "text": "E aí a gente parou...", "turn": False}]
        ok, msgs = curation.validate_clip((0.0, 65.0), segs, {})
        self.assertTrue(ok, msgs)

    def test_fim_com_interrogacao_e_aceito(self):
        segs = [{"start": 0.0, "end": 65.0, "text": "Como que a gente faz isso?", "turn": False}]
        ok, msgs = curation.validate_clip((0.0, 65.0), segs, {})
        self.assertTrue(ok, msgs)


class TestFinsDeFrase(unittest.TestCase):
    """Candidatos a fim de clip, para não escolher o ponto à mão."""

    def setUp(self):
        self.segs = [
            {"start": 0.0, "end": 30.0, "text": "Abertura da conversa.", "turn": False},
            {"start": 30.0, "end": 70.0,
             "text": "Primeira ideia fecha aqui. E a segunda fecha aqui também.",
             "turn": False},
            {"start": 70.0, "end": 100.0, "text": "Bem depois do limite.", "turn": False},
        ]

    def test_devolve_apenas_duracoes_validas(self):
        for _inst, dur, _ctx in curation.sentence_ends(self.segs, 0.0, 30.0, 100.0):
            self.assertGreaterEqual(dur, 60.0)
            self.assertLessEqual(dur, 90.0)

    def test_ordenado_por_instante(self):
        r = curation.sentence_ends(self.segs, 0.0, 30.0, 100.0)
        self.assertEqual([x[0] for x in r], sorted(x[0] for x in r))

    def test_traz_contexto_do_trecho(self):
        r = curation.sentence_ends(self.segs, 0.0, 30.0, 100.0)
        self.assertTrue(all(isinstance(x[2], str) and x[2] for x in r), r)

    def test_sem_candidato_fora_da_janela(self):
        self.assertEqual(curation.sentence_ends(self.segs, 0.0, 95.0, 100.0), [])


class TestSobreposicaoEntreAprovados(unittest.TestCase):
    """Dois approved no mesmo trecho competem entre si na distribuição.

    `validate_clip` já barrava, mas who chamava `approve()` direto escapava —
    dois cortes dividiram 74s por isso.
    """

    def setUp(self):
        self.estado = curation.new_state(meta=5)
        curation.approve(self.estado, {"slug": "a", "start": 100.0, "end": 170.0})

    def test_recusa_corte_sobreposto(self):
        with self.assertRaises(ValueError) as cm:
            curation.approve(self.estado, {"slug": "b", "start": 150.0, "end": 220.0})
        self.assertIn("sobrepõe", str(cm.exception))

    def test_aceita_corte_disjunto(self):
        curation.approve(self.estado, {"slug": "b", "start": 200.0, "end": 270.0})
        self.assertEqual(len(self.estado["approved"]), 2)

    def test_ajuste_de_tempo_pode_encostar_em_outro(self):
        """Ajustar um clip não pode ser barrado por um vizinho distante.

        A checagem de sobreposição deve ignorar o próprio clip sendo
        substituído — senão mover 5s um clip já aprovado vira error.
        """
        curation.approve(self.estado, {"slug": "b", "start": 200.0, "end": 270.0})
        curation.approve(self.estado, {"slug": "b", "start": 205.0, "end": 275.0})
        self.assertEqual(len(self.estado["approved"]), 2)
        self.assertEqual(self.estado["approved"][1]["start"], 205.0)

    def test_ajuste_nao_pode_invadir_outro_corte(self):
        """Mas mover um clip PARA CIMA de outro continua sendo error."""
        curation.approve(self.estado, {"slug": "b", "start": 200.0, "end": 270.0})
        with self.assertRaises(ValueError):
            curation.approve(self.estado, {"slug": "b", "start": 120.0, "end": 190.0})

    def test_mesmo_slug_e_ajuste_de_tempo(self):
        """Reaprovar o mesmo clip com outro tempo substitui, não duplica."""
        curation.approve(self.estado, {"slug": "a", "start": 105.0, "end": 175.0})
        self.assertEqual(len(self.estado["approved"]), 1)
        self.assertEqual(self.estado["approved"][0]["start"], 105.0)


class TestAtribuicaoConfiavel(unittest.TestCase):
    """Alerta que mente treina o operador a ignorar a saída."""

    def test_episodio_bem_atribuido(self):
        segs = [
            {"start": 0.0, "end": 30.0, "speaker": "host",
             "text": "Conta pra gente sobre sua trajetória?"},
            {"start": 30.0, "end": 90.0, "speaker": "convidado",
             "text": "A gente começou com nossa primeira company."},
        ]
        self.assertTrue(curation.attribution_trustworthy(segs))

    def test_host_falando_da_propria_empresa_e_suspeito(self):
        segs = [
            {"start": 0.0, "end": 60.0, "speaker": "host",
             "text": "A gente montou nossa estrutura, nosso laboratório."},
            {"start": 60.0, "end": 70.0, "speaker": "host", "text": "Sim."},
        ]
        self.assertFalse(curation.attribution_trustworthy(segs))

    def test_suprime_alertas_que_leem_speaker(self):
        segs = [
            {"start": 0.0, "end": 65.0, "speaker": "host",
             "text": "A gente montou nossa estrutura, nosso laboratório."},
        ]
        alertas = curation.clip_warnings((0.0, 65.0), segs)
        self.assertFalse(any("convidado fala só" in a for a in alertas), alertas)
        self.assertFalse(any("abre com" in a for a in alertas), alertas)


class TestAberturaDoHost(unittest.TestCase):
    """Corte que abre com pergunta longa perde o espectador frio."""

    def setUp(self):
        self.segs = [
            {"start": 0.0, "end": 40.0, "text": "Pergunta longa do host?",
             "turn": False, "speaker": "host"},
            {"start": 40.0, "end": 110.0, "text": "Resposta do convidado.",
             "turn": True, "speaker": "convidado"},
        ]

    def test_alerta_quando_host_abre_demais(self):
        alertas = curation.clip_warnings((0.0, 70.0), self.segs)
        self.assertTrue(any("host" in a for a in alertas), alertas)

    def test_sem_alerta_quando_abre_no_convidado(self):
        alertas = curation.clip_warnings((40.0, 105.0), self.segs)
        self.assertFalse(any("abre com" in a for a in alertas), alertas)

    def test_sem_speaker_nao_alerta(self):
        """Origem sem marcador de troca: não acusar no escuro."""
        segs = [{"start": 0.0, "end": 70.0, "text": "Fala qualquer.", "turn": False}]
        self.assertEqual(curation.host_opening((0.0, 65.0), segs), 0.0)


class TestHesitacaoNumerica(unittest.TestCase):
    def test_detecta_uns(self):
        self.assertTrue(curation.has_hedged_number("eram uns 570, 580 clientes"))

    def test_detecta_acho_que(self):
        self.assertTrue(curation.has_hedged_number("acho que uns 40%"))

    def test_detecta_aproximadamente(self):
        self.assertTrue(curation.has_hedged_number("aproximadamente 2005"))

    def test_detecta_se_nao_me_engano(self):
        self.assertTrue(curation.has_hedged_number("se eu não me engano, 12"))

    def test_numero_cravado_nao_alerta(self):
        self.assertFalse(curation.has_hedged_number("fundada em 2006"))

    def test_texto_sem_numero_nao_alerta(self):
        self.assertFalse(curation.has_hedged_number("acho que é importante"))


class TestProtagonismo(unittest.TestCase):
    """Protagonismo do convidado.

    A atribuição de fala é ABSOLUTA: vem do campo `speaker`, resolvido
    globalmente no parse sobre o episódio inteiro. Não se deduz de '>>'
    dentro da fatia do clip, porque '>>' marca QUE trocou, não QUEM fala.
    """

    def test_convidado_domina(self):
        segs = [
            {"start": 0.0, "end": 10.0, "text": "Pergunta?", "turn": False,
             "speaker": "host"},
            {"start": 10.0, "end": 90.0, "text": "Resposta longa.", "turn": True,
             "speaker": "convidado"},
        ]
        frac = curation.guest_speech_fraction((0.0, 90.0), segs)
        self.assertGreater(frac, 0.8)

    def test_host_domina(self):
        segs = [
            {"start": 0.0, "end": 80.0, "text": "Fala longa do host.", "turn": False,
             "speaker": "host"},
            {"start": 80.0, "end": 90.0, "text": "Sim.", "turn": True,
             "speaker": "convidado"},
        ]
        frac = curation.guest_speech_fraction((0.0, 90.0), segs)
        self.assertLess(frac, 0.3)

    def test_sem_segmentos_retorna_zero(self):
        self.assertEqual(curation.guest_speech_fraction((0.0, 90.0), []), 0.0)

    def test_corte_no_meio_da_resposta_sem_turno_dentro(self):
        """Regressão do bug: clip 100% convidado que reportava 0.0.

        Nenhum segmento da fatia tem turn=True — a troca ficou para trás, no
        episódio. A fração tem de ser alta.
        """
        segs = [
            {"start": 0.0, "end": 20.0, "text": "Pergunta do host?", "turn": False,
             "speaker": "host"},
            {"start": 20.0, "end": 60.0, "text": "Comeco da resposta.", "turn": True,
             "speaker": "convidado"},
            {"start": 60.0, "end": 110.0, "text": "Meio da resposta.", "turn": False,
             "speaker": "convidado"},
            {"start": 110.0, "end": 160.0, "text": "Fim da resposta.", "turn": False,
             "speaker": "convidado"},
        ]
        frac = curation.guest_speech_fraction((60.0, 150.0), segs)
        self.assertEqual(frac, 1.0)

    def test_corte_majoritariamente_host(self):
        segs = [
            {"start": 0.0, "end": 70.0, "text": "Contexto longo do host.",
             "turn": False, "speaker": "host"},
            {"start": 70.0, "end": 90.0, "text": "Comeco da resposta.", "turn": True,
             "speaker": "convidado"},
        ]
        frac = curation.guest_speech_fraction((0.0, 90.0), segs)
        self.assertLess(frac, curation.config.GUEST_SPEECH_MIN)

    def test_speaker_ausente_nao_dispara_alerta_falso(self):
        """Sem `speaker` (vtt/Whisper, ou dado anterior ao fix) não dá para
        medir protagonismo. Devolve 1.0 — desliga o alerta em vez de acusar
        falsamente um clip que pode ser 100% convidado."""
        segs = [
            {"start": 0.0, "end": 45.0, "text": "Uma fala.", "turn": False},
            {"start": 45.0, "end": 90.0, "text": "Outra fala.", "turn": False},
        ]
        self.assertEqual(curation.guest_speech_fraction((0.0, 90.0), segs), 1.0)

    def test_speaker_ausente_nao_gera_alerta_de_protagonismo(self):
        segs = [
            {"start": 0.0, "end": 90.0, "text": "Uma fala.", "turn": False},
        ]
        alertas = curation.clip_warnings((0.0, 90.0), segs)
        self.assertFalse([a for a in alertas if "convidado fala" in a], alertas)

    def test_speaker_parcial_usa_so_o_que_esta_marcado(self):
        """Mistura de segmentos com e sem `speaker`: mede sobre os marcados."""
        segs = [
            {"start": 0.0, "end": 30.0, "text": "Host.", "turn": False,
             "speaker": "host"},
            {"start": 30.0, "end": 60.0, "text": "Sem marcacao.", "turn": False},
            {"start": 60.0, "end": 90.0, "text": "Convidado.", "turn": False,
             "speaker": "convidado"},
        ]
        frac = curation.guest_speech_fraction((0.0, 90.0), segs)
        self.assertAlmostEqual(frac, 0.5)


class TestOperacoes(unittest.TestCase):
    def setUp(self):
        self.estado = curation.new_state(meta=5)

    def test_aprovar_adiciona(self):
        curation.approve(self.estado, {"slug": "c1", "start": 10.0, "end": 80.0})
        self.assertEqual(len(self.estado["approved"]), 1)

    def test_rejeitar_registra_motivo(self):
        curation.reject(self.estado, {"start": 10.0, "end": 80.0,
                                         "summary": "trecho X"}, "gancho fraco")
        self.assertEqual(self.estado["rejected"][0]["reason"], "gancho fraco")

    def test_aprovar_alem_da_meta_da_erro(self):
        for i in range(5):
            curation.approve(self.estado, {"slug": f"c{i}", "start": i * 200.0,
                                            "end": i * 200.0 + 70.0})
        with self.assertRaises(ValueError):
            curation.approve(self.estado, {"slug": "c6", "start": 2000.0, "end": 2070.0})

    def test_composicao_por_tipo(self):
        curation.approve(self.estado, {"slug": "a", "start": 0.0, "end": 70.0,
                                        "kind": "story"})
        curation.approve(self.estado, {"slug": "b", "start": 200.0, "end": 270.0,
                                        "kind": "story"})
        comp = curation.composition(self.estado)
        self.assertEqual(comp["story"], 2)

    def test_tipos_ausentes(self):
        curation.approve(self.estado, {"slug": "a", "start": 0.0, "end": 70.0,
                                        "kind": "story"})
        faltando = curation.missing_kinds(self.estado)
        self.assertIn("thesis", faltando)
        self.assertNotIn("story", faltando)

    def test_motivos_acumulados(self):
        curation.reject(self.estado, {"start": 0.0, "end": 70.0}, "muito técnico")
        curation.reject(self.estado, {"start": 200.0, "end": 270.0}, "muito técnico")
        self.assertEqual(curation.reasons(self.estado), ["muito técnico"])

    def test_fechado_quando_atinge_meta(self):
        self.assertFalse(curation.is_closed(self.estado))
        for i in range(5):
            curation.approve(self.estado, {"slug": f"c{i}", "start": i * 200.0,
                                            "end": i * 200.0 + 70.0})
        self.assertTrue(curation.is_closed(self.estado))


class TestExportacao(unittest.TestCase):
    def test_exporta_momentos_com_campos_do_render(self):
        estado = curation.new_state(meta=2)
        curation.approve(estado, {
            "slug": "corte1", "start": 10.0, "end": 80.0, "kind": "story",
            "screen_text": "O ganho sem o custo", "post_caption": "...",
        })
        moments = curation.to_moments(estado)
        self.assertEqual(len(moments), 1)
        m = moments[0]
        self.assertEqual(m["slug"], "corte1")
        self.assertEqual(m["start"], 10.0)
        self.assertEqual(m["end"], 80.0)
        self.assertEqual(m["screen_text"], "O ganho sem o custo")

    def test_exportar_sem_aprovados_da_erro(self):
        estado = curation.new_state(meta=5)
        with self.assertRaises(ValueError):
            curation.to_moments(estado)


if __name__ == "__main__":
    unittest.main()
