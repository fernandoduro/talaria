"""Assembling the caption segments inside a clip."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from talaria import audio, config, layout, render


class TestValleyBefore(unittest.TestCase):
    """A pause only counts as an end of speech if the silence LASTS.

    In continuous speech the energy dips between words every ~100ms. Cutting at
    the first dip splits the sentence: one clip ended in an 80ms internal pause
    and the speech vanished before "...a project that long".
    """

    def _points(self, spec):
        """[(t, dB)] from [(n_windows, dB)]."""
        points, t = [], 0.0
        for n, db in spec:
            for _ in range(n):
                points.append((round(t, 3), db))
                t += audio.WINDOW_S
        return points

    def test_ignores_a_short_internal_pause(self):
        """4 windows (80ms) of silence mid-speech is not a sentence end."""
        points = self._points([(10, -18.0), (4, -44.0), (10, -18.0)])
        i = 10
        self.assertLess(
            audio._silence_duration(points, i, audio.PAUSE_THRESHOLD_DB),
            audio.SILENCE_MIN_S)

    def test_accepts_a_long_silence(self):
        """15 windows (300ms) of silence is an end of speech."""
        points = self._points([(10, -18.0), (15, -44.0)])
        self.assertGreaterEqual(
            audio._silence_duration(points, 10, audio.PAUSE_THRESHOLD_DB),
            audio.SILENCE_MIN_S)

    def test_minimum_silence_exceeds_the_inter_word_pause(self):
        """The inter-word pause runs 40-100ms; the threshold must sit above."""
        self.assertGreater(audio.SILENCE_MIN_S, 0.12)


class TestAdjustRespectsMinimum(unittest.TestCase):
    """Neither valley nor margin may take the clip below the minimum."""

    def test_margin_does_not_drop_below_the_minimum(self):
        from talaria import config
        start = 100.0
        end = start + config.CLIP_MIN_S          # exactly at the limit
        self.assertGreaterEqual(
            render.apply_end_margin(end, start) - start, config.CLIP_MIN_S)


class TestClipsMidWord(unittest.TestCase):
    """Telling speech that ENDS from speech that was CUT OFF.

    All speech ends on a syllable, so "there is energy at the end" flags every
    clip. The signal is the decay: a word ending decays; a word cut off stops
    abruptly, still at a high level. Measured numbers.
    """

    def test_threshold_separates_the_measured_cases(self):
        # defective clip: -31 -28 -31 (stable, high)
        self.assertFalse(self._decays([-31.1, -28.5, -30.6]))
        # correct "importadas.": -25.8 -> -39.4 (plunges)
        self.assertTrue(self._decays([-25.8, -25.9, -39.4]))

    def _decays(self, dbs, threshold=-25.0):
        """Reproduces the clips_mid_word decision over a measured series."""
        if dbs[-1] <= threshold - 10.0:
            return True
        return (dbs[0] - dbs[-1]) >= 8.0

    def test_silence_at_the_end_never_flags(self):
        self.assertTrue(self._decays([-44.0, -46.0, -48.0]))

    def test_window_is_narrow(self):
        """A wide window would catch the final syllable of any speech."""
        import inspect
        sig = inspect.signature(audio.clips_mid_word)
        self.assertLessEqual(sig.parameters["window"].default, 0.08)


class TestEndMargin(unittest.TestCase):
    """The clip end needs slack so it does not catch the next word.

    The times come from the transcript, whose resolution is 1 second — cutting
    exactly at a block boundary touches the attack of the next word. One clip
    ended at 901.0 and let the "Few" that opens the next block leak (the
    pause between the two words lasts ~50ms).
    """

    def test_pulls_the_end_back_by_the_margin(self):
        """A clip with slack above the minimum backs off the whole margin."""
        self.assertAlmostEqual(render.apply_end_margin(901.0, 830.0),
                               901.0 - render.END_MARGIN_S)

    def test_margin_does_not_invert_the_clip(self):
        """A clip too short for the margin keeps at least the start."""
        end = render.apply_end_margin(10.05, 10.0)
        self.assertGreater(end, 10.0)

    def test_margin_is_small(self):
        """A large margin would cut the last syllable of the usable speech."""
        self.assertLessEqual(render.END_MARGIN_S, 0.15)


class TestSegmentsInCut(unittest.TestCase):
    """The displayed text cannot go past what the clip audio reaches.

    The times were already trimmed by the clip (min/max), but the TEXT went
    whole into the PNG: a segment trimmed to 1.4s still showed the original
    block's 150 letters. The clip closed on "able to reproduce it" while
    the screen went on showing "I think that is a a first point..." — a
    sentence the viewer never hears.
    """

    def setUp(self):
        self.segs = [
            {"start": 0.0, "end": 10.0, "text": "First whole stretch of speech.",
             "turn": False},
            {"start": 10.0, "end": 20.0,
             "text": "You will not be able to reproduce it. I think that is "
                     "a first point.",
             "turn": False},
            {"start": 20.0, "end": 30.0, "text": "After the clip.", "turn": False},
        ]

    def test_segment_outside_the_clip_does_not_enter(self):
        items = render._segments_in_cut(self.segs, 0.0, 20.0)
        self.assertEqual(len(items), 2)
        self.assertNotIn("After the clip", " ".join(t for _, _, t in items))

    def test_times_are_relative_to_the_clip_start(self):
        items = render._segments_in_cut(self.segs, 10.0, 30.0)
        self.assertEqual(items[0][0], 0.0)

    def test_text_trimmed_when_the_clip_ends_mid_block(self):
        """A clip at 15.0 takes half of block 10-20: the text has to shrink."""
        items = render._segments_in_cut(self.segs, 0.0, 15.0)
        last = items[-1][2]
        self.assertIn("You will not be able to reproduce it.", last)
        self.assertNotIn("first point", last)

    def test_whole_text_when_the_segment_fits_the_clip(self):
        items = render._segments_in_cut(self.segs, 0.0, 20.0)
        self.assertIn("first point", items[-1][2])

    def test_ignores_a_slice_too_short_to_read(self):
        """Leftover milliseconds at the end must not become a blinking caption.

        The clip ends a few ms after the next block starts (the end comes from
        the audio valley, not the transcript grid). Without a duration floor
        that block becomes a 1-frame PNG — the clip displayed "Few" for
        20ms, exactly the word the audio adjustment removed.
        """
        segs = [
            {"start": 0.0, "end": 60.0, "text": "The speech we keep.",
             "turn": False},
            {"start": 60.0, "end": 70.0, "text": "Few people are doing it.",
             "turn": False},
        ]
        items = render._segments_in_cut(segs, 0.0, 60.02)
        self.assertEqual(len(items), 1, items)
        self.assertNotIn("Few", " ".join(t for _, _, t in items))

    def test_keeps_a_short_but_readable_slice(self):
        """The floor must not swallow a legitimately short caption."""
        segs = [
            {"start": 0.0, "end": 60.0, "text": "The speech we keep.",
             "turn": False},
            {"start": 60.0, "end": 70.0, "text": "Yes.", "turn": False},
        ]
        items = render._segments_in_cut(segs, 0.0, 61.0)
        self.assertEqual(len(items), 2, items)

    def test_text_trimmed_at_the_clip_start(self):
        """A clip starting mid-block does not show what has already passed."""
        items = render._segments_in_cut(self.segs, 15.0, 30.0)
        first = items[0][2]
        self.assertNotIn("You will not be able to reproduce it.", first)

    def test_trim_extends_to_nearby_punctuation(self):
        """A slice stopping 1-2 words before the full stop should reach it.

        Truncating before it leaves the caption hanging ("more of the") when
        the audio completed the sentence ("more of the same."). Real case.
        """
        txt = "more of the same. now capsule, then tablet."
        self.assertEqual(render._trim_text(txt, 0.0, 0.25), "more of the same.")

    def test_trim_does_not_extend_across_a_whole_sentence(self):
        """The extension is local: it cannot drag in the whole next sentence."""
        txt = "first. " + " ".join(f"p{i}" for i in range(20)) + " end."
        out = render._trim_text(txt, 0.0, 0.2)
        self.assertNotIn("end.", out)

    def test_trim_respects_the_word_boundary(self):
        """Trimmed text never ends on a half word."""
        items = render._segments_in_cut(self.segs, 0.0, 13.0)
        last = items[-1][2]
        self.assertFalse(last.endswith("re"), last)
        for word in last.split():
            self.assertIn(word.strip(".,!?"),
                          self.segs[1]["text"].replace(".", " ").split())


class TestWrapByPixels(unittest.TestCase):
    """wrap_by_pixels serves the burned-in caption AND the quote post."""

    DESIGN_QUOTE = ("Everybody told us we had to move to a bigger city. We "
                         "stayed, and that turned out to be the edge.")

    def test_wrap_accepts_an_alternative_font_and_width(self):
        """The wrap serves caption and post, with different font and width.

        Measures properties that hold for ANY font: no line exceeds the width,
        and no word disappears or changes order. The check against the reference
        wrap is in the next test, which demands the right font.
        """
        from PIL import ImageFont
        from talaria import config, render
        fnt = ImageFont.truetype(config.POST_FONT, config.POST_QUOTE_SIZE)
        lines = render.wrap_by_pixels(self.DESIGN_QUOTE, fnt=fnt,
                                       width=config.POST_TEXT_W)
        self.assertGreater(len(lines), 1)
        for line in lines:
            # A single word wider than the width is a known exception: it goes
            # onto the line anyway, because there is nowhere to break.
            if len(line.split()) > 1:
                self.assertLessEqual(fnt.getlength(line),
                                     config.POST_TEXT_W)
        self.assertEqual(" ".join(lines), self.DESIGN_QUOTE)

    def test_design_wrap_with_the_design_font(self):
        """The reference quote wraps to 5 lines in the versioned font.

        There is no candidate chain any more: the font comes from assets/fonts/,
        so the wrap is the same on any machine and the test demands the layout
        instead of skipping.
        """
        from PIL import ImageFont
        from talaria import config, render
        fnt = ImageFont.truetype(config.POST_FONT, config.POST_QUOTE_SIZE)
        self.assertEqual(fnt.getname(), ("Poppins", "SemiBold"))
        lines = render.wrap_by_pixels(self.DESIGN_QUOTE, fnt=fnt,
                                       width=config.POST_TEXT_W)
        self.assertEqual(lines, ["Everybody told us we",
                                  "had to move to a",
                                  "bigger city. We stayed,",
                                  "and that turned out to",
                                  "be the edge."])

    def test_wrap_with_no_arguments_keeps_the_caption_behaviour(self):
        from talaria import render
        lines = render.wrap_by_pixels("word " * 30)
        self.assertGreater(len(lines), 1)


if __name__ == "__main__":
    unittest.main()


class TestSuggestFrames(unittest.TestCase):
    """Where to look for a thumbnail frame: inside the approved clips.

    The final choice is visual and stays with the manager — the region is what
    gets automated. The suggestion landed at 1619s; the hand pick was 1620s.
    """

    def setUp(self):
        from talaria import thumbnail
        self.thumbnail = thumbnail
        self.moments = [{"start": s, "end": s + 60.0}
                         for s in (100.0, 500.0, 900.0, 1300.0, 1700.0, 2100.0)]

    def test_suggests_inside_the_clips(self):
        for t in self.thumbnail.suggest_frames(self.moments):
            self.assertTrue(any(m["start"] <= t <= m["end"] for m in self.moments),
                            f"{t} outside every clip")

    def test_respects_the_requested_limit(self):
        self.assertLessEqual(len(self.thumbnail.suggest_frames(self.moments, n=3)), 3)

    def test_fewer_clips_than_the_limit(self):
        r = self.thumbnail.suggest_frames(self.moments[:2], n=5)
        self.assertEqual(len(r), 2)

    def test_no_moments(self):
        self.assertEqual(self.thumbnail.suggest_frames([]), [])


class TestClipCaption(unittest.TestCase):
    """The publishing .txt written beside each rendered piece."""

    def setUp(self):
        self.d = tempfile.mkdtemp()

    def _texts(self, data):
        p = layout.ensure_dir(layout.texts(self.d))
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def _episode(self, url):
        p = layout.ensure_dir(layout.episode(self.d))
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"youtube_url": url}, f)

    def test_writes_a_txt_for_each_platform(self):
        # Every rendered piece gets a sibling .txt.
        self._texts({"hashtags": "#One #Two"})
        pieces = [os.path.join(self.d, "youtube_shorts", "c1_short.mp4"),
                 os.path.join(self.d, "instagram_reels", "c1_reel.mp4")]
        render.write_captions(self.d, {"slug": "c1",
                                         "post_caption": "The sentence."}, pieces)
        for p in pieces:
            txt = p[:-4] + ".txt"
            self.assertTrue(os.path.exists(txt), txt)
            with open(txt, encoding="utf-8") as f:
                self.assertEqual(f.read(), "The sentence.\n\n#One #Two")

    def test_missing_post_caption_warns_and_writes_hashtags(self):
        # An absence must not pass silently.
        self._texts({"hashtags": "#One"})
        piece = os.path.join(self.d, "youtube_shorts", "c5_short.mp4")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            render.write_captions(self.d, {"slug": "c5"}, [piece])
        self.assertIn("c5", buf.getvalue())
        self.assertIn("no post_caption", buf.getvalue())
        with open(piece[:-4] + ".txt", encoding="utf-8") as f:
            self.assertEqual(f.read(), "#One")

    def test_with_a_post_caption_it_does_not_warn(self):
        self._texts({"hashtags": "#One"})
        self._episode("https://youtu.be/XYZ")
        piece = os.path.join(self.d, "youtube_shorts", "c1_short.mp4")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            render.write_captions(self.d, {"slug": "c1",
                                             "post_caption": "The sentence."}, [piece])
        self.assertEqual(buf.getvalue(), "")

    def test_without_texts_json_it_does_not_break(self):
        # An episode with no texts.json still yields a caption.
        piece = os.path.join(self.d, "youtube_shorts", "c1_short.mp4")
        render.write_captions(self.d, {"slug": "c1",
                                         "post_caption": "The sentence."}, [piece])
        with open(piece[:-4] + ".txt", encoding="utf-8") as f:
            self.assertEqual(f.read(), "The sentence.")


    def test_episode_link_only_on_youtube(self):
        # The episode URL goes into the Short description and NOT the Reels
        # caption: on Instagram it is not clickable and sends the reader away.
        self._texts({"hashtags": "#One"})
        self._episode("https://youtu.be/XYZ")
        yt = os.path.join(self.d, "youtube_shorts", "c1_short.mp4")
        ig = os.path.join(self.d, "instagram_reels", "c1_reel.mp4")
        render.write_captions(self.d, {"slug": "c1",
                                         "post_caption": "The sentence."}, [yt, ig])
        with open(yt[:-4] + ".txt", encoding="utf-8") as f:
            self.assertEqual(
                f.read(),
                "The sentence.\n\n▶ Full episode: https://youtu.be/XYZ\n\n#One")
        with open(ig[:-4] + ".txt", encoding="utf-8") as f:
            self.assertEqual(f.read(), "The sentence.\n\n#One")

    def test_missing_youtube_url_warns_and_writes_without_the_link(self):
        # A clip rendered before the long video goes up is the normal case —
        # it must not break, but must not pass silently either: the Short would
        # go live without the call, only noticed after it is published.
        self._texts({"hashtags": "#One"})
        piece = os.path.join(self.d, "youtube_shorts", "c1_short.mp4")
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            render.write_captions(self.d, {"slug": "c1",
                                             "post_caption": "The sentence."},
                                    [piece])
        self.assertIn("youtube_url", buf.getvalue())
        with open(piece[:-4] + ".txt", encoding="utf-8") as f:
            self.assertEqual(f.read(), "The sentence.\n\n#One")

    def test_invalid_episode_json_does_not_break_the_caption(self):
        # An incomplete episode.json aborts in `load`, which validates the
        # whole episode. The caption reads only the optional URL, and goes on.
        self._texts({"hashtags": "#One"})
        with open(layout.ensure_dir(layout.episode(self.d)), "w",
                  encoding="utf-8") as f:
            f.write("{ not json")
        piece = os.path.join(self.d, "youtube_shorts", "c1_short.mp4")
        with contextlib.redirect_stdout(io.StringIO()):
            render.write_captions(self.d, {"slug": "c1",
                                             "post_caption": "The sentence."},
                                    [piece])
        with open(piece[:-4] + ".txt", encoding="utf-8") as f:
            self.assertEqual(f.read(), "The sentence.\n\n#One")


class TestEpisodeCaption(unittest.TestCase):
    """The .txt with the episode title and description, at the publish/ root."""

    def setUp(self):
        self.d = tempfile.mkdtemp()

    def _texts(self, data):
        p = layout.ensure_dir(layout.texts(self.d))
        with open(p, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def _episode(self, url):
        p = layout.ensure_dir(layout.episode(self.d))
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"youtube_url": url}, f)

    def test_writes_title_description_and_hashtags(self):
        self._texts({"title": "The Title", "description": "The description.",
                      "hashtags": "#One"})
        out = render.write_episode_caption(self.d)
        self.assertEqual(out, layout.episode_txt(self.d))
        with open(out, encoding="utf-8") as f:
            self.assertEqual(f.read(), "The Title\n\nThe description.\n\n#One")

    def test_without_texts_json_it_neither_writes_nor_breaks(self):
        # An episode before the materials step: nothing to paste yet.
        self.assertIsNone(render.write_episode_caption(self.d))
        self.assertFalse(os.path.exists(layout.episode_txt(self.d)))

    def test_empty_texts_json_produces_no_file(self):
        self._texts({})
        self.assertIsNone(render.write_episode_caption(self.d))
        self.assertFalse(os.path.exists(layout.episode_txt(self.d)))


class TestWatermarkGraph(unittest.TestCase):
    """The watermark overlay, chained after [outv]."""

    def test_chains_after_outv_and_produces_outv2(self):
        fg = render._watermark_graph("outv", "logoinput")
        self.assertIn("[outv]", fg)
        self.assertIn("[logoinput]", fg)
        self.assertTrue(fg.strip().endswith("[outv2]"))

    def test_uses_the_margin_and_width_from_config(self):
        fg = render._watermark_graph("outv", "3")
        self.assertIn(f"scale={config.WATERMARK_W}", fg)
        self.assertIn(f"W-w-{config.WATERMARK_MARGIN}", fg)
        self.assertIn(f"{config.WATERMARK_MARGIN}[outv2]", fg)


def _has_ffmpeg():
    return shutil.which("ffmpeg") is not None


class TestWatermarkAndCardIntegration(unittest.TestCase):
    """Real render, with real ffmpeg: confirms the command runs and produces a
    file carrying watermark + card, not merely that the filtergraph string
    looks right.
    """

    def setUp(self):
        self.d = tempfile.mkdtemp()

    @unittest.skipUnless(_has_ffmpeg(), "ffmpeg not available")
    def test_clip_comes_out_with_watermark_and_card(self):
        video = layout.ensure_dir(layout.video(self.d))
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=s=640x360:d=8:r=25",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=8",
            "-c:v", "libx264", "-crf", "30", "-c:a", "aac", "-shortest", video,
        ], check=True)

        segs = [{"start": 0.5, "end": 4.0, "text": "Test caption.", "turn": False},
                {"start": 4.0, "end": 7.5, "text": "Second caption.", "turn": True}]
        with open(layout.ensure_dir(layout.transcript(self.d)), "w", encoding="utf-8") as f:
            json.dump({"segments": segs}, f)
        moment = {"slug": "c1", "start": 0.0, "end": 8.0}
        with open(layout.ensure_dir(layout.moments(self.d)), "w", encoding="utf-8") as f:
            json.dump([moment], f)

        render.render_all(self.d, ["youtube"])

        out = os.path.join(layout.platform(self.d, "youtube_shorts"), "c1_short.mp4")
        self.assertTrue(os.path.exists(out))

        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", out], capture_output=True, text=True, check=True)
        duration = float(r.stdout.strip())
        # The clip's own duration varies with the audio adjustment
        # (adjust_end_by_audio); the card adds CARD_DURATION_S on top.
        self.assertGreater(duration, config.CARD_DURATION_S)

        # The cached card must exist at the publish/ root (not inside a
        # platform folder) and be reused, not made once per clip.
        card = layout.end_card_mp4(self.d)
        self.assertTrue(os.path.exists(card))


class TestConcatenateEndCard(unittest.TestCase):
    """Concatenating clip + card through the concat filter."""

    def setUp(self):
        self.d = tempfile.mkdtemp()

    @unittest.skipUnless(_has_ffmpeg(), "ffmpeg not available")
    def test_final_duration_is_clip_plus_card(self):
        clip = os.path.join(self.d, "clip.mp4")
        subprocess.run([
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=red:s=1080x1920:d=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", config.VCODEC, "-preset", config.PRESET, "-crf", config.CRF,
            "-pix_fmt", config.PIX_FMT, "-c:a", config.ACODEC,
            "-shortest", clip,
        ], check=True)

        render.append_end_card(clip, self.d)

        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", clip], capture_output=True, text=True, check=True)
        self.assertAlmostEqual(float(r.stdout.strip()),
                               2.0 + config.CARD_DURATION_S, delta=0.3)

    @unittest.skipUnless(_has_ffmpeg(), "ffmpeg not available")
    def test_is_in_place_on_the_same_path(self):
        clip = os.path.join(self.d, "clip.mp4")
        subprocess.run([
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=blue:s=1080x1920:d=1",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-c:v", config.VCODEC, "-preset", config.PRESET, "-crf", config.CRF,
            "-pix_fmt", config.PIX_FMT, "-c:a", config.ACODEC,
            "-shortest", clip,
        ], check=True)

        before = os.path.getsize(clip)
        render.append_end_card(clip, self.d)
        self.assertTrue(os.path.exists(clip))
        self.assertGreater(os.path.getsize(clip), before)

    @unittest.skipUnless(_has_ffmpeg(), "ffmpeg not available")
    def test_path_with_an_apostrophe_does_not_break(self):
        # A hand-typed project slug can contain an apostrophe.
        subdir = os.path.join(self.d, "proj's episode")
        os.makedirs(subdir, exist_ok=True)
        clip = os.path.join(subdir, "clip.mp4")
        subprocess.run([
            "ffmpeg", "-y", "-v", "error",
            "-f", "lavfi", "-i", "color=c=green:s=1080x1920:d=1",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
            "-c:v", config.VCODEC, "-preset", config.PRESET, "-crf", config.CRF,
            "-pix_fmt", config.PIX_FMT, "-c:a", config.ACODEC,
            "-shortest", clip,
        ], check=True)
        render.append_end_card(clip, subdir)
        self.assertTrue(os.path.exists(clip))


class TestClipsMidWordOrderBeforeCard(unittest.TestCase):
    """clips_mid_word has to measure the clip BEFORE the card is concatenated.

    Real risk: if the check runs on the file with the card already glued on, the
    measured instant (end-start) falls near where the SILENT card begins. The
    reading window has slack (180ms) around that point — depending on frame
    rounding it can capture card silence instead of speech, masking a genuine
    mid-word clip. Rather than depend on an audio threshold (fragile, sensitive
    to codec/timing), the test pins the CONTRACT: clips_mid_word must be called
    with a file that does NOT have the card duration added — that is, before
    concatenation.
    """

    def setUp(self):
        self.d = tempfile.mkdtemp()

    @unittest.skipUnless(_has_ffmpeg(), "ffmpeg not available")
    def test_mid_word_check_runs_before_concatenation(self):
        video = layout.ensure_dir(layout.video(self.d))
        subprocess.run([
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
            "-f", "lavfi", "-i", "testsrc2=s=640x360:d=5:r=25",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=5",
            "-c:v", "libx264", "-crf", "30", "-c:a", "aac", "-shortest", video,
        ], check=True)
        with open(layout.ensure_dir(layout.transcript(self.d)), "w", encoding="utf-8") as f:
            json.dump({"segments": []}, f)
        with open(layout.ensure_dir(layout.moments(self.d)), "w", encoding="utf-8") as f:
            json.dump([{"slug": "c1", "start": 0.0, "end": 5.0}], f)

        durations_seen = []
        original = audio.clips_mid_word

        def spy(video_path, end, *a, **kw):
            r = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", video_path],
                capture_output=True, text=True, check=True)
            durations_seen.append(float(r.stdout.strip()))
            return original(video_path, end, *a, **kw)

        import unittest.mock as mock
        with mock.patch("talaria.render.audio.clips_mid_word", side_effect=spy):
            render.render_all(self.d, ["youtube"])

        self.assertEqual(len(durations_seen), 1)
        # The file the check sees must not already carry the card's +3.5s —
        # otherwise it is measuring the wrong instant.
        self.assertLess(durations_seen[0], 5.0 + config.CARD_DURATION_S,
                        "clips_mid_word got the file already concatenated with the "
                        "card — the check has to run BEFORE the concat")

        out = os.path.join(layout.platform(self.d, "youtube_shorts"), "c1_short.mp4")
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", out], capture_output=True, text=True, check=True)
        self.assertGreater(float(r.stdout.strip()), config.CARD_DURATION_S + 3.0)
