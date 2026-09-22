"""Tests for publishing to Instagram (Graph API mocked)."""
import unittest
from unittest import mock

from talaria import publish_instagram

ENV = {"IG_PAGE_TOKEN": "tok", "IG_BUSINESS_ACCOUNT_ID": "123"}


def _response(body, status=200):
    r = mock.Mock()
    r.status_code = status
    r.content = b"x"
    r.json.return_value = body
    r.text = str(body)
    return r


class TestCredentials(unittest.TestCase):
    @mock.patch.dict("os.environ", {}, clear=True)
    def test_missing_credential_names_the_variable(self):
        with self.assertRaises(RuntimeError) as ctx:
            publish_instagram.publish_reel("/tmp/v.mp4", "cap")
        self.assertIn("IG_PAGE_TOKEN", str(ctx.exception))


class TestHostForToken(unittest.TestCase):
    """Meta has two flows, on different hosts and with differently prefixed
    tokens. Sending one flow's token to the other flow's host returns
    'Cannot parse access token', an error that does not say what is wrong."""

    def test_an_instagram_token_uses_graph_instagram(self):
        self.assertEqual(publish_instagram.host_for_token("IGAAc0abc"),
                         publish_instagram.GRAPH_INSTAGRAM)

    def test_a_page_token_uses_graph_facebook(self):
        self.assertEqual(publish_instagram.host_for_token("EAAGxyz123"),
                         publish_instagram.GRAPH_FACEBOOK)

    def test_an_unknown_prefix_falls_back_to_facebook_the_old_default(self):
        # With no recognised prefix it keeps the previous behaviour instead of
        # inventing one: the API error is more informative than a guess.
        self.assertEqual(publish_instagram.host_for_token("xyz"),
                         publish_instagram.GRAPH_FACEBOOK)

    @mock.patch.dict("os.environ", {"IG_PAGE_TOKEN": "IGAAc0tok",
                                    "IG_BUSINESS_ACCOUNT_ID": "123"})
    @mock.patch("talaria.publish_instagram.storage_temp")
    @mock.patch("talaria.publish_instagram.requests")
    def test_publishes_on_the_host_matching_the_token(self, req, storage):
        storage.put.return_value = "https://signed/p.png"
        req.post.side_effect = [_response({"id": "c1"}), _response({"id": "m1"})]
        req.get.side_effect = [
            _response({"status_code": "FINISHED"}),
            _response({"permalink": "https://ig/p/1"}),
        ]
        publish_instagram.publish_post(["/tmp/p.png"], "cap")
        url = req.post.call_args_list[0].args[0]
        self.assertTrue(url.startswith(publish_instagram.GRAPH_INSTAGRAM), url)


@mock.patch.dict("os.environ", ENV)
@mock.patch("talaria.publish_instagram.storage_temp")
@mock.patch("talaria.publish_instagram.requests")
class TestPublishReel(unittest.TestCase):
    def test_container_poll_publish_and_cleanup(self, req, storage):
        storage.put.return_value = "https://signed/v.mp4"
        req.post.side_effect = [
            _response({"id": "cont1"}),          # create container
            _response({"id": "media9"}),         # media_publish
        ]
        req.get.side_effect = [
            _response({"status_code": "FINISHED"}),   # poll
            _response({"permalink": "https://instagr.am/p/x"}),
        ]
        r = publish_instagram.publish_reel("/tmp/v.mp4", "caption")
        self.assertEqual(r, {"id": "media9",
                             "permalink": "https://instagr.am/p/x"})
        storage.remove.assert_called_once_with("https://signed/v.mp4")

    def test_status_error_becomes_a_failure_naming_the_status(self, req, storage):
        # ERROR/EXPIRED are terminal — without this the poll runs forever.
        storage.put.return_value = "https://signed/v.mp4"
        req.post.side_effect = [_response({"id": "cont1"})]
        req.get.side_effect = [_response({"status_code": "ERROR"})]
        with self.assertRaises(RuntimeError) as ctx:
            publish_instagram.publish_reel("/tmp/v.mp4", "cap")
        self.assertIn("ERROR", str(ctx.exception))
        storage.remove.assert_called_once()  # cleans up on failure too

    def test_poll_timeout_gives_up_with_a_message(self, req, storage):
        storage.put.return_value = "https://signed/v.mp4"
        req.post.side_effect = [_response({"id": "cont1"})]
        req.get.return_value = _response({"status_code": "IN_PROGRESS"})
        clock = iter([0, 100, 200, 400])  # passes 300s on the 4th tick
        with mock.patch("talaria.publish_instagram.time") as t:
            t.monotonic.side_effect = clock
            with self.assertRaises(RuntimeError) as ctx:
                publish_instagram.publish_reel("/tmp/v.mp4", "cap")
        self.assertIn("gave up waiting", str(ctx.exception))

    def test_a_non_json_body_still_becomes_a_readable_error(self, req, storage):
        # A proxy or balancer in front of Graph returns HTML on a 502. Letting
        # r.json() blow up trades "Graph API: 502" for a JSONDecodeError that
        # says nothing about what happened — right during the incident.
        storage.put.return_value = "https://signed/v.mp4"
        bad = mock.Mock()
        bad.status_code = 502
        bad.content = b"<html>Bad Gateway</html>"
        bad.json.side_effect = ValueError("Expecting value")
        bad.text = "<html>Bad Gateway</html>"
        req.post.side_effect = [bad]
        with self.assertRaises(RuntimeError) as ctx:
            publish_instagram.publish_reel("/tmp/v.mp4", "cap")
        self.assertIn("Bad Gateway", str(ctx.exception))

    def test_an_api_error_carries_the_api_message(self, req, storage):
        storage.put.return_value = "https://signed/v.mp4"
        req.post.side_effect = [
            _response({"error": {"message": "Invalid OAuth token"}}, 400)]
        with self.assertRaises(RuntimeError) as ctx:
            publish_instagram.publish_reel("/tmp/v.mp4", "cap")
        self.assertIn("Invalid OAuth token", str(ctx.exception))


