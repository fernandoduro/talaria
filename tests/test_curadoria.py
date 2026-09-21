"""Testes do estado da curadoria iterativa."""
import unittest

from talaria import curadoria


class TestSobreposicao(unittest.TestCase):
    def test_sobreposicao_total(self):
        self.assertTrue(curadoria.sobrepoe((10, 70), (10, 70)))

    def test_sem_sobreposicao(self):
        self.assertFalse(curadoria.sobrepoe((10, 70), (100, 160)))

    def test_encosta_nao_sobrepoe(self):
        self.assertFalse(curadoria.sobrepoe((10, 70), (70, 130)))

    def test_sobreposicao_pequena_abaixo_do_limiar(self):
        # 5s de 60s = 8% — abaixo do limiar de 30%, não conta
        self.assertFalse(curadoria.sobrepoe((10, 70), (65, 125)))

    def test_sobreposicao_grande_acima_do_limiar(self):
        # corte 10s adiante do rejeitado — mesmo trecho disfarçado
        self.assertTrue(curadoria.sobrepoe((10, 70), (20, 80)))


class TestQueimados(unittest.TestCase):
    def setUp(self):
        self.estado = {
            "meta": 5,
            "aprovados": [{"slug": "a", "start": 100.0, "end": 170.0}],
            "rejeitados": [{"start": 300.0, "end": 370.0, "motivo": "gancho fraco"}],
            "rodadas": 1,
        }

    def test_faixas_incluem_aprovados_e_rejeitados(self):
        faixas = curadoria.faixas_queimadas(self.estado)
        self.assertIn((100.0, 170.0), faixas)
        self.assertIn((300.0, 370.0), faixas)

    def test_proposta_sobre_rejeitado_e_queimada(self):
        self.assertTrue(curadoria.esta_queimado((310.0, 380.0), self.estado))

    def test_proposta_livre_nao_e_queimada(self):
        self.assertFalse(curadoria.esta_queimado((500.0, 570.0), self.estado))

    def test_vagas_restantes(self):
        self.assertEqual(curadoria.vagas(self.estado), 4)

    def test_vagas_nunca_negativa(self):
        e = dict(self.estado, aprovados=[{"slug": str(i)} for i in range(7)])
        self.assertEqual(curadoria.vagas(e), 0)


class TestEstadoInicial(unittest.TestCase):
    def test_novo_estado_tem_meta(self):
        e = curadoria.novo_estado(meta=5)
        self.assertEqual(e["meta"], 5)
        self.assertEqual(e["aprovados"], [])
        self.assertEqual(e["rejeitados"], [])
        self.assertEqual(e["rodadas"], 0)


class TestValidacoes(unittest.TestCase):
    def setUp(self):
        self.segs = [
            {"start": 0.0, "end": 30.0, "text": "Pergunta do host?", "turn": False},
            {"start": 30.0, "end": 95.0, "text": "Resposta longa do convidado.", "turn": True},
            {"start": 95.0, "end": 120.0, "text": "Continua a resposta.", "turn": False},
        ]

    def test_duracao_dentro_da_faixa(self):
        ok, msgs = curadoria.valida_corte((0.0, 75.0), self.segs, {})
        self.assertTrue(ok, msgs)

    def test_duracao_curta_demais(self):
        ok, msgs = curadoria.valida_corte((0.0, 30.0), self.segs, {})
        self.assertFalse(ok)
        self.assertTrue(any("duração" in m for m in msgs))

    def test_duracao_longa_demais(self):
        ok, msgs = curadoria.valida_corte((0.0, 120.0), self.segs, {})
        self.assertFalse(ok)
        self.assertTrue(any("duração" in m for m in msgs))

    def test_fronteira_fora_de_segmento(self):
        ok, msgs = curadoria.valida_corte((12.0, 87.0), self.segs, {})
        self.assertFalse(ok)
        self.assertTrue(any("fronteira" in m for m in msgs))

    def test_corte_sobre_faixa_queimada(self):
        estado = {"meta": 5, "aprovados": [], "rodadas": 0,
                  "rejeitados": [{"start": 0.0, "end": 75.0}]}
        ok, msgs = curadoria.valida_corte((0.0, 75.0), self.segs, estado)
        self.assertFalse(ok)
        self.assertTrue(any("queimad" in m for m in msgs))


