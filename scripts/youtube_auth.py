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
            f"{path} does not exist. Check the path given on the command "
            f"line."
        )
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise SystemExit(
            f"{path} is not readable JSON: {e}. Download the file again "
            f"from the Google Cloud Console."
        ) from None
    if not isinstance(data, dict) or "installed" not in data:
        if isinstance(data, dict):
            part = f"it has: {', '.join(sorted(data)) or 'nothing'}"
        else:
            part = "it is not a JSON object"
        raise SystemExit(
            f"{path} is not a Desktop client ({part}). In the Google "
            f"Cloud Console, create the OAuth credential with application "
            f"type 'Desktop app' and download its JSON."
        )
    installed = data["installed"]
    fields = installed if isinstance(installed, dict) else {}
    missing = [k for k in INSTALLED_KEYS if not fields.get(k)]
    if missing:
        raise SystemExit(
            f"{path} has an incomplete 'installed' block (missing "
            f"{', '.join(missing)}). In the Google Cloud Console, generate "
            f"the OAuth credential again and save the whole JSON."
        )
    return installed


def main(argv: list) -> int:
    if len(argv) != 1:
        raise SystemExit(
            "usage: python scripts/youtube_auth.py <client_secret.json>"
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
            "Google did not return a refresh_token. Revoke this app's access "
            "at myaccount.google.com/permissions and run again."
        )
    print()
    print("Paste into .env:")
    print()
    print(f"YT_CLIENT_SECRET_PATH={os.path.abspath(path)}")
    print(f"YT_REFRESH_TOKEN={creds.refresh_token}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