@mock.patch.dict("os.environ", ENV)
@mock.patch("talaria.publish_instagram.storage_temp")
@mock.patch("talaria.publish_instagram.requests")
class TestPublishPost(unittest.TestCase):
    def test_a_single_image_without_a_carousel(self, req, storage):
        storage.put.return_value = "https://signed/p.png"
        req.post.side_effect = [
            _response({"id": "cont1"}),
            _response({"id": "media1"}),
        ]
        req.get.side_effect = [
            _response({"status_code": "FINISHED"}),
            _response({"permalink": "https://ig/p/1"}),
        ]
        r = publish_instagram.publish_post(["/tmp/p.png"], "cap")
        self.assertEqual(r["id"], "media1")
        # single image: container directly, no children
        params = req.post.call_args_list[0].kwargs["params"]
        self.assertIn("image_url", params)
        self.assertNotIn("children", params)

    def test_an_image_waits_for_the_container_to_be_ready(self, req, storage):
        # The IMAGE container also processes asynchronously. Publishing while
        # it is still IN_PROGRESS returns "Media ID is not available" — which is
        # what broke the post, because this function assumed a synchronous upload.
        storage.put.return_value = "https://signed/p.png"
        req.post.side_effect = [
            _response({"id": "cont1"}),
            _response({"id": "media1"}),
        ]
        req.get.side_effect = [
            _response({"status_code": "IN_PROGRESS"}),
            _response({"status_code": "FINISHED"}),
            _response({"permalink": "https://ig/p/1"}),
        ]
        with mock.patch("talaria.publish_instagram.POLL_INTERVAL_S", 0):
            r = publish_instagram.publish_post(["/tmp/p.png"], "cap")
        self.assertEqual(r["id"], "media1")
        # media_publish only goes out AFTER the container turns FINISHED.
        paths = [c.args[0] for c in req.post.call_args_list]
        self.assertTrue(paths[1].endswith("media_publish"))
        self.assertEqual(req.get.call_count, 3)

    def test_an_image_with_a_container_in_error_does_not_publish(self, req, storage):
        # A container ending in ERROR is an explicit failure, not an attempt
        # to publish anyway.
        storage.put.return_value = "https://signed/p.png"
        req.post.side_effect = [_response({"id": "cont1"})]
        req.get.side_effect = [_response({"status_code": "ERROR"})]
        with self.assertRaises(RuntimeError) as ctx:
            publish_instagram.publish_post(["/tmp/p.png"], "cap")
        self.assertIn("ERROR", str(ctx.exception))
        self.assertEqual(req.post.call_count, 1)  # media_publish not called

    def test_an_upload_failing_partway_cleans_up_what_went_up(self, req, storage):
        # Failure on the 3rd of 5: the first 2 are in the bucket and must go.
        # A list comprehension only binds the name at the end, so `finally`
        # would see [] and leave the temporaries orphaned there.
        storage.put.side_effect = ["https://a/1.png", "https://a/2.png",
                                    Exception("upload died")]
        with self.assertRaises(Exception):
            publish_instagram.publish_post(
                ["/tmp/1.png", "/tmp/2.png", "/tmp/3.png"], "cap")
        self.assertEqual(
            [c.args[0] for c in storage.remove.call_args_list],
            ["https://a/1.png", "https://a/2.png"])

    def test_a_carousel_creates_children_and_a_parent(self, req, storage):
        storage.put.side_effect = ["https://a/1.png", "https://a/2.png"]
        req.post.side_effect = [
            _response({"id": "f1"}), _response({"id": "f2"}),  # children
            _response({"id": "parent"}),                          # carousel
            _response({"id": "media2"}),                       # publish
        ]
        # One poll per child and one for the parent: building the parent over a
        # still IN_PROGRESS child fails, and then without saying which child.
        req.get.side_effect = [
            _response({"status_code": "FINISHED"}),   # f1
            _response({"status_code": "FINISHED"}),   # f2
            _response({"status_code": "FINISHED"}),   # parent
            _response({"permalink": "https://ig/p/2"}),
        ]
        r = publish_instagram.publish_post(["/tmp/1.png", "/tmp/2.png"], "cap")
        self.assertEqual(r["id"], "media2")
        parent_params = req.post.call_args_list[2].kwargs["params"]
        self.assertEqual(parent_params["children"], "f1,f2")
        self.assertEqual(parent_params["media_type"], "CAROUSEL")
        self.assertEqual(storage.remove.call_count, 2)  # cleans up both


if __name__ == "__main__":
    unittest.main()