class TestFimEmFraseCompleta(unittest.TestCase):
    """O fim do corte tem que fechar frase, não só coincidir com fim de bloco.

    A transcrição do YouTube quebra os blocos por TEMPO, não por pontuação:
    um bloco pode terminar no meio de uma frase. Conferir apenas o limite do
    bloco deixava passar corte que termina em palavra solta — foi o que
    aconteceu no EP8 (bloco 1655-1663 fecha em "...transferência de tecnologia
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
        ok, msgs = curadoria.valida_corte((30.0, 95.0), self.segs, {})
        self.assertTrue(ok, msgs)

    def test_fim_no_meio_de_frase_reprova(self):
        """Bloco 95-160 acaba sem pontuação final: o corte fica pela metade."""
        ok, msgs = curadoria.valida_corte((95.0, 160.0), self.segs, {})
        self.assertFalse(ok)
        self.assertTrue(any("fim" in m.lower() for m in msgs), msgs)

    def test_fim_com_reticencias_e_aceito(self):
        segs = [{"start": 0.0, "end": 65.0, "text": "E aí a gente parou...", "turn": False}]
        ok, msgs = curadoria.valida_corte((0.0, 65.0), segs, {})
        self.assertTrue(ok, msgs)

    def test_fim_com_interrogacao_e_aceito(self):
        segs = [{"start": 0.0, "end": 65.0, "text": "Como que a gente faz isso?", "turn": False}]
        ok, msgs = curadoria.valida_corte((0.0, 65.0), segs, {})
        self.assertTrue(ok, msgs)


class TestFinsDeFrase(unittest.TestCase):
    """Candidatos a fim de corte, para não escolher o ponto à mão."""

    def setUp(self):
        self.segs = [
            {"start": 0.0, "end": 30.0, "text": "Abertura da conversa.", "turn": False},
            {"start": 30.0, "end": 70.0,
             "text": "Primeira ideia fecha aqui. E a segunda fecha aqui também.",
             "turn": False},
            {"start": 70.0, "end": 100.0, "text": "Bem depois do limite.", "turn": False},
        ]

    def test_devolve_apenas_duracoes_validas(self):
        for _inst, dur, _ctx in curadoria.fins_de_frase(self.segs, 0.0, 30.0, 100.0):
            self.assertGreaterEqual(dur, 60.0)
            self.assertLessEqual(dur, 90.0)

    def test_ordenado_por_instante(self):
        r = curadoria.fins_de_frase(self.segs, 0.0, 30.0, 100.0)
        self.assertEqual([x[0] for x in r], sorted(x[0] for x in r))

    def test_traz_contexto_do_trecho(self):
        r = curadoria.fins_de_frase(self.segs, 0.0, 30.0, 100.0)
        self.assertTrue(all(isinstance(x[2], str) and x[2] for x in r), r)

    def test_sem_candidato_fora_da_janela(self):
        self.assertEqual(curadoria.fins_de_frase(self.segs, 0.0, 95.0, 100.0), [])


class TestSobreposicaoEntreAprovados(unittest.TestCase):
    """Dois aprovados no mesmo trecho competem entre si na distribuição.

    `valida_corte` já barrava, mas quem chamava `aprovar()` direto escapava —
    no EP8 dois cortes dividiram 74s por isso.
    """

    def setUp(self):
        self.estado = curadoria.novo_estado(meta=5)
        curadoria.aprovar(self.estado, {"slug": "a", "start": 100.0, "end": 170.0})

    def test_recusa_corte_sobreposto(self):
        with self.assertRaises(ValueError) as cm:
            curadoria.aprovar(self.estado, {"slug": "b", "start": 150.0, "end": 220.0})
        self.assertIn("sobrepõe", str(cm.exception))

    def test_aceita_corte_disjunto(self):
        curadoria.aprovar(self.estado, {"slug": "b", "start": 200.0, "end": 270.0})
        self.assertEqual(len(self.estado["aprovados"]), 2)

    def test_ajuste_de_tempo_pode_encostar_em_outro(self):
        """Ajustar um corte não pode ser barrado por um vizinho distante.

        A checagem de sobreposição deve ignorar o próprio corte sendo
        substituído — senão mover 5s um corte já aprovado vira erro.
        """
        curadoria.aprovar(self.estado, {"slug": "b", "start": 200.0, "end": 270.0})
        curadoria.aprovar(self.estado, {"slug": "b", "start": 205.0, "end": 275.0})
        self.assertEqual(len(self.estado["aprovados"]), 2)
        self.assertEqual(self.estado["aprovados"][1]["start"], 205.0)

    def test_ajuste_nao_pode_invadir_outro_corte(self):
        """Mas mover um corte PARA CIMA de outro continua sendo erro."""
        curadoria.aprovar(self.estado, {"slug": "b", "start": 200.0, "end": 270.0})
        with self.assertRaises(ValueError):
            curadoria.aprovar(self.estado, {"slug": "b", "start": 120.0, "end": 190.0})

    def test_mesmo_slug_e_ajuste_de_tempo(self):
        """Reaprovar o mesmo corte com outro tempo substitui, não duplica."""
        curadoria.aprovar(self.estado, {"slug": "a", "start": 105.0, "end": 175.0})
        self.assertEqual(len(self.estado["aprovados"]), 1)
        self.assertEqual(self.estado["aprovados"][0]["start"], 105.0)


class TestAtribuicaoConfiavel(unittest.TestCase):
    """Alerta que mente treina o operador a ignorar a saída."""

    def test_episodio_bem_atribuido(self):
        segs = [
            {"start": 0.0, "end": 30.0, "speaker": "host",
             "text": "Conta pra gente sobre sua trajetória?"},
            {"start": 30.0, "end": 90.0, "speaker": "convidado",
             "text": "A gente começou com nossa primeira empresa."},
        ]
        self.assertTrue(curadoria.atribuicao_confiavel(segs))

    def test_host_falando_da_propria_empresa_e_suspeito(self):
        segs = [
            {"start": 0.0, "end": 60.0, "speaker": "host",
             "text": "A gente montou nossa estrutura, nosso laboratório."},
            {"start": 60.0, "end": 70.0, "speaker": "host", "text": "Sim."},
        ]
        self.assertFalse(curadoria.atribuicao_confiavel(segs))

    def test_suprime_alertas_que_leem_speaker(self):
        segs = [
            {"start": 0.0, "end": 65.0, "speaker": "host",
             "text": "A gente montou nossa estrutura, nosso laboratório."},
        ]
        alertas = curadoria.alertas_corte((0.0, 65.0), segs)
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
        alertas = curadoria.alertas_corte((0.0, 70.0), self.segs)
        self.assertTrue(any("host" in a for a in alertas), alertas)

    def test_sem_alerta_quando_abre_no_convidado(self):
        alertas = curadoria.alertas_corte((40.0, 105.0), self.segs)
        self.assertFalse(any("abre com" in a for a in alertas), alertas)

    def test_sem_speaker_nao_alerta(self):
        """Origem sem marcador de troca: não acusar no escuro."""
        segs = [{"start": 0.0, "end": 70.0, "text": "Fala qualquer.", "turn": False}]
        self.assertEqual(curadoria.abertura_do_host((0.0, 65.0), segs), 0.0)


class TestHesitacaoNumerica(unittest.TestCase):
    def test_detecta_uns(self):
        self.assertTrue(curadoria.tem_hesitacao_numerica("eram uns 570, 580 clientes"))

    def test_detecta_acho_que(self):
        self.assertTrue(curadoria.tem_hesitacao_numerica("acho que uns 40%"))

    def test_detecta_aproximadamente(self):
        self.assertTrue(curadoria.tem_hesitacao_numerica("aproximadamente 2005"))

    def test_detecta_se_nao_me_engano(self):
        self.assertTrue(curadoria.tem_hesitacao_numerica("se eu não me engano, 12"))

    def test_numero_cravado_nao_alerta(self):
        self.assertFalse(curadoria.tem_hesitacao_numerica("fundada em 2006"))

    def test_texto_sem_numero_nao_alerta(self):
        self.assertFalse(curadoria.tem_hesitacao_numerica("acho que é importante"))


class TestProtagonismo(unittest.TestCase):
    """Seção 5 do prompt de cortes — protagonismo do convidado.

    A atribuição de fala é ABSOLUTA: vem do campo `speaker`, resolvido
    globalmente no parse sobre o episódio inteiro. Não se deduz de '>>'
    dentro da fatia do corte, porque '>>' marca QUE trocou, não QUEM fala.
    """

    def test_convidado_domina(self):
        segs = [
            {"start": 0.0, "end": 10.0, "text": "Pergunta?", "turn": False,
             "speaker": "host"},
            {"start": 10.0, "end": 90.0, "text": "Resposta longa.", "turn": True,
             "speaker": "convidado"},
        ]
        frac = curadoria.fracao_convidado((0.0, 90.0), segs)
        self.assertGreater(frac, 0.8)

    def test_host_domina(self):
        segs = [
            {"start": 0.0, "end": 80.0, "text": "Fala longa do host.", "turn": False,
             "speaker": "host"},
            {"start": 80.0, "end": 90.0, "text": "Sim.", "turn": True,
             "speaker": "convidado"},
        ]
        frac = curadoria.fracao_convidado((0.0, 90.0), segs)
        self.assertLess(frac, 0.3)

    def test_sem_segmentos_retorna_zero(self):
        self.assertEqual(curadoria.fracao_convidado((0.0, 90.0), []), 0.0)

    def test_corte_no_meio_da_resposta_sem_turno_dentro(self):
        """Regressão do bug: corte 100% convidado que reportava 0.0.

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
        frac = curadoria.fracao_convidado((60.0, 150.0), segs)
        self.assertEqual(frac, 1.0)

    def test_corte_majoritariamente_host(self):
        segs = [
            {"start": 0.0, "end": 70.0, "text": "Contexto longo do host.",
             "turn": False, "speaker": "host"},
            {"start": 70.0, "end": 90.0, "text": "Comeco da resposta.", "turn": True,
             "speaker": "convidado"},
        ]
        frac = curadoria.fracao_convidado((0.0, 90.0), segs)
        self.assertLess(frac, curadoria.config.FALA_CONVIDADO_MIN)

    def test_speaker_ausente_nao_dispara_alerta_falso(self):
        """Sem `speaker` (vtt/Whisper, ou dado anterior ao fix) não dá para
        medir protagonismo. Devolve 1.0 — desliga o alerta em vez de acusar
        falsamente um corte que pode ser 100% convidado."""
        segs = [
            {"start": 0.0, "end": 45.0, "text": "Uma fala.", "turn": False},
            {"start": 45.0, "end": 90.0, "text": "Outra fala.", "turn": False},
        ]
        self.assertEqual(curadoria.fracao_convidado((0.0, 90.0), segs), 1.0)

    def test_speaker_ausente_nao_gera_alerta_de_protagonismo(self):
        segs = [
            {"start": 0.0, "end": 90.0, "text": "Uma fala.", "turn": False},
        ]
        alertas = curadoria.alertas_corte((0.0, 90.0), segs)
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
        frac = curadoria.fracao_convidado((0.0, 90.0), segs)
        self.assertAlmostEqual(frac, 0.5)


