"""Tests for assembling the reading packets."""
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
                "city": "Ribeirão Açaí", "uf": "SP",
                "guests": [{"name": "Teresa", "role": "sócio",
                                "linkedin": "https://linkedin.com/in/x"}],
                "topics": ["biotech", "B2B para B2C"],
            }, f)
        with open(layout.ensure_dir(layout.transcript(self.d)), "w", encoding="utf-8") as f:
            json.dump({"segments": [
                {"start": 10.0, "end": 15.0, "text": "Primeira fala.", "turn": False},
                {"start": 15.0, "end": 80.0, "text": "Segunda fala.", "turn": True},
            ]}, f)

    def test_formatted_transcript_has_timestamps(self):
        txt = brief.readable_transcript(self.d)
        self.assertIn("00:10", txt)
        self.assertIn("Primeira fala.", txt)

    def test_formatted_metadata(self):
        m = brief.readable_metadata(self.d)
        self.assertIn("Zarvik", m)
        self.assertIn("T2E07", m)
        self.assertIn("Ribeirão Açaí", m)
        self.assertIn("Teresa", m)

    def test_replaces_the_transcript_placeholder(self):
        tpl = "PROMPT AQUI\n\n{{TRANSCRICAO}}\n"
        out = brief.fill_template(tpl, transcript="XPTO", metadata="")
        self.assertIn("XPTO", out)
        self.assertNotIn("{{TRANSCRICAO}}", out)

    def test_replaces_the_metadata_placeholder(self):
        tpl = "PROMPT\n{{METADADOS}}\n"
        out = brief.fill_template(tpl, transcript="", metadata="DADOS")
        self.assertIn("DADOS", out)
        self.assertNotIn("{{METADADOS}}", out)

    def test_replaces_the_curation_placeholder(self):
        tpl = "PROMPT\n{{CURADORIA}}\n"
        out = brief.fill_template(tpl, transcript="", metadata="", curation="ESTADO")
        self.assertIn("ESTADO", out)
        self.assertNotIn("{{CURADORIA}}", out)

    def test_absent_placeholder_does_not_break(self):
        out = brief.fill_template("sem placeholder", transcript="X", metadata="Y")
        self.assertEqual(out, "sem placeholder")

    def test_readable_state_first_round(self):
        state = {"target": 5, "approved": [], "rejected": [], "rounds": 0}
        txt = brief.readable_curation(state)
        self.assertIn("PRIMEIRA RODADA", txt)
        self.assertIn("10", txt)

    def test_readable_state_with_rejections(self):
        state = {"target": 5, "rounds": 1,
                  "approved": [{"slug": "a", "start": 100.0, "end": 170.0,
                                 "kind": "story"}],
                  "rejected": [{"start": 300.0, "end": 370.0,
                                  "reason": "gancho fraco", "summary": "trecho X"}]}
        txt = brief.readable_curation(state)
        self.assertIn("gancho fraco", txt)
        self.assertIn("4", txt)          # slots_left remaining
        self.assertIn("05:00", txt)      # burned span in mm:ss


class TestBriefPosts(unittest.TestCase):
    """Reading packet for choosing quotes (the `post --clips` command)."""

    def setUp(self):
        self.d = tempfile.mkdtemp()
        with open(layout.ensure_dir(layout.episode(self.d)), "w", encoding="utf-8") as f:
            json.dump({
                "season": 2, "episode": 8, "company": "Zarvik",
                "city": "Ribeirão Açaí", "uf": "SP", "topics": [],
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

    def test_brings_the_speech_inside_the_clip(self):
        out = brief.build_posts(self.d, [self.clip])
        with open(out, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("corte1_mar_azul", text)
        self.assertIn("A oportunidade estava do lado.", text)
        self.assertIn("E a gente não viu.", text)

    def test_brings_speech_from_the_segment_crossing_the_boundary(self):
        """A segment split by the boundary is still speech from the clip.

        Requiring full containment hid the LAST sentence of every clip —
        exactly where the punchline usually sits. The video shows that speech
        (render._segments_in_cut trims the text), so the reading packet has to
        show it too.
        """
        clip = {"slug": "c", "start": 10.0, "end": 16.0, "kind": "thesis",
                 "screen_text": "", "post_caption": "", "trecho": ""}
        text = brief.clip_speech(self.d, clip)
        self.assertIn("A oportunidade estava do lado.", text)
        # The 2nd segment (14-18s) is trimmed by the boundary at 16s: the half
        # the clip reaches goes in, not the whole block and not nothing.
        self.assertIn("E a", text)
        self.assertNotIn("não viu", text)

    def test_does_not_bring_speech_from_outside_the_clip(self):
        out = brief.build_posts(self.d, [self.clip])
        with open(out, encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("Fala de outro trecho.", text)

    def test_brings_metadata_and_the_fit_limit(self):
        out = brief.build_posts(self.d, [self.clip])
        with open(out, encoding="utf-8") as f:
            text = f.read()
        self.assertIn("Marina Siqueira", text)
        self.assertIn("100 caracteres", text)
        # the prompt placeholders have to have been replaced
        self.assertNotIn("{{", text)

    def test_writes_to_brief_posts_md(self):
        out = brief.build_posts(self.d, [self.clip])
        self.assertEqual(out, layout.brief(self.d, "posts"))
        self.assertTrue(os.path.exists(out))


if __name__ == "__main__":
    unittest.main()
