"""Testes do S3 temporário (a Graph API exige URL pública da mídia)."""
import unittest
from unittest import mock

from talaria import storage_temp


class TestPut(unittest.TestCase):
    @mock.patch.dict("os.environ", {"S3_PUBLISH_BUCKET": "meu-bucket"})
    @mock.patch("talaria.storage_temp.boto3")
    def test_sobe_no_prefixo_e_devolve_url_assinada(self, boto3_mock):
        s3 = boto3_mock.client.return_value
        s3.generate_presigned_url.return_value = "https://assinada"
        url = storage_temp.put("/tmp/video.mp4")
        self.assertEqual(url, "https://assinada")
        bucket, key = s3.upload_file.call_args[0][1:3]
        self.assertEqual(bucket, "meu-bucket")
        self.assertTrue(key.startswith("tmp-publish/"))
        self.assertTrue(key.endswith("_video.mp4"))
        # Validade de 1h: tempo pro Instagram processar, sem URL eterna.
        kwargs = s3.generate_presigned_url.call_args
        self.assertEqual(kwargs.kwargs.get("ExpiresIn"), 3600)

    @mock.patch.dict("os.environ", {"S3_PUBLISH_BUCKET": "b",
                                    "S3_ENDPOINT_URL": "https://r2.exemplo"})
    @mock.patch("talaria.storage_temp.boto3")
    def test_endpoint_customizado_permite_r2_e_compativeis(self, boto3_mock):
        # Sem endpoint configurável o boto3 só fala com a AWS. R2/MinIO usam
        # a mesma API — mudar de provedor não pode exigir mudar código.
        storage_temp.put("/tmp/video.mp4")
        self.assertEqual(boto3_mock.client.call_args.kwargs.get("endpoint_url"),
                         "https://r2.exemplo")

    @mock.patch.dict("os.environ", {"S3_PUBLISH_BUCKET": "b"}, clear=True)
    @mock.patch("talaria.storage_temp.boto3")
    def test_sem_endpoint_usa_o_padrao_da_aws(self, boto3_mock):
        storage_temp.put("/tmp/video.mp4")
        self.assertIsNone(boto3_mock.client.call_args.kwargs.get("endpoint_url"))

    @mock.patch.dict("os.environ", {"S3_PUBLISH_BUCKET": "b"})
    @mock.patch("talaria.storage_temp.boto3")
    def test_assina_com_sigv4(self, boto3_mock):
        # O boto3 pode cair em SigV2, que o R2 recusa com 401 na URL assinada
        # — e aí o Instagram não baixa a mídia. O error só apareceria na
        # publicação, como "container falhou", sem dizer que era a assinatura.
        storage_temp.put("/tmp/video.mp4")
        cfg = boto3_mock.client.call_args.kwargs.get("config")
        self.assertEqual(getattr(cfg, "signature_version", None), "s3v4")

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_sem_bucket_no_ambiente_aborta_com_o_nome_da_variavel(self):
        with self.assertRaises(RuntimeError) as ctx:
            storage_temp.put("/tmp/video.mp4")
        self.assertIn("S3_PUBLISH_BUCKET", str(ctx.exception))


class TestRemove(unittest.TestCase):
    @mock.patch.dict("os.environ", {"S3_PUBLISH_BUCKET": "meu-bucket"})
    @mock.patch("talaria.storage_temp.boto3")
    def test_remove_pela_key_da_url(self, boto3_mock):
        s3 = boto3_mock.client.return_value
        storage_temp.remove(
            "https://meu-bucket.s3.amazonaws.com/tmp-publish/abc_v.mp4?X-Amz=1")
        s3.delete_object.assert_called_once_with(
            Bucket="meu-bucket", Key="tmp-publish/abc_v.mp4")

    @mock.patch.dict("os.environ", {"S3_PUBLISH_BUCKET": "meu-bucket"})
    @mock.patch("talaria.storage_temp.boto3")
    def test_remove_em_url_path_style(self, boto3_mock):
        # R2 e MinIO assinam no formato /bucket/key, não bucket.host/key. Sem
        # tirar o bucket do path, o delete apontava para uma key que não
        # existe e falhava calado — o arquivo ficava público até expirar.
        s3 = boto3_mock.client.return_value
        storage_temp.remove(
            "https://account.r2.cloudflarestorage.com/meu-bucket/"
            "tmp-publish/abc_v.mp4?X-Amz-Signature=x")
        s3.delete_object.assert_called_once_with(
            Bucket="meu-bucket", Key="tmp-publish/abc_v.mp4")

    @mock.patch.dict("os.environ", {"S3_PUBLISH_BUCKET": "tmp-publish"})
    @mock.patch("talaria.storage_temp.boto3")
    def test_bucket_com_nome_do_prefixo_nao_corta_demais(self, boto3_mock):
        # Bucket chamado igual ao PREFIX: na URL da AWS o bucket está no
        # HOST, e a key já começa em 'tmp-publish/'. Decidir pelo texto do
        # path cortaria o prefixo real e apagaria nada — o mesmo silêncio
        # que a correção do path-style veio resolver.
        s3 = boto3_mock.client.return_value
        storage_temp.remove(
            "https://tmp-publish.s3.amazonaws.com/tmp-publish/abc_v.mp4")
        s3.delete_object.assert_called_once_with(
            Bucket="tmp-publish", Key="tmp-publish/abc_v.mp4")

    @mock.patch.dict("os.environ", {"S3_PUBLISH_BUCKET": "meu-bucket"})
    @mock.patch("talaria.storage_temp.boto3")
    def test_falha_ao_remover_so_avisa(self, boto3_mock):
        # Resíduo no bucket é o pior caso aceitável; publicação perdida não é.
        boto3_mock.client.return_value.delete_object.side_effect = Exception("x")
        storage_temp.remove("https://b.s3.amazonaws.com/tmp-publish/k.mp4")
        # não levantou — passou.


if __name__ == "__main__":
    unittest.main()
