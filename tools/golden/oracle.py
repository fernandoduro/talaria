# python-reason: long-lived CPython differential oracle until the Go cutover
"""One JSON request/response per line, no protocol output on stderr/stdout."""
import contextlib
import io
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from talaria import utils, post_instagram

for line in sys.stdin:
    try:
        req = json.loads(line)
        with contextlib.redirect_stdout(io.StringIO()):
            if req["op"] == "clean_caption":
                value = utils.clean_caption(req["text"])
            elif req["op"] == "fix_proper_nouns":
                value = utils.fix_proper_nouns(req["text"], req["names"])
            elif req["op"] == "file_slug":
                value = post_instagram.file_slug(req["text"])
            else:
                raise ValueError("unknown oracle operation")
        result = {"value": value, "error": None}
    except Exception as exc:
        result = {"value": "", "error": str(exc)}
    print(json.dumps(result, ensure_ascii=True), flush=True)
