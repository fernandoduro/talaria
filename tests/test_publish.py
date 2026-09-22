"""Tests for the publishing orchestrator."""
import json
import os
import tempfile
import unittest
from unittest import mock

from talaria import layout, publish

ENV_OK = {"IG_PAGE_TOKEN": "t", "IG_BUSINESS_ACCOUNT_ID": "1",
          "S3_PUBLISH_BUCKET": "b", "YT_CLIENT_SECRET_PATH": "/x",
          "YT_REFRESH_TOKEN": "r"}


def _project(pd, title="Short title"):
    """A complete project: moments, posts, schedule and files in publish/."""
    moments = [{"slug": "clip1", "start": 1.0, "end": 70.0,
                 "title": title}]
    with open(layout.ensure_dir(layout.moments(pd)), "w", encoding="utf-8") as f:
        json.dump(moments, f)
    with open(layout.ensure_dir(layout.posts(pd)), "w", encoding="utf-8") as f:
        json.dump({"posts": [{"slug": "cit_x", "cards": ["a", "b"],
                              "caption": "cap"}]}, f)
    with open(layout.ensure_dir(layout.schedule(pd)), "w", encoding="utf-8") as f:
        json.dump({"schedule": [
            {"date": "2026-08-24", "kind": "clip", "slug": "clip1"},
            {"date": "2026-08-24", "kind": "post", "slug": "cit_x"},
        ]}, f)
    # rendered pieces + captions
    for folder, name in (("youtube_shorts", "clip1_short"),
                        ("instagram_reels", "clip1_reel")):
        base = os.path.join(layout.platform(pd, folder), name)
        layout.ensure_dir(base + ".mp4")
        open(base + ".mp4", "w").close()
        with open(base + ".txt", "w", encoding="utf-8") as f:
            f.write("Clip caption.\n\n#Tag")
    folder = layout.posts_png(pd)
    os.makedirs(folder, exist_ok=True)
    for n in ("post_cit_x_1.png", "post_cit_x_2.png"):
        open(os.path.join(folder, n), "w").close()
    with open(os.path.join(folder, "post_cit_x.txt"), "w",
              encoding="utf-8") as f:
        f.write("Post caption.\n\n#Tag")


class TestPrecheck(unittest.TestCase):
    def setUp(self):
        self.pd = tempfile.mkdtemp()
        _project(self.pd)

    @mock.patch.dict("os.environ", ENV_OK)
    def test_a_complete_project_passes(self):
        import datetime as dt
        from talaria import schedule
        pairs = schedule.pending(self.pd, day=dt.date(2026, 8, 24))
        self.assertEqual(publish.precheck(self.pd, pairs), [])

    @mock.patch.dict("os.environ", ENV_OK)
    def test_missing_mp4_points_at_render(self):
        import datetime as dt
        from talaria import schedule
        os.remove(os.path.join(layout.platform(self.pd, "youtube_shorts"),
                               "clip1_short.mp4"))
        pairs = schedule.pending(self.pd, day=dt.date(2026, 8, 24))
        errors = publish.precheck(self.pd, pairs)
        self.assertTrue(any("render" in e for e in errors))

    @mock.patch.dict("os.environ", ENV_OK)
    def test_clip_without_a_title_points_at_curation(self):
        import datetime as dt
        from talaria import schedule
        _project(self.pd, title="")
        pairs = schedule.pending(self.pd, day=dt.date(2026, 8, 24))
        errors = publish.precheck(self.pd, pairs)
        self.assertTrue(any("title" in e and "curation" in e for e in errors))

    @mock.patch.dict("os.environ", ENV_OK)
    def test_title_over_100_aborts(self):
        import datetime as dt
        from talaria import schedule
        _project(self.pd, title="x" * 101)
        pairs = schedule.pending(self.pd, day=dt.date(2026, 8, 24))
        errors = publish.precheck(self.pd, pairs)
        self.assertTrue(any("100" in e for e in errors))

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_missing_credential_lists_the_variables(self):
        import datetime as dt
        from talaria import schedule
        pairs = schedule.pending(self.pd, day=dt.date(2026, 8, 24))
        errors = publish.precheck(self.pd, pairs)
        text = "\n".join(errors)
        for var in ("IG_PAGE_TOKEN", "YT_REFRESH_TOKEN", "S3_PUBLISH_BUCKET"):
            self.assertIn(var, text)

    @mock.patch.dict("os.environ", {**ENV_OK, "YT_PRIVACY": "unlised"})
    def test_invalid_yt_privacy_fails_before_uploading(self):
        # A typo in the privacy value has to surface BEFORE the upload: found
        # afterwards, the video would already be live under the wrong privacy.
        import datetime as dt
        from talaria import schedule
        pairs = schedule.pending(self.pd, day=dt.date(2026, 8, 24))
        errors = publish.precheck(self.pd, pairs)
        self.assertTrue(any("YT_PRIVACY" in e for e in errors))

    @mock.patch.dict("os.environ", {**ENV_OK, "YT_PRIVACY": "unlisted"})
    def test_valid_yt_privacy_passes(self):
        import datetime as dt
        from talaria import schedule
        pairs = schedule.pending(self.pd, day=dt.date(2026, 8, 24))
        self.assertEqual(publish.precheck(self.pd, pairs), [])

    @mock.patch.dict("os.environ", ENV_OK)
    def test_missing_post_png_points_at_generate(self):
        import datetime as dt
        from talaria import schedule
        folder = layout.posts_png(self.pd)
        for n in os.listdir(folder):
            if n.endswith(".png"):
                os.remove(os.path.join(folder, n))
        pairs = schedule.pending(self.pd, day=dt.date(2026, 8, 24))
        errors = publish.precheck(self.pd, pairs)
        self.assertTrue(any("post --generate" in e for e in errors))


