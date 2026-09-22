"""Tests for the iterative curation state."""
import unittest

from talaria import curation


class TestOverlap(unittest.TestCase):
    def test_full_overlap(self):
        self.assertTrue(curation.overlaps((10, 70), (10, 70)))

    def test_no_overlap(self):
        self.assertFalse(curation.overlaps((10, 70), (100, 160)))

    def test_touching_is_not_overlap(self):
        self.assertFalse(curation.overlaps((10, 70), (70, 130)))

    def test_small_overlap_below_the_threshold(self):
        # 5s of 60s = 8% — below the 30% threshold, does not count
        self.assertFalse(curation.overlaps((10, 70), (65, 125)))

    def test_large_overlap_above_the_threshold(self):
        # clip 10s past the rejected one — the same stretch in disguise
        self.assertTrue(curation.overlaps((10, 70), (20, 80)))


class TestBurned(unittest.TestCase):
    def setUp(self):
        self.state = {
            "target": 5,
            "approved": [{"slug": "a", "start": 100.0, "end": 170.0}],
            "rejected": [{"start": 300.0, "end": 370.0, "reason": "weak hook"}],
            "rounds": 1,
        }

    def test_spans_include_approved_and_rejected(self):
        spans = curation.burned_spans(self.state)
        self.assertIn((100.0, 170.0), spans)
        self.assertIn((300.0, 370.0), spans)

    def test_proposal_over_a_rejection_is_burned(self):
        self.assertTrue(curation.is_burned((310.0, 380.0), self.state))

    def test_free_proposal_is_not_burned(self):
        self.assertFalse(curation.is_burned((500.0, 570.0), self.state))

    def test_slots_left(self):
        self.assertEqual(curation.slots_left(self.state), 4)

    def test_slots_never_negative(self):
        e = dict(self.state, approved=[{"slug": str(i)} for i in range(7)])
        self.assertEqual(curation.slots_left(e), 0)


class TestInitialState(unittest.TestCase):
    def test_new_state_has_a_target(self):
        e = curation.new_state(target=5)
        self.assertEqual(e["target"], 5)
        self.assertEqual(e["approved"], [])
        self.assertEqual(e["rejected"], [])
        self.assertEqual(e["rounds"], 0)


class TestValidations(unittest.TestCase):
    def setUp(self):
        self.segs = [
            {"start": 0.0, "end": 30.0, "text": "Host question?", "turn": False},
            {"start": 30.0, "end": 95.0, "text": "Long answer from the guest.",
             "turn": True},
            {"start": 95.0, "end": 120.0, "text": "The response continues.",
             "turn": False},
        ]

    def test_duration_within_range(self):
        ok, msgs = curation.validate_clip((0.0, 75.0), self.segs, {})
        self.assertTrue(ok, msgs)

    def test_duration_too_short(self):
        ok, msgs = curation.validate_clip((0.0, 30.0), self.segs, {})
        self.assertFalse(ok)
        # The branch, not just the word "duration": both duration messages
        # carry it, so pinning the word alone cannot tell them apart.
        self.assertTrue(any("below the minimum" in m for m in msgs), msgs)

    def test_duration_too_long(self):
        ok, msgs = curation.validate_clip((0.0, 120.0), self.segs, {})
        self.assertFalse(ok)
        self.assertTrue(any("above the maximum" in m for m in msgs), msgs)

    def test_boundary_outside_a_segment(self):
        ok, msgs = curation.validate_clip((12.0, 87.0), self.segs, {})
        self.assertFalse(ok)
        self.assertTrue(any("sentence boundary" in m for m in msgs), msgs)

    def test_clip_over_a_burned_span(self):
        state = {"target": 5, "approved": [], "rounds": 0,
                  "rejected": [{"start": 0.0, "end": 75.0}]}
        ok, msgs = curation.validate_clip((0.0, 75.0), self.segs, state)
        self.assertFalse(ok)
        self.assertTrue(any("burned span" in m for m in msgs), msgs)


