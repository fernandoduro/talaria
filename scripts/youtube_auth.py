"""Autorização única do canal: imprime o YT_REFRESH_TOKEN para o .env.

Roda uma vez, na máquina de who é dono do canal — o pipeline nunca abre
browser. O `publish` só recebe o refresh token pelo environment.
"""
from __future__ import annotations

import json
import os
import sys

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
INSTALLED_KEYS = ("client_id", "client_secret", "token_uri")


def validate_client_secret(path: str) -> dict:
    """Devolve o bloco `installed`, ou sai explicando o que baixar.

    O publish lê client_secret["installed"]: um client do kind Web passa pelo
    consentimento inteiro e só quebra no primeiro upload, depois de a agenda
    já contar com ele. Um `installed` sem as chaves que
    `publish_youtube._credentials` lê quebra do mesmo jeito.
    """
    if not os.path.exists(path):
        raise SystemExit(
            f"{path} não existe. Confira o path passado na linha "
            f"de comando."
        )
    try:
        with open(path, encoding="utf-8") as f:
            dados = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise SystemExit(
            f"{path} não é um JSON legível: {e}. Baixe o arquivo de "
            f"novo no Google Cloud Console."
        ) from None
    if not isinstance(dados, dict) or "installed" not in dados:
        if isinstance(dados, dict):
            parte = f"tem: {', '.join(sorted(dados)) or 'vazio'}"
        else:
            parte = "não é um objeto JSON"
        raise SystemExit(
            f"{path} não é um client Desktop ({parte}). No Google "
            f"Cloud Console, crie a credencial OAuth com tipo de aplicativo "
            f"'Desktop app' e baixe o JSON dela."
        )
    installed = dados["installed"]
    campos = installed if isinstance(installed, dict) else {}
    faltando = [k for k in INSTALLED_KEYS if not campos.get(k)]
    if faltando:
        raise SystemExit(
            f"{path} tem o bloco 'installed' incompleto (falta "
            f"{', '.join(faltando)}). No Google Cloud Console, gere a "
            f"credencial OAuth de novo e salve o JSON inteiro."
        )
    return installed


def main(argv: list) -> int:
    if len(argv) != 1:
        raise SystemExit(
            "uso: python scripts/youtube_auth.py <client_secret.json>"
        )
    path = argv[0]
    validate_client_secret(path)

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(path, SCOPES)
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
    print(f"YT_CLIENT_SECRET_PATH={os.path.abspath(path)}")
    print(f"YT_REFRESH_TOKEN={creds.refresh_token}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