class TestOperacoes(unittest.TestCase):
    def setUp(self):
        self.estado = curadoria.novo_estado(meta=5)

    def test_aprovar_adiciona(self):
        curadoria.aprovar(self.estado, {"slug": "c1", "start": 10.0, "end": 80.0})
        self.assertEqual(len(self.estado["aprovados"]), 1)

    def test_rejeitar_registra_motivo(self):
        curadoria.rejeitar(self.estado, {"start": 10.0, "end": 80.0,
                                         "resumo": "trecho X"}, "gancho fraco")
        self.assertEqual(self.estado["rejeitados"][0]["motivo"], "gancho fraco")

    def test_aprovar_alem_da_meta_da_erro(self):
        for i in range(5):
            curadoria.aprovar(self.estado, {"slug": f"c{i}", "start": i * 200.0,
                                            "end": i * 200.0 + 70.0})
        with self.assertRaises(ValueError):
            curadoria.aprovar(self.estado, {"slug": "c6", "start": 2000.0, "end": 2070.0})

    def test_composicao_por_tipo(self):
        curadoria.aprovar(self.estado, {"slug": "a", "start": 0.0, "end": 70.0,
                                        "tipo": "historia"})
        curadoria.aprovar(self.estado, {"slug": "b", "start": 200.0, "end": 270.0,
                                        "tipo": "historia"})
        comp = curadoria.composicao(self.estado)
        self.assertEqual(comp["historia"], 2)

    def test_tipos_ausentes(self):
        curadoria.aprovar(self.estado, {"slug": "a", "start": 0.0, "end": 70.0,
                                        "tipo": "historia"})
        faltando = curadoria.tipos_ausentes(self.estado)
        self.assertIn("tese", faltando)
        self.assertNotIn("historia", faltando)

    def test_motivos_acumulados(self):
        curadoria.rejeitar(self.estado, {"start": 0.0, "end": 70.0}, "muito técnico")
        curadoria.rejeitar(self.estado, {"start": 200.0, "end": 270.0}, "muito técnico")
        self.assertEqual(curadoria.motivos(self.estado), ["muito técnico"])

    def test_fechado_quando_atinge_meta(self):
        self.assertFalse(curadoria.fechado(self.estado))
        for i in range(5):
            curadoria.aprovar(self.estado, {"slug": f"c{i}", "start": i * 200.0,
                                            "end": i * 200.0 + 70.0})
        self.assertTrue(curadoria.fechado(self.estado))


class TestExportacao(unittest.TestCase):
    def test_exporta_momentos_com_campos_do_render(self):
        estado = curadoria.novo_estado(meta=2)
        curadoria.aprovar(estado, {
            "slug": "corte1", "start": 10.0, "end": 80.0, "tipo": "historia",
            "texto_tela": "O ganho sem o custo", "legenda_post": "...",
        })
        momentos = curadoria.para_momentos(estado)
        self.assertEqual(len(momentos), 1)
        m = momentos[0]
        self.assertEqual(m["slug"], "corte1")
        self.assertEqual(m["start"], 10.0)
        self.assertEqual(m["end"], 80.0)
        self.assertEqual(m["texto_tela"], "O ganho sem o custo")

    def test_exportar_sem_aprovados_da_erro(self):
        estado = curadoria.novo_estado(meta=5)
        with self.assertRaises(ValueError):
            curadoria.para_momentos(estado)


if __name__ == "__main__":
    unittest.main()