class TestEndAtCompleteSentence(unittest.TestCase):
    """The clip end has to close a sentence, not just match a block end.

    The YouTube transcript breaks blocks by TIME, not by punctuation: a block
    can end mid-sentence. Checking only the block boundary let through a clip
    ending on a stray word — which is what happened (block 1655-1663 closes at
    "...technology transfer and the", a sentence that only ends in the
    next block).
    """

    def setUp(self):
        self.segs = [
            {"start": 0.0, "end": 30.0, "text": "Opening of the conversation.",
             "turn": False},
            # ends on a complete sentence
            {"start": 30.0, "end": 95.0,
             "text": "You will not be able to reproduce it.", "turn": True},
            # does NOT end a sentence: runs on into the next block
            {"start": 95.0, "end": 160.0,
             "text": "I think that is a first point which", "turn": False},
            {"start": 160.0, "end": 200.0, "text": "mattered to us.",
             "turn": False},
        ]

    def test_end_on_a_complete_sentence_passes(self):
        ok, msgs = curation.validate_clip((30.0, 95.0), self.segs, {})
        self.assertTrue(ok, msgs)

    def test_end_mid_sentence_fails(self):
        """Block 95-160 ends with no closing punctuation: the clip is half done."""
        ok, msgs = curation.validate_clip((95.0, 160.0), self.segs, {})
        self.assertFalse(ok)
        self.assertTrue(any("does not close a sentence" in m for m in msgs), msgs)

    def test_end_with_an_ellipsis_is_accepted(self):
        segs = [{"start": 0.0, "end": 65.0, "text": "And then we stopped...",
                 "turn": False}]
        ok, msgs = curation.validate_clip((0.0, 65.0), segs, {})
        self.assertTrue(ok, msgs)

    def test_end_with_a_question_mark_is_accepted(self):
        segs = [{"start": 0.0, "end": 65.0, "text": "How do we do that?",
                 "turn": False}]
        ok, msgs = curation.validate_clip((0.0, 65.0), segs, {})
        self.assertTrue(ok, msgs)


class TestSentenceEnds(unittest.TestCase):
    """Candidates for a clip end, so the point is not picked by hand."""

    def setUp(self):
        self.segs = [
            {"start": 0.0, "end": 30.0, "text": "Opening of the conversation.",
             "turn": False},
            {"start": 30.0, "end": 70.0,
             "text": "The first idea closes here. And the second closes here too.",
             "turn": False},
            {"start": 70.0, "end": 100.0, "text": "Well past the limit.",
             "turn": False},
        ]

    def test_returns_only_valid_durations(self):
        for _inst, dur, _ctx in curation.sentence_ends(self.segs, 0.0, 30.0, 100.0):
            self.assertGreaterEqual(dur, 60.0)
            self.assertLessEqual(dur, 90.0)

    def test_ordered_by_instant(self):
        r = curation.sentence_ends(self.segs, 0.0, 30.0, 100.0)
        self.assertEqual([x[0] for x in r], sorted(x[0] for x in r))

    def test_brings_the_stretch_context(self):
        r = curation.sentence_ends(self.segs, 0.0, 30.0, 100.0)
        self.assertTrue(all(isinstance(x[2], str) and x[2] for x in r), r)

    def test_no_candidate_outside_the_window(self):
        self.assertEqual(curation.sentence_ends(self.segs, 0.0, 95.0, 100.0), [])


