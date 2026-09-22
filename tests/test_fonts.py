import os
import unittest

from PIL import ImageFont

from talaria import config

EXPECTED = {
    "FONT": ("DejaVu Sans", "Bold"),
    "POST_FONT": ("Poppins", "SemiBold"),
    "POST_MONO": ("DejaVu Sans Mono", "Bold"),
}


class TestFontesVersionadas(unittest.TestCase):
    """As fontes vêm do repositório, não do sistema.

    O texto é queimado no vídeo: fonte resolvida pelo fontconfig muda com a
    máquina e o error só aparece no vídeo published, que não se corrige.
    """

    def test_cada_fonte_e_um_arquivo_do_repositorio(self):
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(config.__file__)))
        esperado = os.path.join(raiz, "assets", "fonts")
        for name in EXPECTED:
            path = getattr(config, name)
            self.assertTrue(os.path.isfile(path), f"{name}: {path}")
            self.assertEqual(os.path.dirname(path), esperado, name)

    def test_cada_fonte_tem_a_identidade_esperada(self):
        for name, identidade in EXPECTED.items():
            fnt = ImageFont.truetype(getattr(config, name), 40)
            self.assertEqual(fnt.getname(), identidade, name)

    def test_fonte_ausente_aborta_com_mensagem_util(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            config._bundled_font("NaoExiste-Bold.ttf")
        self.assertIn("NaoExiste-Bold.ttf", str(ctx.exception))
        self.assertIn("assets/fonts", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
