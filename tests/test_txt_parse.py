"""Testes do parser de transcrição .txt com timestamps."""
import os
import unittest

from talaria import txt_parse

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "exemplo.txt")


def _bloco(start, end, text, turn=False):
    return {"start": start, "end": end, "text": text, "turn": turn}


class TestParseTxt(unittest.TestCase):
    def setUp(self):
        self.segs = txt_parse.parse_txt(FIXTURE)

    def test_gera_segmentos(self):
        self.assertGreater(len(self.segs), 0)

    def test_todo_segmento_tem_campos(self):
        for s in self.segs:
            self.assertIn("start", s)
            self.assertIn("end", s)
            self.assertIn("text", s)
            self.assertIn("turn", s)

    def test_end_sempre_maior_que_start(self):
        for s in self.segs:
            self.assertGreater(s["end"], s["start"], msg=str(s))

    def test_sem_sobreposicao(self):
        for a, b in zip(self.segs, self.segs[1:]):
            self.assertLessEqual(a["end"], b["start"] + 0.001)

    def test_primeiro_segmento_comeca_em_10s(self):
        self.assertEqual(self.segs[0]["start"], 10.0)

    def test_marcador_de_turno_detectado(self):
        self.assertTrue(any(s["turn"] for s in self.segs))

    def test_marcador_removido_do_texto(self):
        for s in self.segs:
            self.assertFalse(s["text"].startswith(">>"), msg=s["text"])

    def test_formato_hora_minuto_segundo(self):
        # 1:02:03 = 3723s
        self.assertTrue(any(s["start"] == 3723.0 for s in self.segs),
                        msg="H:MM:SS não foi parseado")

    def test_total_duration_fecha_ultimo_segmento(self):
        segs = txt_parse.parse_txt(FIXTURE, total_duration=4000.0)
        self.assertEqual(segs[-1]["end"], 4000.0)

    def test_ultimo_segmento_estimado_por_ritmo_de_fala(self):
        ultimo = self.segs[-1]
        self.assertGreater(ultimo["end"] - ultimo["start"], 1.0)

    def test_remove_marcacao_de_som_e_entidades(self):
        todo = " ".join(s["text"] for s in self.segs)
        self.assertNotIn("[música]", todo)
        self.assertNotIn("&amp;", todo)


class TestRegroupIntoSentences(unittest.TestCase):
    def test_junta_blocos_ate_pontuacao(self):
        blocks = [
            _bloco(0.0, 5.0, "primeira parte da frase"),
            _bloco(5.0, 10.0, "que termina aqui."),
            _bloco(10.0, 15.0, "Outra frase."),
        ]
        segs = txt_parse.regroup_into_sentences(blocks)
        self.assertEqual(len(segs), 2)
        self.assertEqual(segs[0]["text"], "primeira parte da frase que termina aqui.")
        self.assertEqual(segs[0]["start"], 0.0)
        self.assertEqual(segs[0]["end"], 10.0)

    def test_troca_de_turno_quebra_segmento(self):
        blocks = [
            _bloco(0.0, 5.0, "fala sem pontuacao final"),
            _bloco(5.0, 10.0, "resposta do outro", turn=True),
        ]
        segs = txt_parse.regroup_into_sentences(blocks)
        self.assertEqual(len(segs), 2)

    def test_quebra_por_tamanho_maximo(self):
        # sem pontuação final: só o limite de caracteres pode quebrar
        blocks = [_bloco(float(i * 2), float(i * 2 + 2), "palavra " * 12)
                  for i in range(4)]
        segs = txt_parse.regroup_into_sentences(blocks)
        self.assertGreater(len(segs), 1, msg="SEG_MAX_CHARS não quebrou o segmento")

    def test_lista_vazia(self):
        self.assertEqual(txt_parse.regroup_into_sentences([]), [])


