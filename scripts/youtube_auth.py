"""Autorização única do canal: imprime o YT_REFRESH_TOKEN para o .env.

Roda uma vez, na máquina de quem é dono do canal — o pipeline nunca abre
browser. O `publish` só recebe o refresh token pelo ambiente.
"""
from __future__ import annotations

import json
import os
import sys

ESCOPO = ["https://www.googleapis.com/auth/youtube.upload"]


def valida_client_secret(caminho: str) -> dict:
    """Devolve o bloco `installed`, ou sai explicando o que baixar.

    O publish lê client_secret["installed"]: um client do tipo Web passa pelo
    consentimento inteiro e só quebra no primeiro upload, depois de a agenda
    já contar com ele.
    """
    if not os.path.exists(caminho):
        raise SystemExit(
            f"{caminho} não existe. Confira o caminho passado na linha "
            f"de comando."
        )
    try:
        with open(caminho, encoding="utf-8") as f:
            dados = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise SystemExit(
            f"{caminho} não é um JSON legível: {e}. Baixe o arquivo de "
            f"novo no Google Cloud Console."
        ) from None
    if not isinstance(dados, dict) or "installed" not in dados:
        if isinstance(dados, dict):
            parte = f"tem: {', '.join(sorted(dados)) or 'vazio'}"
        else:
            parte = "não é um objeto JSON"
        raise SystemExit(
            f"{caminho} não é um client Desktop ({parte}). No Google "
            f"Cloud Console, crie a credencial OAuth com tipo de aplicativo "
            f"'Desktop app' e baixe o JSON dela."
        )
    return dados["installed"]


def main(argv: list) -> int:
    if len(argv) != 1:
        raise SystemExit(
            "uso: python scripts/youtube_auth.py <client_secret.json>"
        )
    caminho = argv[0]
    valida_client_secret(caminho)

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(caminho, ESCOPO)
    # access_type=offline + prompt=consent: sem os dois o Google devolve só um
    # access token de 1h, e o publish precisa do refresh.
    creds = flow.run_local_server(port=0, access_type="offline",
                                  prompt="consent")
    if not creds.refresh_token:
        raise SystemExit(
            "o Google não devolveu refresh_token. Revogue o acesso deste app "
            "em myaccount.google.com/permissions e rode de novo."
        )
    print()
    print("Cole no .env:")
    print()
    print(f"YT_CLIENT_SECRET_PATH={os.path.abspath(caminho)}")
    print(f"YT_REFRESH_TOKEN={creds.refresh_token}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
