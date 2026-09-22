"""The publishing caption: the text that accompanies each piece at publish time.

A `.txt` beside every `.mp4`/`.png`, with the same base name — the manager opens
it, copies and pastes into the Instagram or YouTube caption field.

The description comes from the caller (`post_caption` of the clip, `caption` of
the post) and the hashtags from `texts.json`, which apply to the whole episode.
Assembling it here, and not in each caller, is the same reason `layout.py` is
the single authority over paths: `render` and `post_instagram` need an identical
format, and two copies diverge at the first change.

The only block that differs per platform is the call to the full episode: it
enters the Short description and not the Reels caption (see `compose`). The
divergence is a parameter of this function, not a second assembler — the rest
of the format has to stay identical at both ends.
"""
from __future__ import annotations

import os

# Description and hashtags are blocks separated by a blank line: that is how
# Instagram and YouTube render a paragraph, and it keeps the hashtag line set
# apart for whoever reviews before publishing.
SEPARATOR = "\n\n"

# The channel does not use em dashes in captions: it reads as AI text, and one
# escaped all the way to a live clip anyway — which is why the rule also lives
# here, where every caption passes through.
EM_DASH = "\u2014"


def validate(field: str, value, piece: str) -> None:
    """Refuses a non-text description, naming the piece and the field.

    Both description fields (`post_caption` on the clip, `caption` on the post)
    are typed by hand into the JSON. Without this check, a value of another kind
    only surfaces much later as `AttributeError: 'int' object has no attribute
    'strip'`, which does not tell the manager where he went wrong.

    `None` passes: that is the absent key, normal in an episode older than the field.
    """
    if value is not None and not isinstance(value, str):
        raise ValueError(
            f"'{piece}': '{field}' esperava texto, recebeu "
            f"{type(value).__name__} — é o caption que acompanha a "
            f"publicação, uma string só."
        )
    if isinstance(value, str) and EM_DASH in value:
        # WARNS instead of aborting: the em dash is a writing choice, and the
        # fix is to rewrite the sentence — swapping the character in code would
        # leave the same AI construction, just with different punctuation.
        # Aborting here would block a render over a matter of style.
        print(f"[caption] !! {piece}: '{field}' tem travessão — o canal não "
              f"usa em legenda (sai com cara de texto de IA). Reescreva a "
              f"frase antes de publicar.")


# Call to the full episode, in the Short description. The YouTube API does not
# link one video to another (`videos.insert` has no relation field), and the
# dashboard link only exists for a Short created from the long video. Writing
# the URL into the description is what is left, and what the channel did by hand.
EPISODE_PREFIX = "▶ Episódio completo: "


def episode_line(url: str | None) -> str:
    """The call to the full episode, or empty when there is no URL.

    An episode with no `youtube_url` in episode.json (the case for every episode
    older than the field) returns an empty string, which `compose` discards like
    any other absent block.
    """
    url = (url or "").strip()
    return EPISODE_PREFIX + url if url else ""


def compose(description: str | None, hashtags: str | None,
          episode_url: str | None = None) -> str:
    """Joins description, episode call and hashtags into a finished caption.

    Any of the blocks may be missing and the result stays usable: with no
    `texts.json` only the description comes out; with no `post_caption` only the
    hashtags. What must not happen is a stray blank line at either end, because
    the text goes straight into the publishing field.

    `episode_url` is optional on purpose: only the YouTube description gets it.
    On Instagram the URL is not clickable and pushes the reader out of the app,
    so the Reels caption comes out without it — the same `.txt` as before.

    `None` arrives when the key does not exist in the JSON — treated as empty
    rather than blowing up, the common case for an old clip predating the field.
    """
    parts = [(description or "").strip(), episode_line(episode_url),
              (hashtags or "").strip()]
    return SEPARATOR.join(p for p in parts if p)


def compose_episode(title: str | None, description: str | None,
                   hashtags: str | None) -> str:
    """Caption for the whole episode: title, description and hashtags.

    The title goes in as the first line because the `.txt` is read while
    uploading the video, and the two fields are pasted into different YouTube
    boxes — having both in one file avoids opening the JSON just for the title.

    The description already carries its own blocks and separators; it is
    inserted as-is, without reflow.
    """
    parts = [(p or "").strip() for p in (title, description, hashtags)]
    return SEPARATOR.join(p for p in parts if p)


def txt_path(piece_path: str) -> str:
    """Path of a piece's sibling `.txt`, swapping the extension.

    Takes the piece path already resolved by `layout` instead of building a new
    one, so literal paths are not reintroduced outside `layout.py`.
    """
    stem, _ = os.path.splitext(piece_path)
    return stem + ".txt"


def write(piece_path: str, text: str) -> str:
    """Writes the caption beside the piece and returns the path written.

    Overwrites whatever is there: regenerating a clip has to update the caption,
    not pile an old version up beside it (the same contract as the `.mp4`, which
    is also rewritten in place).
    """
    destination = txt_path(piece_path)
    os.makedirs(os.path.dirname(os.path.abspath(destination)), exist_ok=True)
    with open(destination, "w", encoding="utf-8") as f:
        f.write(text)
    return destination
