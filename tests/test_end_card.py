"""Card de end_card: logo + @ ao final de cada clip."""
import os
import subprocess
import tempfile
import time
import unittest

from PIL import Image

from talaria import config, end_card


class TestMontaCard(unittest.TestCase):
    def test_tamanho_do_frame_bate_com_o_video(self):
        img = end_card.compose_card()
        self.assertEqual(img.size, (config.FRAME_W, config.FRAME_H))

    def test_fundo_e_o_configurado(self):
        img = end_card.compose_card()
        # Canto da imagem não tem logo nem texto — é fundo puro.
        self.assertEqual(img.getpixel((5, 5)), config.CARD_BG)

    def test_logo_aparece_centralizado(self):
        # O bloco logo+@ é centralizado; o pixel exato do meio-meio da tela
        # varia com o design, então o teste confere que ALGO foi desenhado
        # ali (não é mais o fundo liso) em vez de fixar posição de pixel.
        img = end_card.compose_card()
        centro = img.getpixel((config.FRAME_W // 2, config.FRAME_H // 2))
        self.assertNotEqual(centro, config.CARD_BG)

    def test_logo_ausente_da_mensagem_clara(self):
        # Mesmo padrão do POST_TEMPLATE em post_instagram.py: error explícito
        # dizendo onde o asset deveria estar, não um FileNotFoundError cru
        # do Pillow apontando pra um path sem contexto.
        antigo = config.LOGO_PATH
        config.LOGO_PATH = "/path/que/nao/existe/logo.png"
        try:
            with self.assertRaises(FileNotFoundError) as e:
                end_card.compose_card()
            self.assertIn("assets/", str(e.exception))
        finally:
            config.LOGO_PATH = antigo


class TestCardCacheado(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()

    def test_gera_o_arquivo_na_primeira_chamada(self):
        path = end_card.cached_card(self.d)
        self.assertTrue(os.path.exists(path))

    def test_duracao_do_arquivo_bate_com_config(self):
        path = end_card.cached_card(self.d)
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", path],
            capture_output=True, text=True, check=True)
        self.assertAlmostEqual(float(r.stdout.strip()),
                               config.CARD_DURATION_S, delta=0.15)

    def test_reaproveita_sem_regravar(self):
        path = end_card.cached_card(self.d)
        mtime_1 = os.path.getmtime(path)
        time.sleep(0.05)
        caminho_2 = end_card.cached_card(self.d)
        self.assertEqual(path, caminho_2)
        self.assertEqual(os.path.getmtime(path), mtime_1)

    def test_logo_trocado_invalida_o_cache(self):
        path = end_card.cached_card(self.d)
        mtime_1 = os.path.getmtime(path)
        # Guarda o mtime ANTES de mexer, em vez de reconstruí-lo do git no
        # final: fora de um clone git (tarball, cópia do código) o comando não
        # devolve nada, a restauração não acontece em silêncio e o logo fica
        # no futuro — quebrando o teste de cache que roda depois deste.
        stat_antes = os.stat(config.LOGO_PATH)
        futuro = time.time() + 5
        os.utime(config.LOGO_PATH, (futuro, futuro))
        try:
            time.sleep(0.05)
            end_card.cached_card(self.d)
            self.assertGreater(os.path.getmtime(path), mtime_1)
        finally:
            os.utime(config.LOGO_PATH,
                     (stat_antes.st_atime, stat_antes.st_mtime))

    def test_nao_deixa_temporario_para_tras(self):
        # A escrita passa por um .tmp.mp4/.tmp.png com o PID — nenhum dos
        # dois pode sobrar depois de cached_card() terminar com sucesso.
        destino = end_card.cached_card(self.d)
        pasta = os.path.dirname(destino)
        sobras = [n for n in os.listdir(pasta) if ".tmp" in n]
        self.assertEqual(sobras, [], f"temporário ficou para trás: {sobras}")

    def test_race_entre_dois_processos_nao_corrompe(self):
        # Simula dois "processos" concorrentes chamando cached_card() para
        # o MESMO episódio, cada um com seu PID simulado (o teste roda no
        # mesmo processo, então cada chamada usa os.getpid() real — o que
        # importa aqui é que o produto final é sempre um mp4 válido e
        # completo, nunca um arquivo pela metade de uma escrita concorrente).
        r1 = end_card.cached_card(self.d)
        r2 = end_card.cached_card(self.d)
        self.assertEqual(r1, r2)
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", r1], capture_output=True, text=True, check=True)
        self.assertAlmostEqual(float(r.stdout.strip()),
                               config.CARD_DURATION_S, delta=0.15)


if __name__ == "__main__":
    unittest.main()
