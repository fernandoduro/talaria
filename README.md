# Talaria

A video pipeline that turns videocast episodes into vertical clips for social
media.

It takes one videocast episode and produces vertical 9:16 clips (YouTube
Shorts / Instagram Reels), quote posts for the feed, a thumbnail and the
publishing texts — and publishes all of it through the APIs, on a schedule of
dates.

## What it does

```
ingest → episode.json → brief --materials → brief --clips → curate
       → render/thumb → post → schedule → publish
```

The code prepares and executes; the editorial judgement stays with whoever
operates it. The `brief` commands assemble reading packets (prompt + metadata
+ transcript) for a language model to consume in a session, and the decisions
come back as JSON files in the episode folder.

## Installation

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
```

Needs `ffmpeg` and `ffprobe` on PATH.

## Usage

```bash
# 1) download the video and convert the transcript
python run.py ingest --project ep1 --src "<url or file>"

# 2) fill in projects/ep1/episode.json (template created by ingest)
#    Season, episode, company, city, guests, links.
#    It is the source of truth — the transcript gets proper nouns wrong.

# 3) materials: title, description and thumbnail text
python run.py brief --project ep1 --materials

# 4) clips: assembles the curation packet
python run.py brief --project ep1 --clips

# 5) follow the curation state between rounds
python run.py curate --project ep1

# 6) once the target is met, export moments.json
python run.py curate --project ep1 --export

# 7) render and produce the thumbnail
python run.py render --project ep1
python run.py thumb  --project ep1

# 8) quote posts for the feed
python run.py post --project ep1 --clips 1,3
python run.py post --project ep1 --generate

# 9) schedule and publish
python run.py schedule --project ep1
python run.py publish  --project ep1
```

## Publishing

The schedule is `decisions/schedule.json`:

```json
{
  "schedule": [
    {"date": "2026-01-12", "kind": "clip", "slug": "clip1_example"},
    {"date": "2026-01-13", "kind": "post", "slug": "clip1_example"}
  ]
}
```

`kind: "clip"` publishes to YouTube Shorts and Instagram Reels; `kind: "post"`
goes to the Instagram feed (single image or carousel). An overdue item stays
pending, and what already went live is recorded in `decisions/published.json`,
per piece **and** platform — a clip whose Reel failed retries only the Reel,
without republishing the Short.

Before publishing, everything is validated: the rendered file, the caption,
the Short's title (≤100 characters), the caption limits and the credentials.
Any outstanding problem aborts **before** the first upload.

**Credentials:** copy `.env.example` to `.env` and fill it in. Instagram
requires a Business account (Creator cannot publish through the API) and
accepts no binary upload: it fetches the media from a public URL, so the file
goes up to an S3-compatible bucket, is published and then removed. For
YouTube, run `python scripts/youtube_auth.py <client_secret.json>` once. The
OAuth client from the Google Cloud Console has to be of type **Desktop**, not
Web.

## Customising

Six things are channel identity. The first four come neutral in this package;
the palette and the fixed texts come with placeholder values.

| What | Where |
|---|---|
| Curation and writing prompts | `prompts/*.md` |
| Post template and logo | `assets/` |
| Show name and social handle | `SHOW_NAME` and `CARD_HANDLE` in `talaria/config.py` |
| Render and post fonts | `assets/fonts/` |
| Thumbnail and card palette | `THUMB_ORANGE`, `CARD_HANDLE_COLOR` and the `POST_*_COLOR` values in `talaria/config.py` |
| Fixed hashtags and the episode call | `CHANNEL_TAGS` in `talaria/hashtags.py` and `EPISODE_PREFIX` in `talaria/caption.py` |

The prompts are skeletons: they carry the structure and the placeholders the
code expects, but the editorial criteria have to be written by whoever knows
the channel. It is the part that most affects the result.

## Tests

```bash
python3 -m unittest discover -s tests -v
```

There are 391 tests, with no network dependency: the API calls (YouTube,
Instagram, S3) are mocked. Run them inside the venv.

## Notes

- Python 3.9+.
- `projects/` is git-ignored (videos do not enter the repository).
- The ffmpeg on some machines has no `drawtext`; in that case the pipeline
  rasterises the captions to PNG and composites them with `overlay`,
  automatically.
