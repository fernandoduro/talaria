"""Testes da publicação no Instagram (Graph API mockada)."""
import unittest
from unittest import mock

from talaria import publish_instagram

ENV = {"IG_PAGE_TOKEN": "tok", "IG_BUSINESS_ACCOUNT_ID": "123"}


def _resposta(corpo, status=200):
    r = mock.Mock()
    r.status_code = status
    r.content = b"x"
    r.json.return_value = corpo
    r.text = str(corpo)
    return r


class TestCredenciais(unittest.TestCase):
    @mock.patch.dict("os.environ", {}, clear=True)
    def test_sem_credencial_diz_qual_variavel(self):
        with self.assertRaises(RuntimeError) as ctx:
            publish_instagram.publica_reel("/tmp/v.mp4", "leg")
        self.assertIn("IG_PAGE_TOKEN", str(ctx.exception))


class TestHostDoToken(unittest.TestCase):
    """A Meta tem dois fluxos, com hosts diferentes e tokens de prefixo
    diferente. Mandar o token de um para o host do outro devolve
    'Cannot parse access token', erro que não diz qual é o problema."""

    def test_token_do_instagram_usa_graph_instagram(self):
        self.assertEqual(publish_instagram.host_do_token("IGAAc0abc"),
                         publish_instagram.GRAPH_INSTAGRAM)

    def test_token_de_pagina_usa_graph_facebook(self):
        self.assertEqual(publish_instagram.host_do_token("EAAGxyz123"),
                         publish_instagram.GRAPH_FACEBOOK)

    def test_desconhecido_cai_no_facebook_que_era_o_padrao(self):
        # Sem prefixo reconhecido, mantém o comportamento anterior em vez de
        # inventar: o erro da API é mais informativo que um palpite nosso.
        self.assertEqual(publish_instagram.host_do_token("xyz"),
                         publish_instagram.GRAPH_FACEBOOK)

    @mock.patch.dict("os.environ", {"IG_PAGE_TOKEN": "IGAAc0tok",
                                    "IG_BUSINESS_ACCOUNT_ID": "123"})
    @mock.patch("talaria.publish_instagram.storage_temp")
    @mock.patch("talaria.publish_instagram.requests")
    def test_publica_no_host_certo_do_token(self, req, storage):
        storage.sobe.return_value = "https://assinada/p.png"
        req.post.side_effect = [_resposta({"id": "c1"}), _resposta({"id": "m1"})]
        req.get.side_effect = [
            _resposta({"status_code": "FINISHED"}),
            _resposta({"permalink": "https://ig/p/1"}),
        ]
        publish_instagram.publica_post(["/tmp/p.png"], "leg")
        url = req.post.call_args_list[0].args[0]
        self.assertTrue(url.startswith(publish_instagram.GRAPH_INSTAGRAM), url)


@mock.patch.dict("os.environ", ENV)
@mock.patch("talaria.publish_instagram.storage_temp")
@mock.patch("talaria.publish_instagram.requests")
class TestPublicaReel(unittest.TestCase):
    def test_container_poll_publish_e_limpa(self, req, storage):
        storage.sobe.return_value = "https://assinada/v.mp4"
        req.post.side_effect = [
            _resposta({"id": "cont1"}),          # cria container
            _resposta({"id": "media9"}),         # media_publish
        ]
        req.get.side_effect = [
            _resposta({"status_code": "FINISHED"}),   # poll
            _resposta({"permalink": "https://instagr.am/p/x"}),
        ]
        r = publish_instagram.publica_reel("/tmp/v.mp4", "legenda")
        self.assertEqual(r, {"id": "media9",
                             "permalink": "https://instagr.am/p/x"})
        storage.remove.assert_called_once_with("https://assinada/v.mp4")

    def test_status_error_vira_falha_com_o_status_na_mensagem(self, req, storage):
        # AP-03/AP-21: ERROR/EXPIRED são finais — sem isso o poll roda pra sempre.
        storage.sobe.return_value = "https://assinada/v.mp4"
        req.post.side_effect = [_resposta({"id": "cont1"})]
        req.get.side_effect = [_resposta({"status_code": "ERROR"})]
        with self.assertRaises(RuntimeError) as ctx:
            publish_instagram.publica_reel("/tmp/v.mp4", "leg")
        self.assertIn("ERROR", str(ctx.exception))
        storage.remove.assert_called_once()  # limpa também na falha

    def test_timeout_do_poll_desiste_com_mensagem(self, req, storage):
        storage.sobe.return_value = "https://assinada/v.mp4"
        req.post.side_effect = [_resposta({"id": "cont1"})]
        req.get.return_value = _resposta({"status_code": "IN_PROGRESS"})
        relogio = iter([0, 100, 200, 400])  # estoura os 300s no 4º tique
        with mock.patch("talaria.publish_instagram.time") as t:
            t.monotonic.side_effect = relogio
            with self.assertRaises(RuntimeError) as ctx:
                publish_instagram.publica_reel("/tmp/v.mp4", "leg")
        self.assertIn("desisti", str(ctx.exception))

    def test_corpo_que_nao_e_json_ainda_vira_erro_legivel(self, req, storage):
        # Proxy/balanceador na frente do Graph devolve HTML no 502. Deixar o
        # r.json() estourar troca "Graph API: 502" por um JSONDecodeError que
        # não diz o que aconteceu — justo na hora do incidente.
        storage.sobe.return_value = "https://assinada/v.mp4"
        ruim = mock.Mock()
        ruim.status_code = 502
        ruim.content = b"<html>Bad Gateway</html>"
        ruim.json.side_effect = ValueError("Expecting value")
        ruim.text = "<html>Bad Gateway</html>"
        req.post.side_effect = [ruim]
        with self.assertRaises(RuntimeError) as ctx:
            publish_instagram.publica_reel("/tmp/v.mp4", "leg")
        self.assertIn("Bad Gateway", str(ctx.exception))

    def test_erro_da_api_carrega_a_mensagem_da_api(self, req, storage):
        storage.sobe.return_value = "https://assinada/v.mp4"
        req.post.side_effect = [
            _resposta({"error": {"message": "Invalid OAuth token"}}, 400)]
        with self.assertRaises(RuntimeError) as ctx:
            publish_instagram.publica_reel("/tmp/v.mp4", "leg")
        self.assertIn("Invalid OAuth token", str(ctx.exception))