class TestResolucaoDeFalante(unittest.TestCase):
    """O falante é resolvido globalmente, sobre o episódio inteiro.

    O marcador '>>' diz QUE trocou de interlocutor, não QUEM passou a falar.
    Como o podcast abre com os apresentadores, o primeiro segmento é host e
    cada troca alterna a partir dali.
    """

    def setUp(self):
        self.segs = txt_parse.parse_txt(FIXTURE)

    def test_todo_segmento_tem_speaker(self):
        for s in self.segs:
            self.assertIn("speaker", s, msg=str(s))
            self.assertIn(s["speaker"], ("host", "convidado"), msg=str(s))

    def test_primeiro_segmento_e_host(self):
        self.assertEqual(self.segs[0]["speaker"], "host")

    def test_speaker_alterna_em_cada_turno(self):
        anterior = None
        for s in self.segs:
            if anterior is not None and s["turn"]:
                self.assertNotEqual(s["speaker"], anterior["speaker"], msg=str(s))
            anterior = s

    def test_segmentos_entre_turnos_herdam_o_mesmo_speaker(self):
        anterior = None
        for s in self.segs:
            if anterior is not None and not s["turn"]:
                self.assertEqual(s["speaker"], anterior["speaker"], msg=str(s))
            anterior = s

    def test_alternancia_explicita(self):
        blocks = [
            _bloco(0.0, 5.0, "Abertura do host."),
            _bloco(5.0, 10.0, "Resposta do convidado.", turn=True),
            _bloco(10.0, 15.0, "Continua a resposta."),
            _bloco(15.0, 20.0, "Pergunta do host?", turn=True),
        ]
        segs = txt_parse.regroup_into_sentences(blocks)
        segs = txt_parse.resolve_speakers(segs)
        self.assertEqual([s["speaker"] for s in segs],
                         ["host", "convidado", "convidado", "host"])

    def test_lista_vazia_nao_quebra(self):
        self.assertEqual(txt_parse.resolve_speakers([]), [])

    def test_primeiro_segmento_com_turn_ainda_e_host(self):
        """Transcrição que já abre com '>>' não deve inverter o episódio."""
        blocks = [
            _bloco(0.0, 5.0, "Abertura do host.", turn=True),
            _bloco(5.0, 10.0, "Resposta do convidado.", turn=True),
        ]
        segs = txt_parse.resolve_speakers(txt_parse.regroup_into_sentences(blocks))
        self.assertEqual([s["speaker"] for s in segs], ["host", "convidado"])

    def test_backchannel_do_host_desloca_atribuicao(self):
        """RISCO CONHECIDO, não corrigido — documenta o comportamento atual.

        Um "Sei."/"Certo." do host marcado com '>>' conta como troca real e
        desloca tudo o que vem depois. Aqui o segundo trecho do convidado sai
        rotulado como host. Nenhuma heurística conservadora foi aplicada: na
        transcrição real o backchannel ('>> Maravilha.') aparece com 29s de
        duração — o `end` vem do timestamp seguinte, não da fala — e tem
        falantes DIFERENTES dos dois lados, então nem duração nem "mesmo
        falante em volta" o identificam.
        """
        blocks = [
            _bloco(0.0, 5.0, "Pergunta do host?"),
            _bloco(5.0, 10.0, "Comeco da resposta.", turn=True),
            _bloco(10.0, 12.0, "Sei.", turn=True),          # backchannel do host
            _bloco(12.0, 20.0, "Continuo respondendo."),    # ainda o convidado
            _bloco(20.0, 30.0, "E foi assim que crescemos."),
        ]
        segs = txt_parse.resolve_speakers(txt_parse.regroup_into_sentences(blocks))
        # O ideal seria [host, convidado, host, convidado, convidado]. Com um
        # número ímpar de trocas espúrias, a resposta do convidado sai rotulada
        # como host daí em diante e subestima a fração no corte.
        self.assertEqual([s["speaker"] for s in segs],
                         ["host", "convidado", "host", "host", "host"])


if __name__ == "__main__":
    unittest.main()
