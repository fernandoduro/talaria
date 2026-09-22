import os
import unittest

from PIL import ImageFont

from talaria import config

EXPECTED = {
    "FONT": ("DejaVu Sans", "Bold"),
    "POST_FONT": ("Poppins", "SemiBold"),
    "POST_MONO": ("DejaVu Sans Mono", "Bold"),
}


class TestVersionedFonts(unittest.TestCase):
    """As fontes vêm do repositório, não do sistema.

    O texto é queimado no vídeo: fonte resolvida pelo fontconfig muda com a
    máquina e o error só aparece no vídeo published, que não se corrige.
    """

    def test_cada_fonte_e_um_arquivo_do_repositorio(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(config.__file__)))
        expected = os.path.join(root, "assets", "fonts")
        for name in EXPECTED:
            path = getattr(config, name)
            self.assertTrue(os.path.isfile(path), f"{name}: {path}")
            self.assertEqual(os.path.dirname(path), expected, name)

    def test_cada_fonte_tem_a_identidade_esperada(self):
        for name, identity in EXPECTED.items():
            fnt = ImageFont.truetype(getattr(config, name), 40)
            self.assertEqual(fnt.getname(), identity, name)

    def test_fonte_ausente_aborta_com_mensagem_util(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            config._bundled_font("NaoExiste-Bold.ttf")
        self.assertIn("NaoExiste-Bold.ttf", str(ctx.exception))
        self.assertIn("assets/fonts", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