class TestOverlapBetweenApproved(unittest.TestCase):
    """Two approved clips on the same stretch compete in distribution.

    `validate_clip` already blocked it, but a direct `approve()` call escaped —
    two clips shared 74s because of that.
    """

    def setUp(self):
        self.state = curation.new_state(target=5)
        curation.approve(self.state, {"slug": "a", "start": 100.0, "end": 170.0})

    def test_refuses_an_overlapping_clip(self):
        with self.assertRaises(ValueError) as cm:
            curation.approve(self.state, {"slug": "b", "start": 150.0, "end": 220.0})
        # The approve-time wording, not the bare verb: validate_clip's
        # burned-span message also says "overlaps".
        self.assertIn("overlaps approved clip", str(cm.exception))

    def test_accepts_a_disjoint_clip(self):
        curation.approve(self.state, {"slug": "b", "start": 200.0, "end": 270.0})
        self.assertEqual(len(self.state["approved"]), 2)

    def test_time_adjustment_may_touch_another(self):
        """Adjusting a clip must not be blocked by a distant neighbour.

        The overlap check has to ignore the clip being replaced — otherwise
        moving an already-approved clip by 5s becomes an error.
        """
        curation.approve(self.state, {"slug": "b", "start": 200.0, "end": 270.0})
        curation.approve(self.state, {"slug": "b", "start": 205.0, "end": 275.0})
        self.assertEqual(len(self.state["approved"]), 2)
        self.assertEqual(self.state["approved"][1]["start"], 205.0)

    def test_adjustment_cannot_invade_another_clip(self):
        """But moving a clip ON TOP of another is still an error."""
        curation.approve(self.state, {"slug": "b", "start": 200.0, "end": 270.0})
        with self.assertRaises(ValueError):
            curation.approve(self.state, {"slug": "b", "start": 120.0, "end": 190.0})

    def test_same_slug_is_a_time_adjustment(self):
        """Re-approving the same clip at another time replaces, not duplicates."""
        curation.approve(self.state, {"slug": "a", "start": 105.0, "end": 175.0})
        self.assertEqual(len(self.state["approved"]), 1)
        self.assertEqual(self.state["approved"][0]["start"], 105.0)


class TestAttributionTrustworthy(unittest.TestCase):
    """A lying alert trains the operator to ignore the output."""

    def test_well_attributed_episode(self):
        segs = [
            {"start": 0.0, "end": 30.0, "speaker": "host",
             "text": "How did the company get started?"},
            {"start": 30.0, "end": 90.0, "speaker": "guest",
             "text": "We built our first product in a garage."},
        ]
        self.assertTrue(curation.attribution_trustworthy(segs))

    def test_host_talking_about_own_company_is_suspect(self):
        segs = [
            {"start": 0.0, "end": 60.0, "speaker": "host",
             "text": "We set up our own studio, our own lab."},
            {"start": 60.0, "end": 70.0, "speaker": "host", "text": "Right."},
        ]
        self.assertFalse(curation.attribution_trustworthy(segs))

    def test_first_person_plural_is_detected(self):
        for txt in ("we built it here", "our first hire", "my co-founder left"):
            self.assertTrue(bool(curation.RE_FIRST_PERSON.search(txt)), txt)

    def test_third_person_is_not_detected(self):
        self.assertFalse(bool(curation.RE_FIRST_PERSON.search(
            "the company hired three people")))

    def test_suppresses_warnings_that_read_speaker(self):
        segs = [
            {"start": 0.0, "end": 65.0, "speaker": "host",
             "text": "We set up our own studio, our own lab."},
        ]
        alerts = curation.clip_warnings((0.0, 65.0), segs)
        self.assertFalse(any("guest speaks only" in a for a in alerts), alerts)
        self.assertFalse(any("opens with" in a for a in alerts), alerts)


class TestHostOpening(unittest.TestCase):
    """A clip opening with a long question loses the cold viewer."""

    def setUp(self):
        self.segs = [
            {"start": 0.0, "end": 40.0, "text": "Long question from the host?",
             "turn": False, "speaker": "host"},
            {"start": 40.0, "end": 110.0, "text": "Answer from the guest.",
             "turn": True, "speaker": "guest"},
        ]

    def test_alerts_when_the_host_opens_too_long(self):
        alerts = curation.clip_warnings((0.0, 70.0), self.segs)
        self.assertTrue(any("host" in a for a in alerts), alerts)

    def test_no_alert_when_it_opens_on_the_guest(self):
        alerts = curation.clip_warnings((40.0, 105.0), self.segs)
        self.assertFalse(any("opens with" in a for a in alerts), alerts)

    def test_no_speaker_does_not_alert(self):
        """An origin with no turn marker: do not accuse in the dark."""
        segs = [{"start": 0.0, "end": 70.0, "text": "Some speech.", "turn": False}]
        self.assertEqual(curation.host_opening((0.0, 65.0), segs), 0.0)


