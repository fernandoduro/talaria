import os
import unittest

from PIL import ImageFont

from talaria import config

ESPERADAS = {
    "FONT": ("DejaVu Sans", "Bold"),
    "POST_FONT": ("Poppins", "SemiBold"),
    "POST_MONO": ("DejaVu Sans Mono", "Bold"),
}


class TestFontesVersionadas(unittest.TestCase):
    """As fontes vêm do repositório, não do sistema.

    O texto é queimado no vídeo: fonte resolvida pelo fontconfig muda com a
    máquina e o erro só aparece no vídeo publicado, que não se corrige.
    """

    def test_cada_fonte_e_um_arquivo_do_repositorio(self):
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(config.__file__)))
        esperado = os.path.join(raiz, "assets", "fonts")
        for nome in ESPERADAS:
            caminho = getattr(config, nome)
            self.assertTrue(os.path.isfile(caminho), f"{nome}: {caminho}")
            self.assertEqual(os.path.dirname(caminho), esperado, nome)

    def test_cada_fonte_tem_a_identidade_esperada(self):
        for nome, identidade in ESPERADAS.items():
            fnt = ImageFont.truetype(getattr(config, nome), 40)
            self.assertEqual(fnt.getname(), identidade, nome)

    def test_fonte_ausente_aborta_com_mensagem_util(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            config._fonte_versionada("NaoExiste-Bold.ttf")
        self.assertIn("NaoExiste-Bold.ttf", str(ctx.exception))
        self.assertIn("assets/fonts", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