@mock.patch.dict("os.environ", ENV)
@mock.patch("talaria.publish_instagram.storage_temp")
@mock.patch("talaria.publish_instagram.requests")
class TestPublicaPost(unittest.TestCase):
    def test_imagem_unica_sem_carrossel(self, req, storage):
        storage.sobe.return_value = "https://assinada/p.png"
        req.post.side_effect = [
            _resposta({"id": "cont1"}),
            _resposta({"id": "media1"}),
        ]
        req.get.side_effect = [
            _resposta({"status_code": "FINISHED"}),
            _resposta({"permalink": "https://ig/p/1"}),
        ]
        r = publish_instagram.publica_post(["/tmp/p.png"], "leg")
        self.assertEqual(r["id"], "media1")
        # imagem única: container direto, sem children
        params = req.post.call_args_list[0].kwargs["params"]
        self.assertIn("image_url", params)
        self.assertNotIn("children", params)

    def test_imagem_espera_o_container_ficar_pronto(self, req, storage):
        # O container de IMAGEM também processa assíncrono. Publicar com ele
        # ainda IN_PROGRESS devolve "Media ID is not available" — foi o que
        # derrubou o post do EP9, porque esta função presumia upload síncrono.
        storage.sobe.return_value = "https://assinada/p.png"
        req.post.side_effect = [
            _resposta({"id": "cont1"}),
            _resposta({"id": "media1"}),
        ]
        req.get.side_effect = [
            _resposta({"status_code": "IN_PROGRESS"}),
            _resposta({"status_code": "FINISHED"}),
            _resposta({"permalink": "https://ig/p/1"}),
        ]
        with mock.patch("talaria.publish_instagram.POLL_INTERVALO_S", 0):
            r = publish_instagram.publica_post(["/tmp/p.png"], "leg")
        self.assertEqual(r["id"], "media1")
        # O media_publish só sai DEPOIS do container ficar FINISHED.
        caminhos = [c.args[0] for c in req.post.call_args_list]
        self.assertTrue(caminhos[1].endswith("media_publish"))
        self.assertEqual(req.get.call_count, 3)

    def test_imagem_com_container_em_erro_nao_publica(self, req, storage):
        # Container que termina em ERROR é falha explícita, não tentativa de
        # publicar assim mesmo.
        storage.sobe.return_value = "https://assinada/p.png"
        req.post.side_effect = [_resposta({"id": "cont1"})]
        req.get.side_effect = [_resposta({"status_code": "ERROR"})]
        with self.assertRaises(RuntimeError) as ctx:
            publish_instagram.publica_post(["/tmp/p.png"], "leg")
        self.assertIn("ERROR", str(ctx.exception))
        self.assertEqual(req.post.call_count, 1)  # não chamou media_publish

    def test_upload_que_falha_no_meio_limpa_o_que_ja_subiu(self, req, storage):
        # Falha no 3º de 5: os 2 primeiros já estão no bucket e precisam sair.
        # Uma list comprehension só liga o nome no fim, então o `finally`
        # veria [] e deixaria os temporários órfãos lá.
        storage.sobe.side_effect = ["https://a/1.png", "https://a/2.png",
                                    Exception("upload caiu")]
        with self.assertRaises(Exception):
            publish_instagram.publica_post(
                ["/tmp/1.png", "/tmp/2.png", "/tmp/3.png"], "leg")
        self.assertEqual(
            [c.args[0] for c in storage.remove.call_args_list],
            ["https://a/1.png", "https://a/2.png"])

    def test_carrossel_cria_filhos_e_pai(self, req, storage):
        storage.sobe.side_effect = ["https://a/1.png", "https://a/2.png"]
        req.post.side_effect = [
            _resposta({"id": "f1"}), _resposta({"id": "f2"}),  # filhos
            _resposta({"id": "pai"}),                          # carrossel
            _resposta({"id": "media2"}),                       # publish
        ]
        # Um poll por filho e um do pai: montar o pai sobre filho ainda
        # IN_PROGRESS falha, e aí sem dizer qual dos filhos era.
        req.get.side_effect = [
            _resposta({"status_code": "FINISHED"}),   # f1
            _resposta({"status_code": "FINISHED"}),   # f2
            _resposta({"status_code": "FINISHED"}),   # pai
            _resposta({"permalink": "https://ig/p/2"}),
        ]
        r = publish_instagram.publica_post(["/tmp/1.png", "/tmp/2.png"], "leg")
        self.assertEqual(r["id"], "media2")
        pai_params = req.post.call_args_list[2].kwargs["params"]
        self.assertEqual(pai_params["children"], "f1,f2")
        self.assertEqual(pai_params["media_type"], "CAROUSEL")
        self.assertEqual(storage.remove.call_count, 2)  # limpa os dois


if __name__ == "__main__":
    unittest.main()