class TestHedgedNumber(unittest.TestCase):
    def test_detects_approximate_figure(self):
        for txt in ("about 2005", "roughly 570 users", "I think 12 people"):
            self.assertTrue(curation.has_hedged_number(txt), txt)

    def test_exact_figure_does_not_warn(self):
        self.assertFalse(curation.has_hedged_number("founded in 2006"))

    def test_marker_without_a_number_does_not_warn(self):
        self.assertFalse(curation.has_hedged_number("I think this matters"))
        # Same marker, now with a digit: without this the assertion above
        # would also pass on a marker the pattern no longer recognises.
        self.assertTrue(curation.has_hedged_number("I think this matters, 12"))


class TestProminence(unittest.TestCase):
    """Guest prominence.

    Speech attribution is ABSOLUTE: it comes from the `speaker` field, resolved
    globally at parse time over the whole episode. It is not deduced from '>>'
    inside the clip slice, because '>>' marks THAT it changed, not WHO speaks.
    """

    def test_guest_dominates(self):
        segs = [
            {"start": 0.0, "end": 10.0, "text": "A question?", "turn": False,
             "speaker": "host"},
            {"start": 10.0, "end": 90.0, "text": "A long answer.", "turn": True,
             "speaker": "guest"},
        ]
        frac = curation.guest_speech_fraction((0.0, 90.0), segs)
        self.assertGreater(frac, 0.8)

    def test_host_dominates(self):
        segs = [
            {"start": 0.0, "end": 80.0, "text": "Long host speech.", "turn": False,
             "speaker": "host"},
            {"start": 80.0, "end": 90.0, "text": "Yes.", "turn": True,
             "speaker": "guest"},
        ]
        frac = curation.guest_speech_fraction((0.0, 90.0), segs)
        self.assertLess(frac, 0.3)

    def test_no_segments_returns_zero(self):
        self.assertEqual(curation.guest_speech_fraction((0.0, 90.0), []), 0.0)

    def test_clip_mid_answer_with_no_turn_inside(self):
        """Bug regression: a 100%-guest clip that reported 0.0.

        No segment of the slice has turn=True — the change happened earlier, in
        the episode. The fraction has to be high.
        """
        segs = [
            {"start": 0.0, "end": 20.0, "text": "Host question?", "turn": False,
             "speaker": "host"},
            {"start": 20.0, "end": 60.0, "text": "Start of the response.",
             "turn": True, "speaker": "guest"},
            {"start": 60.0, "end": 110.0, "text": "Middle of the response.",
             "turn": False, "speaker": "guest"},
            {"start": 110.0, "end": 160.0, "text": "End of the response.",
             "turn": False, "speaker": "guest"},
        ]
        frac = curation.guest_speech_fraction((60.0, 150.0), segs)
        self.assertEqual(frac, 1.0)

    def test_clip_mostly_host(self):
        segs = [
            {"start": 0.0, "end": 70.0, "text": "Long host context.",
             "turn": False, "speaker": "host"},
            {"start": 70.0, "end": 90.0, "text": "Start of the response.",
             "turn": True, "speaker": "guest"},
        ]
        frac = curation.guest_speech_fraction((0.0, 90.0), segs)
        self.assertLess(frac, curation.config.GUEST_SPEECH_MIN)

    def test_absent_speaker_does_not_fire_a_false_alert(self):
        """Without `speaker` (vtt/Whisper, or data older than the fix)
        prominence cannot be measured. Returns 1.0 — turns the alert off rather
        than falsely accusing a clip that may be 100% guest."""
        segs = [
            {"start": 0.0, "end": 45.0, "text": "Some speech.", "turn": False},
            {"start": 45.0, "end": 90.0, "text": "Other speech.", "turn": False},
        ]
        self.assertEqual(curation.guest_speech_fraction((0.0, 90.0), segs), 1.0)

    def test_absent_speaker_produces_no_prominence_alert(self):
        segs = [
            {"start": 0.0, "end": 90.0, "text": "Some speech.", "turn": False},
        ]
        alerts = curation.clip_warnings((0.0, 90.0), segs)
        self.assertFalse([a for a in alerts if "guest speaks" in a], alerts)

    def test_partial_speaker_uses_only_what_is_labelled(self):
        """Mix of segments with and without `speaker`: measures the labelled."""
        segs = [
            {"start": 0.0, "end": 30.0, "text": "Host.", "turn": False,
             "speaker": "host"},
            {"start": 30.0, "end": 60.0, "text": "Unlabelled.", "turn": False},
            {"start": 60.0, "end": 90.0, "text": "Guest.", "turn": False,
             "speaker": "guest"},
        ]
        frac = curation.guest_speech_fraction((0.0, 90.0), segs)
        self.assertAlmostEqual(frac, 0.5)


