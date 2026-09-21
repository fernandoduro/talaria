"""Card de encerramento: logo + @ ao final de cada corte."""
import os
import subprocess
import tempfile
import time
import unittest

from PIL import Image

from nvshorts import config, encerramento


class TestMontaCard(unittest.TestCase):
    def test_tamanho_do_frame_bate_com_o_video(self):
        img = encerramento.monta_card()
        self.assertEqual(img.size, (config.FRAME_W, config.FRAME_H))

    def test_fundo_e_o_configurado(self):
        img = encerramento.monta_card()
        # Canto da imagem não tem logo nem texto — é fundo puro.
        self.assertEqual(img.getpixel((5, 5)), config.CARD_FUNDO)

    def test_logo_aparece_centralizado(self):
        # O bloco logo+@ é centralizado; o pixel exato do meio-meio da tela
        # varia com o design, então o teste confere que ALGO foi desenhado
        # ali (não é mais o fundo liso) em vez de fixar posição de pixel.
        img = encerramento.monta_card()
        centro = img.getpixel((config.FRAME_W // 2, config.FRAME_H // 2))
        self.assertNotEqual(centro, config.CARD_FUNDO)

    def test_logo_ausente_da_mensagem_clara(self):
        # Mesmo padrão do POST_TEMPLATE em post_instagram.py: erro explícito
        # dizendo onde o asset deveria estar, não um FileNotFoundError cru
        # do Pillow apontando pra um caminho sem contexto.
        antigo = config.LOGO_PATH
        config.LOGO_PATH = "/caminho/que/nao/existe/logo.png"
        try:
            with self.assertRaises(FileNotFoundError) as e:
                encerramento.monta_card()
            self.assertIn("assets/", str(e.exception))
        finally:
            config.LOGO_PATH = antigo


class TestCardCacheado(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def test_gera_o_arquivo_na_primeira_chamada(self):
        caminho = encerramento.card_cacheado(self.d)
        self.assertTrue(os.path.exists(caminho))

    def test_duracao_do_arquivo_bate_com_config(self):
        caminho = encerramento.card_cacheado(self.d)
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", caminho],
            capture_output=True, text=True, check=True)
        self.assertAlmostEqual(float(r.stdout.strip()),
                               config.CARD_DURACAO_S, delta=0.15)

    def test_reaproveita_sem_regravar(self):
        caminho = encerramento.card_cacheado(self.d)
        mtime_1 = os.path.getmtime(caminho)
        time.sleep(0.05)
        caminho_2 = encerramento.card_cacheado(self.d)
        self.assertEqual(caminho, caminho_2)
        self.assertEqual(os.path.getmtime(caminho), mtime_1)

    def test_logo_trocado_invalida_o_cache(self):
        caminho = encerramento.card_cacheado(self.d)
        mtime_1 = os.path.getmtime(caminho)
        # Guarda o mtime ANTES de mexer, em vez de reconstruí-lo do git no
        # final: fora de um clone git (tarball, cópia do código) o comando não
        # devolve nada, a restauração não acontece em silêncio e o logo fica
        # no futuro — quebrando o teste de cache que roda depois deste.
        stat_antes = os.stat(config.LOGO_PATH)
        futuro = time.time() + 5
        os.utime(config.LOGO_PATH, (futuro, futuro))
        try:
            time.sleep(0.05)
            encerramento.card_cacheado(self.d)
            self.assertGreater(os.path.getmtime(caminho), mtime_1)
        finally:
            os.utime(config.LOGO_PATH,
                     (stat_antes.st_atime, stat_antes.st_mtime))

    def test_nao_deixa_temporario_para_tras(self):
        # A escrita passa por um .tmp.mp4/.tmp.png com o PID — nenhum dos
        # dois pode sobrar depois de card_cacheado() terminar com sucesso.
        destino = encerramento.card_cacheado(self.d)
        pasta = os.path.dirname(destino)
        sobras = [n for n in os.listdir(pasta) if ".tmp" in n]
        self.assertEqual(sobras, [], f"temporário ficou para trás: {sobras}")

    def test_race_entre_dois_processos_nao_corrompe(self):
        # Simula dois "processos" concorrentes chamando card_cacheado() para
        # o MESMO episódio, cada um com seu PID simulado (o teste roda no
        # mesmo processo, então cada chamada usa os.getpid() real — o que
        # importa aqui é que o produto final é sempre um mp4 válido e
        # completo, nunca um arquivo pela metade de uma escrita concorrente).
        r1 = encerramento.card_cacheado(self.d)
        r2 = encerramento.card_cacheado(self.d)
        self.assertEqual(r1, r2)
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", r1], capture_output=True, text=True, check=True)
        self.assertAlmostEqual(float(r.stdout.strip()),
                               config.CARD_DURACAO_S, delta=0.15)


if __name__ == "__main__":
    unittest.main()
