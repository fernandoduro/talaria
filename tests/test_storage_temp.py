"""Tests for the temporary S3 (the Graph API demands a public media URL)."""
import unittest
from unittest import mock

from talaria import storage_temp


class TestPut(unittest.TestCase):
    @mock.patch.dict("os.environ", {"S3_PUBLISH_BUCKET": "my-bucket"})
    @mock.patch("talaria.storage_temp.boto3")
    def test_uploads_under_the_prefix_and_returns_a_signed_url(self, boto3_mock):
        s3 = boto3_mock.client.return_value
        s3.generate_presigned_url.return_value = "https://signed"
        url = storage_temp.put("/tmp/video.mp4")
        self.assertEqual(url, "https://signed")
        bucket, key = s3.upload_file.call_args[0][1:3]
        self.assertEqual(bucket, "my-bucket")
        self.assertTrue(key.startswith("tmp-publish/"))
        self.assertTrue(key.endswith("_video.mp4"))
        # 1h validity: time for Instagram to process, without an eternal URL.
        kwargs = s3.generate_presigned_url.call_args
        self.assertEqual(kwargs.kwargs.get("ExpiresIn"), 3600)

    @mock.patch.dict("os.environ", {"S3_PUBLISH_BUCKET": "b",
                                    "S3_ENDPOINT_URL": "https://r2.example"})
    @mock.patch("talaria.storage_temp.boto3")
    def test_custom_endpoint_allows_r2_and_compatibles(self, boto3_mock):
        # Without a configurable endpoint boto3 only talks to AWS. R2/MinIO use
        # the same API — switching provider must not require changing code.
        storage_temp.put("/tmp/video.mp4")
        self.assertEqual(boto3_mock.client.call_args.kwargs.get("endpoint_url"),
                         "https://r2.example")

    @mock.patch.dict("os.environ", {"S3_PUBLISH_BUCKET": "b"}, clear=True)
    @mock.patch("talaria.storage_temp.boto3")
    def test_without_an_endpoint_it_uses_the_aws_default(self, boto3_mock):
        storage_temp.put("/tmp/video.mp4")
        self.assertIsNone(boto3_mock.client.call_args.kwargs.get("endpoint_url"))

    @mock.patch.dict("os.environ", {"S3_PUBLISH_BUCKET": "b"})
    @mock.patch("talaria.storage_temp.boto3")
    def test_signs_with_sigv4(self, boto3_mock):
        # boto3 can fall back to SigV2, which R2 refuses with a 401 on the
        # signed URL — and then Instagram does not download the media. The error
        # would only surface at publishing, as "container failed", with nothing
        # naming the signature.
        storage_temp.put("/tmp/video.mp4")
        cfg = boto3_mock.client.call_args.kwargs.get("config")
        self.assertEqual(getattr(cfg, "signature_version", None), "s3v4")

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_missing_bucket_in_the_environment_aborts_naming_the_variable(self):
        with self.assertRaises(RuntimeError) as ctx:
            storage_temp.put("/tmp/video.mp4")
        self.assertIn("S3_PUBLISH_BUCKET", str(ctx.exception))


class TestRemove(unittest.TestCase):
    @mock.patch.dict("os.environ", {"S3_PUBLISH_BUCKET": "my-bucket"})
    @mock.patch("talaria.storage_temp.boto3")
    def test_removes_by_the_key_from_the_url(self, boto3_mock):
        s3 = boto3_mock.client.return_value
        storage_temp.remove(
            "https://my-bucket.s3.amazonaws.com/tmp-publish/abc_v.mp4?X-Amz=1")
        s3.delete_object.assert_called_once_with(
            Bucket="my-bucket", Key="tmp-publish/abc_v.mp4")

    @mock.patch.dict("os.environ", {"S3_PUBLISH_BUCKET": "my-bucket"})
    @mock.patch("talaria.storage_temp.boto3")
    def test_removes_from_a_path_style_url(self, boto3_mock):
        # R2 and MinIO sign in the /bucket/key form, not bucket.host/key.
        # Without stripping the bucket from the path, the delete pointed at a
        # key that does not exist and failed quietly — the file stayed public
        # until it expired.
        s3 = boto3_mock.client.return_value
        storage_temp.remove(
            "https://account.r2.cloudflarestorage.com/my-bucket/"
            "tmp-publish/abc_v.mp4?X-Amz-Signature=x")
        s3.delete_object.assert_called_once_with(
            Bucket="my-bucket", Key="tmp-publish/abc_v.mp4")

    @mock.patch.dict("os.environ", {"S3_PUBLISH_BUCKET": "tmp-publish"})
    @mock.patch("talaria.storage_temp.boto3")
    def test_bucket_named_like_the_prefix_is_not_over_trimmed(self, boto3_mock):
        # A bucket named like the PREFIX: in the AWS URL the bucket is in the
        # HOST, and the key already starts with 'tmp-publish/'. Deciding from
        # the path text would cut the real prefix and delete nothing — the same
        # silence the path-style fix came to solve.
        s3 = boto3_mock.client.return_value
        storage_temp.remove(
            "https://tmp-publish.s3.amazonaws.com/tmp-publish/abc_v.mp4")
        s3.delete_object.assert_called_once_with(
            Bucket="tmp-publish", Key="tmp-publish/abc_v.mp4")

    @mock.patch.dict("os.environ", {"S3_PUBLISH_BUCKET": "my-bucket"})
    @mock.patch("talaria.storage_temp.boto3")
    def test_a_failed_removal_only_warns(self, boto3_mock):
        # A leftover in the bucket is the acceptable worst case; a lost post is not.
        boto3_mock.client.return_value.delete_object.side_effect = Exception("x")
        storage_temp.remove("https://b.s3.amazonaws.com/tmp-publish/k.mp4")
        # it did not raise — that is the pass.


if __name__ == "__main__":
    unittest.main()