class TestOperations(unittest.TestCase):
    def setUp(self):
        self.state = curation.new_state(target=5)

    def test_approve_adds(self):
        curation.approve(self.state, {"slug": "c1", "start": 10.0, "end": 80.0})
        self.assertEqual(len(self.state["approved"]), 1)

    def test_reject_records_the_reason(self):
        curation.reject(self.state, {"start": 10.0, "end": 80.0,
                                         "summary": "stretch X"}, "weak hook")
        self.assertEqual(self.state["rejected"][0]["reason"], "weak hook")

    def test_approving_past_the_target_errors(self):
        for i in range(5):
            curation.approve(self.state, {"slug": f"c{i}", "start": i * 200.0,
                                            "end": i * 200.0 + 70.0})
        with self.assertRaises(ValueError):
            curation.approve(self.state, {"slug": "c6", "start": 2000.0, "end": 2070.0})

    def test_composition_by_kind(self):
        curation.approve(self.state, {"slug": "a", "start": 0.0, "end": 70.0,
                                        "kind": "story"})
        curation.approve(self.state, {"slug": "b", "start": 200.0, "end": 270.0,
                                        "kind": "story"})
        comp = curation.composition(self.state)
        self.assertEqual(comp["story"], 2)

    def test_missing_kinds(self):
        curation.approve(self.state, {"slug": "a", "start": 0.0, "end": 70.0,
                                        "kind": "story"})
        missing = curation.missing_kinds(self.state)
        self.assertIn("thesis", missing)
        self.assertNotIn("story", missing)

    def test_accumulated_reasons(self):
        curation.reject(self.state, {"start": 0.0, "end": 70.0}, "too technical")
        curation.reject(self.state, {"start": 200.0, "end": 270.0}, "too technical")
        self.assertEqual(curation.reasons(self.state), ["too technical"])

    def test_closed_when_the_target_is_met(self):
        self.assertFalse(curation.is_closed(self.state))
        for i in range(5):
            curation.approve(self.state, {"slug": f"c{i}", "start": i * 200.0,
                                            "end": i * 200.0 + 70.0})
        self.assertTrue(curation.is_closed(self.state))


class TestExport(unittest.TestCase):
    def test_exports_moments_with_the_render_fields(self):
        state = curation.new_state(target=2)
        curation.approve(state, {
            "slug": "clip1", "start": 10.0, "end": 80.0, "kind": "story",
            "screen_text": "the upside without the cost", "post_caption": "...",
        })
        moments = curation.to_moments(state)
        self.assertEqual(len(moments), 1)
        m = moments[0]
        self.assertEqual(m["slug"], "clip1")
        self.assertEqual(m["start"], 10.0)
        self.assertEqual(m["end"], 80.0)
        self.assertEqual(m["screen_text"], "the upside without the cost")

    def test_exporting_with_no_approvals_errors(self):
        state = curation.new_state(target=5)
        with self.assertRaises(ValueError):
            curation.to_moments(state)


if __name__ == "__main__":
    unittest.main()
