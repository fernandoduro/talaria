"""Tests for the timestamped .txt transcript parser."""
import os
import unittest

from talaria import txt_parse

FIXTURE = os.path.join(os.path.dirname(__file__), "fixtures", "exemplo.txt")


def _block(start, end, text, turn=False):
    return {"start": start, "end": end, "text": text, "turn": turn}


class TestParseTxt(unittest.TestCase):
    def setUp(self):
        self.segs = txt_parse.parse_txt(FIXTURE)

    def test_produces_segments(self):
        self.assertGreater(len(self.segs), 0)

    def test_every_segment_has_the_fields(self):
        for s in self.segs:
            self.assertIn("start", s)
            self.assertIn("end", s)
            self.assertIn("text", s)
            self.assertIn("turn", s)

    def test_end_is_always_after_start(self):
        for s in self.segs:
            self.assertGreater(s["end"], s["start"], msg=str(s))

    def test_no_overlap(self):
        for a, b in zip(self.segs, self.segs[1:]):
            self.assertLessEqual(a["end"], b["start"] + 0.001)

    def test_first_segment_starts_at_10s(self):
        self.assertEqual(self.segs[0]["start"], 10.0)

    def test_turn_marker_is_detected(self):
        self.assertTrue(any(s["turn"] for s in self.segs))

    def test_marker_is_removed_from_the_text(self):
        for s in self.segs:
            self.assertFalse(s["text"].startswith(">>"), msg=s["text"])

    def test_hour_minute_second_format(self):
        # 1:02:03 = 3723s
        self.assertTrue(any(s["start"] == 3723.0 for s in self.segs),
                        msg="H:MM:SS não foi parseado")

    def test_total_duration_closes_the_last_segment(self):
        segs = txt_parse.parse_txt(FIXTURE, total_duration=4000.0)
        self.assertEqual(segs[-1]["end"], 4000.0)

    def test_last_segment_estimated_from_speaking_rate(self):
        last = self.segs[-1]
        self.assertGreater(last["end"] - last["start"], 1.0)

    def test_strips_sound_tags_and_html_entities(self):
        combined = " ".join(s["text"] for s in self.segs)
        self.assertNotIn("[crosstalk]", combined)
        self.assertNotIn("&amp;", combined)
        # The fixture carries both, so neither assertion can pass vacuously.
        raw = open(FIXTURE, encoding="utf-8").read()
        self.assertIn("[crosstalk]", raw)
        self.assertIn("&amp;", raw)


class TestRegroupIntoSentences(unittest.TestCase):
    def test_joins_blocks_until_punctuation(self):
        blocks = [
            _block(0.0, 5.0, "primeira parte da frase"),
            _block(5.0, 10.0, "que termina aqui."),
            _block(10.0, 15.0, "Outra frase."),
        ]
        segs = txt_parse.regroup_into_sentences(blocks)
        self.assertEqual(len(segs), 2)
        self.assertEqual(segs[0]["text"], "primeira parte da frase que termina aqui.")
        self.assertEqual(segs[0]["start"], 0.0)
        self.assertEqual(segs[0]["end"], 10.0)

    def test_turn_change_breaks_the_segment(self):
        blocks = [
            _block(0.0, 5.0, "fala sem pontuacao final"),
            _block(5.0, 10.0, "response do outro", turn=True),
        ]
        segs = txt_parse.regroup_into_sentences(blocks)
        self.assertEqual(len(segs), 2)

    def test_breaks_at_maximum_length(self):
        # no closing punctuation: only the character limit can break it
        blocks = [_block(float(i * 2), float(i * 2 + 2), "palavra " * 12)
                  for i in range(4)]
        segs = txt_parse.regroup_into_sentences(blocks)
        self.assertGreater(len(segs), 1, msg="SEG_MAX_CHARS não quebrou o segmento")

    def test_empty_list(self):
        self.assertEqual(txt_parse.regroup_into_sentences([]), [])


class TestSpeakerResolution(unittest.TestCase):
    """The speaker is resolved globally, over the whole episode.

    The '>>' marker says THAT the speaker changed, not WHO started talking.
    Since the podcast opens with the hosts, the first segment is host and each
    change alternates from there.
    """

    def setUp(self):
        self.segs = txt_parse.parse_txt(FIXTURE)

    def test_every_segment_has_a_speaker(self):
        for s in self.segs:
            self.assertIn("speaker", s, msg=str(s))
            self.assertIn(s["speaker"], ("host", "guest"), msg=str(s))

    def test_first_segment_is_host(self):
        self.assertEqual(self.segs[0]["speaker"], "host")

    def test_speaker_alternates_on_each_turn(self):
        previous = None
        for s in self.segs:
            if previous is not None and s["turn"]:
                self.assertNotEqual(s["speaker"], previous["speaker"], msg=str(s))
            previous = s

    def test_segments_between_turns_inherit_the_same_speaker(self):
        previous = None
        for s in self.segs:
            if previous is not None and not s["turn"]:
                self.assertEqual(s["speaker"], previous["speaker"], msg=str(s))
            previous = s

    def test_explicit_alternation(self):
        blocks = [
            _block(0.0, 5.0, "Abertura do host."),
            _block(5.0, 10.0, "Resposta do convidado.", turn=True),
            _block(10.0, 15.0, "Continua a response."),
            _block(15.0, 20.0, "Pergunta do host?", turn=True),
        ]
        segs = txt_parse.regroup_into_sentences(blocks)
        segs = txt_parse.resolve_speakers(segs)
        self.assertEqual([s["speaker"] for s in segs],
                         ["host", "guest", "guest", "host"])

    def test_empty_list_does_not_break(self):
        self.assertEqual(txt_parse.resolve_speakers([]), [])

    def test_first_segment_with_turn_is_still_host(self):
        """A transcript that opens with '>>' must not invert the episode."""
        blocks = [
            _block(0.0, 5.0, "Abertura do host.", turn=True),
            _block(5.0, 10.0, "Resposta do convidado.", turn=True),
        ]
        segs = txt_parse.resolve_speakers(txt_parse.regroup_into_sentences(blocks))
        self.assertEqual([s["speaker"] for s in segs], ["host", "guest"])

    def test_host_backchannel_shifts_the_attribution(self):
        """KNOWN RISK, not fixed — documents the current behaviour.

        A host's "Right."/"I see." marked with '>>' counts as a real change and
        shifts everything after it. Here the guest's second stretch comes out
        labelled host. No conservative heuristic was applied: in the real
        transcript the backchannel ('>> Maravilha.') has a 29s duration — the
        `end` comes from the next timestamp, not from the speech — and has
        DIFFERENT speakers on either side, so neither duration nor "same
        speaker around it" identifies it.
        """
        blocks = [
            _block(0.0, 5.0, "Pergunta do host?"),
            _block(5.0, 10.0, "Comeco da response.", turn=True),
            _block(10.0, 12.0, "Sei.", turn=True),          # host backchannel
            _block(12.0, 20.0, "Continuo respondendo."),    # still the guest
            _block(20.0, 30.0, "E foi assim que crescemos."),
        ]
        segs = txt_parse.resolve_speakers(txt_parse.regroup_into_sentences(blocks))
        # Ideally [host, guest, host, guest, guest]. With an odd number of
        # spurious changes, the guest's answer comes out labelled host from
        # there on and underestimates the fraction in the clip.
        self.assertEqual([s["speaker"] for s in segs],
                         ["host", "guest", "host", "host", "host"])


if __name__ == "__main__":
    unittest.main()
