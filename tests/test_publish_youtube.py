"""Tests for the Shorts upload (YouTube Data API mocked)."""
import json
import os
import tempfile
import unittest
from unittest import mock

from talaria import publish_youtube


def _client_secret(d):
    path = os.path.join(d, "client_secret.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"installed": {
            "client_id": "cid", "client_secret": "cs",
            "token_uri": "https://oauth2.googleapis.com/token"}}, f)
    return path


class TestCredentials(unittest.TestCase):
    @mock.patch.dict("os.environ", {}, clear=True)
    def test_missing_credential_names_the_variable_and_the_script(self):
        with self.assertRaises(RuntimeError) as ctx:
            publish_youtube.upload("/tmp/v.mp4", "t", "d")
        self.assertIn("YT_CLIENT_SECRET_PATH", str(ctx.exception))
        self.assertIn("youtube_auth", str(ctx.exception))


class TestUpload(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.env = {"YT_CLIENT_SECRET_PATH": _client_secret(self.d),
                    "YT_REFRESH_TOKEN": "rt"}

    @mock.patch("talaria.publish_youtube.MediaFileUpload")
    @mock.patch("talaria.publish_youtube.build")
    def test_upload_returns_the_short_id_and_url(self, build_mock, media_mock):
        with mock.patch.dict("os.environ", self.env):
            insert = build_mock.return_value.videos.return_value.insert
            insert.return_value.next_chunk.return_value = (None, {"id": "V1D"})
            r = publish_youtube.upload("/tmp/v.mp4", "Title", "Description")
        self.assertEqual(r, {"id": "V1D",
                             "url": "https://www.youtube.com/shorts/V1D"})
        body = insert.call_args.kwargs["body"]
        self.assertEqual(body["snippet"]["title"], "Title")
        self.assertEqual(body["snippet"]["description"], "Description")
        self.assertEqual(body["status"]["privacyStatus"], "public")


class TestPrivacy(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.env = {"YT_CLIENT_SECRET_PATH": _client_secret(self.d),
                    "YT_REFRESH_TOKEN": "rt"}

    def _put(self, extra_env):
        with mock.patch.dict("os.environ", {**self.env, **extra_env}):
            with mock.patch("talaria.publish_youtube.MediaFileUpload"), \
                 mock.patch("talaria.publish_youtube.build") as build_mock:
                insert = build_mock.return_value.videos.return_value.insert
                insert.return_value.next_chunk.return_value = (None, {"id": "V"})
                publish_youtube.upload("/tmp/v.mp4", "T", "D")
                return insert.call_args.kwargs["body"]["status"]

    def test_without_the_variable_it_stays_public(self):
        # The default does not change: configuring nothing publishes as always.
        self.assertEqual(self._put({})["privacyStatus"], "public")

    def test_unlisted_allows_a_check_before_opening_up(self):
        self.assertEqual(self._put({"YT_PRIVACY": "unlisted"})["privacyStatus"],
                         "unlisted")

    def test_private_also_works(self):
        self.assertEqual(self._put({"YT_PRIVACY": "private"})["privacyStatus"],
                         "private")

    def test_an_invalid_value_aborts_instead_of_publishing_publicly(self):
        # A typo ("unlised", "publico") must not silently become a public
        # publication: the video would go live open when the opposite was asked.
        with self.assertRaises(ValueError) as ctx:
            self._put({"YT_PRIVACY": "unlised"})
        self.assertIn("unlised", str(ctx.exception))

    def test_whitespace_and_case_do_not_matter(self):
        self.assertEqual(self._put({"YT_PRIVACY": " Unlisted "})["privacyStatus"],
                         "unlisted")


if __name__ == "__main__":
    unittest.main()
