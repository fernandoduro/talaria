"""One-off channel authorisation: prints the YT_REFRESH_TOKEN for the .env.

Runs once, on the channel owner's machine — the pipeline never opens a browser.
`publish` receives the refresh token only through the environment.
"""
from __future__ import annotations

import json
import os
import sys

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
INSTALLED_KEYS = ("client_id", "client_secret", "token_uri")


def validate_client_secret(path: str) -> dict:
    """Returns the `installed` block, or exits explaining what to download.

    publish reads client_secret["installed"]: a Web-type client passes the whole
    consent flow and only breaks on the first upload, once the schedule already
    counts on it. An `installed` block missing the keys
    `publish_youtube._credentials` reads breaks the same way.
    """
    if not os.path.exists(path):
        raise SystemExit(
            f"{path} não existe. Confira o path passado na linha "
            f"de comando."
        )
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise SystemExit(
            f"{path} não é um JSON legível: {e}. Baixe o arquivo de "
            f"novo no Google Cloud Console."
        ) from None
    if not isinstance(data, dict) or "installed" not in data:
        if isinstance(data, dict):
            part = f"tem: {', '.join(sorted(data)) or 'vazio'}"
        else:
            part = "não é um objeto JSON"
        raise SystemExit(
            f"{path} não é um client Desktop ({part}). No Google "
            f"Cloud Console, crie a credencial OAuth com tipo de aplicativo "
            f"'Desktop app' e baixe o JSON dela."
        )
    installed = data["installed"]
    fields = installed if isinstance(installed, dict) else {}
    missing = [k for k in INSTALLED_KEYS if not fields.get(k)]
    if missing:
        raise SystemExit(
            f"{path} tem o bloco 'installed' incompleto (falta "
            f"{', '.join(missing)}). No Google Cloud Console, gere a "
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
    # access_type=offline + prompt=consent: without both, Google returns only a
    # 1h access token, and publish needs the refresh one.
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
