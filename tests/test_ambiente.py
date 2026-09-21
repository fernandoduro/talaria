"""Testes da carga do .env para o ambiente."""
import os
import tempfile
import unittest
from unittest import mock

from talaria import ambiente


class TestCarrega(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.env = os.path.join(self.d, ".env")

    def _escreve(self, texto):
        with open(self.env, "w", encoding="utf-8") as f:
            f.write(texto)

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_le_par_simples(self):
        self._escreve("IG_PAGE_TOKEN=abc123\n")
        ambiente.carrega(self.env)
        self.assertEqual(os.environ["IG_PAGE_TOKEN"], "abc123")

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_ignora_comentario_e_linha_vazia(self):
        self._escreve("# comentário\n\nA=1\n   # outro\nB=2\n")
        ambiente.carrega(self.env)
        self.assertEqual((os.environ.get("A"), os.environ.get("B")), ("1", "2"))

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_valor_vazio_nao_entra(self):
        # Variável declarada e não preenchida é "não configurada" — entrar
        # como "" faria a checagem de credencial passar e a API recusar
        # depois, com mensagem pior.
        self._escreve("VAZIA=\nCHEIA=x\n")
        ambiente.carrega(self.env)
        self.assertNotIn("VAZIA", os.environ)
        self.assertEqual(os.environ["CHEIA"], "x")

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_tira_aspas_e_espacos(self):
        # Colar de um console costuma trazer aspas junto.
        self._escreve('COM_ASPAS="abc"\nCOM_ESPACO=  def  \nSIMPLES=\'ghi\'\n')
        ambiente.carrega(self.env)
        self.assertEqual(os.environ["COM_ASPAS"], "abc")
        self.assertEqual(os.environ["COM_ESPACO"], "def")
        self.assertEqual(os.environ["SIMPLES"], "ghi")

    @mock.patch.dict("os.environ", {"JA_EXISTE": "do_shell"}, clear=True)
    def test_ambiente_do_shell_vence_o_arquivo(self):
        # `IG_PAGE_TOKEN=x python run.py ...` precisa sobrepor o arquivo, que
        # é o jeito de testar outra credencial sem editar nada.
        self._escreve("JA_EXISTE=do_arquivo\n")
        ambiente.carrega(self.env)
        self.assertEqual(os.environ["JA_EXISTE"], "do_shell")

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_valor_com_igual_no_meio_fica_inteiro(self):
        # Token base64 termina em '=' e URL leva '=' em query.
        self._escreve("T=abc=def==\n")
        ambiente.carrega(self.env)
        self.assertEqual(os.environ["T"], "abc=def==")

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_sem_arquivo_nao_estoura(self):
        # Quem só renderiza corte nunca criou .env — não é erro.
        ambiente.carrega(os.path.join(self.d, "nao_existe"))

    @mock.patch.dict("os.environ", {}, clear=True)
    def test_aceita_export_na_frente(self):
        self._escreve("export A=1\n")
        ambiente.carrega(self.env)
        self.assertEqual(os.environ.get("A"), "1")


if __name__ == "__main__":
    unittest.main()