class TestPostPngs(unittest.TestCase):
    def setUp(self):
        self.pd = tempfile.mkdtemp()
        _project(self.pd)

    def test_carousel_ordered_numerically(self):
        folder = layout.posts_png(self.pd)
        # _10 after _2: NUMERIC ordering, not alphabetical
        for n in ("post_cit_x_10.png",):
            open(os.path.join(folder, n), "w").close()
        pngs = publish._post_pngs(self.pd, "cit_x")
        names = [os.path.basename(p) for p in pngs]
        self.assertEqual(names, ["post_cit_x_1.png", "post_cit_x_2.png",
                                 "post_cit_x_10.png"])


@mock.patch.dict("os.environ", ENV_OK)
@mock.patch("talaria.publish.publish_instagram")
@mock.patch("talaria.publish.publish_youtube")
class TestExecute(unittest.TestCase):
    def setUp(self):
        self.pd = tempfile.mkdtemp()
        _project(self.pd)
        self.day = __import__("datetime").date(2026, 8, 24)

    def test_publishes_everything_and_records_each_one(self, yt, ig):
        yt.upload.return_value = {"id": "v1", "url": "https://yt/v1"}
        ig.publish_reel.return_value = {"id": "r1", "permalink": "https://ig/r1"}
        ig.publish_post.return_value = {"id": "p1", "permalink": "https://ig/p1"}
        results = publish.execute(self.pd, day=self.day)
        self.assertEqual([r["ok"] for r in results], [True, True, True])
        from talaria import published
        reg = published.load(self.pd)
        self.assertTrue(published.is_published(reg, "youtube_shorts", "clip1"))
        self.assertTrue(published.is_published(reg, "instagram_reels", "clip1"))
        self.assertTrue(published.is_published(reg, "instagram_posts", "cit_x"))
        # the title came from moments.json, the description from the .txt
        args = yt.upload.call_args[0]
        self.assertEqual(args[1], "Short title")
        self.assertIn("Clip caption.", args[2])

    def test_a_failure_on_one_platform_does_not_block_the_others(self, yt, ig):
        yt.upload.side_effect = RuntimeError("quota exceeded")
        ig.publish_reel.return_value = {"id": "r1", "permalink": "u"}
        ig.publish_post.return_value = {"id": "p1", "permalink": "u"}
        results = publish.execute(self.pd, day=self.day)
        per_pl = {r["platform"]: r["ok"] for r in results}
        self.assertFalse(per_pl["youtube_shorts"])
        self.assertTrue(per_pl["instagram_reels"])
        self.assertTrue(per_pl["instagram_posts"])
        # what failed does NOT enter the record — it retries tomorrow
        from talaria import published
        reg = published.load(self.pd)
        self.assertFalse(published.is_published(reg, "youtube_shorts", "clip1"))

    def test_the_record_is_immediate_not_at_the_end_of_the_batch(self, yt, ig):
        # If the process dies on item 2, item 1 is already recorded.
        from talaria import published
        state = {}

        def upload_ok(*a, **k):
            return {"id": "v1", "url": "u"}

        def reel_explode(*a, **k):
            # at this point YouTube must ALREADY be recorded
            reg = published.load(self.pd)
            state["yt_recorded"] = published.is_published(
                reg, "youtube_shorts", "clip1")
            raise RuntimeError("boom")

        yt.upload.side_effect = upload_ok
        ig.publish_reel.side_effect = reel_explode
        ig.publish_post.return_value = {"id": "p1", "permalink": "u"}
        publish.execute(self.pd, day=self.day)
        self.assertTrue(state["yt_recorded"])

    def test_a_record_failing_after_going_live_is_not_a_retry(self, yt, ig):
        # The module's worst case: the video WENT UP and the record failed
        # (disk full). Marking ok=False would send the pair to tomorrow's queue
        # and publish it again — a duplicate with no fix. It has to come out as
        # published, shouting that the record needs repairing by hand.
        yt.upload.return_value = {"id": "v1", "url": "https://yt/v1"}
        ig.publish_reel.return_value = {"id": "r1", "permalink": "u"}
        ig.publish_post.return_value = {"id": "p1", "permalink": "u"}
        with mock.patch("talaria.publish.published.record",
                        side_effect=OSError("disk full")):
            results = publish.execute(self.pd, day=self.day)

        yt_r = [r for r in results if r["platform"] == "youtube_shorts"][0]
        self.assertTrue(yt_r["ok"])           # it is live: not a failure
        self.assertTrue(yt_r["record_failed"])
        self.assertEqual(yt_r["id"], "v1")    # id for the manual repair
        self.assertIn("disk full", yt_r["error"])

    def test_a_normal_publication_does_not_flag_record_failed(self, yt, ig):
        yt.upload.return_value = {"id": "v1", "url": "u"}
        ig.publish_reel.return_value = {"id": "r1", "permalink": "u"}
        ig.publish_post.return_value = {"id": "p1", "permalink": "u"}
        results = publish.execute(self.pd, day=self.day)
        self.assertTrue(all(not r.get("record_failed") for r in results))

    def test_a_failed_precheck_publishes_nothing(self, yt, ig):
        os.remove(os.path.join(layout.platform(self.pd, "youtube_shorts"),
                               "clip1_short.mp4"))
        with self.assertRaises(ValueError):
            publish.execute(self.pd, day=self.day)
        yt.upload.assert_not_called()
        ig.publish_reel.assert_not_called()
        ig.publish_post.assert_not_called()

    def test_nothing_pending_returns_empty(self, yt, ig):
        future = __import__("datetime").date(2026, 8, 1)
        self.assertEqual(publish.execute(self.pd, day=future), [])
        yt.upload.assert_not_called()


if __name__ == "__main__":
    unittest.main()
