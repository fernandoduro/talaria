"""Instagram quote post (4:5), written over the channel template.

The template (assets/template_instagram.png) carries the background: gradient,
rule and bar. Logo and quote marks are the channel's. This module writes over
it only what changes per post: quote, name and role. It knows nothing of video
or ffmpeg — it takes text and returns a PNG.
"""
from __future__ import annotations

import json
import os
import re

from PIL import Image, ImageDraw, ImageFont

from . import caption, config, episode, layout, render, texts, utils


def _quote_font():
    return ImageFont.truetype(config.POST_FONT, config.POST_QUOTE_SIZE)


def wrap(text: str) -> list:
    """The quote's lines, measured in the post's real font."""
    return render.wrap_by_pixels(text, fnt=_quote_font(),
                                 width=config.POST_TEXT_W)


def validate_card(text: str) -> dict:
    """Does the text fit in a card? Measured in the font, not counted in chars.

    It does not shrink the font to force a fit: a smaller font breaks the visual
    hierarchy and gives away squeezed text. A card that overflows is an editorial
    problem — shorten the sentence or make it one more card in the carousel.
    """
    text = (text or "").strip()
    if not text:
        return {"fits": False, "lines": 0, "reason": "empty quote"}

    lines = wrap(text)

    # A single word wider than the usable width: the wrap puts it on the line
    # anyway, because there is nowhere to break. It would pass the line count
    # and come out cut off at the edge of the image, unannounced.
    fnt = _quote_font()
    for line in lines:
        width = fnt.getlength(line)
        if width > config.POST_TEXT_W:
            return {
                "fits": False,
                "lines": len(lines),
                "reason": (f"'{line.strip()}' does not fit the card width "
                           f"({round(width)}px of {config.POST_TEXT_W}) "
                           f"— word too long, nowhere to break"),
            }

    n = len(lines)
    if n > config.POST_QUOTE_MAX_LINES:
        excess = n - config.POST_QUOTE_MAX_LINES
        return {
            "fits": False,
            "lines": n,
            "reason": (f"{n} lines, {excess} more than the limit of "
                       f"{config.POST_QUOTE_MAX_LINES} — shorten the sentence "
                       f"or break it into another card"),
        }
    return {"fits": True, "lines": n, "reason": ""}


def _truetype(path, size):
    return ImageFont.truetype(path, size)


def episode_author(project_dir: str, who: str = "") -> dict:
    """Footer name, role and company, read from episode.json.

    Proper nouns come from here, never from the transcript — the same rule as
    the burned-in caption. With no external guest, the company signs the quote.

    `who` picks the guest when the episode has more than one. Without `who`, the
    first one signs. A name absent from episode.json raises an error instead of
    falling back to the first: publishing one person's sentence under another
    person's name is the costliest error of this step, and silence here would
    produce exactly that.
    """
    ep = episode.load(project_dir)
    guests = ep.get("guests") or []
    if not guests:
        return {"name": ep.get("company", ""), "role": "",
                "company": ep.get("city", "")}

    c = guests[0]
    if who:
        target = who.strip().casefold()
        matches = [x for x in guests
                  if (x.get("name") or "").strip().casefold() == target]
        if not matches:
            names = ", ".join(x.get("name", "") for x in guests) or "(none)"
            raise ValueError(
                f"'{who}' is not a guest of this episode — episode.json "
                f"has: {names}"
            )
        c = matches[0]

    return {"name": c.get("name", ""), "role": c.get("role", ""),
            "company": ep.get("company", "")}


def clean_quote(text: str, names: list) -> str:
    """Prepares transcribed speech to become a published quote.

    The same treatment as the burned-in caption — expand contractions, strip
    fillers, fix proper nouns — and for the same reason: "gonna" on screen looks
    like a typo. In a quote attributed to a named person that weighs more, so the
    limit is stricter too: NEVER rewrite the sentence. A quote that has to be
    rewritten to work is not the right quote.
    """
    return utils.fix_proper_nouns(utils.clean_caption(text), names)


def render_card(text: str, author: dict, out_path: str, template: str = None):
    """Writes quote and author over the template and saves the PNG.

    `author` carries name, role and company — from episode.json, never from the
    transcript (the transcript gets proper nouns wrong).

    Raises ValueError if the text does not fit: the decision to shorten or split
    into another card is editorial and cannot be taken here.
    """
    template = template or config.POST_TEMPLATE
    if not os.path.exists(template):
        raise FileNotFoundError(
            f"post template not found at {template} — "
            f"the file should be versioned under assets/"
        )

    v = validate_card(text)
    if not v["fits"]:
        raise ValueError(f"quote does not fit the card: {v['reason']}")

    img = Image.open(template).convert("RGB")
    d = ImageDraw.Draw(img)

    # Quote — anchored at the TOP, not centred: 2-line and 5-line cards start
    # at the same height, so the text does not jump as the carousel is swiped.
    quote_font = _quote_font()
    for i, line in enumerate(wrap(text)):
        y = config.POST_QUOTE_Y + i * config.POST_QUOTE_STEP
        d.text((config.POST_MARGIN_X, y), line, font=quote_font,
               fill=config.POST_QUOTE_COLOR)

    # Footer (the rule already comes drawn on the template)
    name_font = _truetype(config.POST_FONT, config.POST_NAME_SIZE)
    d.text((config.POST_MARGIN_X, config.POST_NAME_Y), author["name"],
           font=name_font, fill=config.POST_NAME_COLOR)

    role_font = _truetype(config.POST_MONO, config.POST_ROLE_SIZE)
    footer = " · ".join(p for p in (author.get("role"), author.get("company")) if p)
    d.text((config.POST_MARGIN_X, config.POST_ROLE_Y), footer,
           font=role_font, fill=config.POST_ROLE_COLOR)

    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
    img.save(out_path, quality=95)
    return out_path


def file_slug(slug: str) -> str:
    """A slug safe to become a filename, keeping it readable.

    The slug is typed by hand into `posts.json` and becomes a filename. Without
    this a `../` creates a junk directory inside the output folder and, with
    enough slashes, breaks in a Pillow FileNotFoundError instead of generating
    the post — an error that does not say what was typed wrong.

    It is public because `publish` sanitises through here too, for the same
    reason: a slug that escapes the folder makes publish find a file from
    outside the project and publish it. Both need the SAME rule — two copies
    diverge at the first change and the divergence only shows once published.
    """
    cleaned = re.sub(r"[^\w.-]", "_", (slug or "").strip(), flags=re.UNICODE)
    cleaned = cleaned.strip("._-")
    return cleaned or "post"


def load(project_dir: str) -> list:
    """Reads the project's posts.json."""
    path = layout.posts(project_dir)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"{path} does not exist. Run 'python run.py post --project "
            f"<slug> --clips <n,n>' and choose the quotes in session before "
            f"generating."
        )
    with open(path, encoding="utf-8") as f:
        return (json.load(f) or {}).get("posts") or []


def generate(project_dir: str) -> list:
    """Renders every post in posts.json. Returns the generated paths.

    Validates ALL cards before writing any file: half-finished material in a
    publishing folder is worse than an error up front — the manager could
    publish card 1 of a carousel that never had a card 2.
    """
    posts = load(project_dir)
    if not posts:
        raise ValueError(f"{layout.posts(project_dir)} has no post")

    ep = episode.load(project_dir)
    names = [ep.get("company", "")] + [c.get("name", "")
                                       for c in (ep.get("guests") or [])]
    # First pass: clean and validate everything.
    planned = []
    for p in posts:
        slug = p.get("slug") or "post"
        cards = p.get("cards") or []
        if not cards:
            raise ValueError(f"post '{slug}' has no card")

        # Who signs: the post's `who` (an episode with two guests) or, by
        # default, the first. Resolved here in the first pass so a wrong name
        # aborts before any file is written.
        author = episode_author(project_dir, who=p.get("who", ""))

        # The caption is validated HERE, not when the .txt is written: this
        # function's contract is to abort before writing any file, and a wrong
        # type found later would already have left the PNGs in the folder.
        caption.validate("caption", p.get("caption"), f"post {slug}")
        for i, raw in enumerate(cards, start=1):
            if not isinstance(raw, str):
                raise ValueError(
                    f"post '{slug}' card {i}: expected text, got "
                    f"{type(raw).__name__} — each item of 'cards' is that "
                    f"card's quote"
                )
            text = clean_quote(raw, names)
            v = validate_card(text)
            if not v["fits"]:
                where = f"{slug} card {i}" if len(cards) > 1 else slug
                raise ValueError(f"'{where}': {v['reason']}")
            fname = file_slug(slug)
            name = (f"post_{fname}.png" if len(cards) == 1
                    else f"post_{fname}_{i}.png")
            planned.append((name, text, author))

    # Second pass: write.
    output_dir = layout.posts_png(project_dir)
    os.makedirs(output_dir, exist_ok=True)
    generated = []
    for name, text, signer in planned:
        generated.append(render_card(text, signer,
                                   os.path.join(output_dir, name)))
        print(f"[post] {name}")

    # One caption per POST, not per card: a carousel is a single publication
    # with a single caption. Hence the list comes from `posts`, not `planned`.
    write_captions(output_dir,
                     [(p.get("slug") or "post", p.get("caption", "")) for p in posts],
                     (texts.load(project_dir) or {}).get("hashtags", ""))
    return generated


def write_captions(output_dir: str, captions: list, hashtags: str) -> list:
    """Writes each post's publishing `.txt` into the output folder.

    `captions` is [(slug, caption)] — one item per POST. The filename uses the
    post slug (`post_<slug>.txt`), so an N-card carousel still has a single
    caption, beside its `post_<slug>_1.png`, `_2.png`...

    The slug goes through the same sanitising as the PNG: without it a `../` in
    the JSON would write the `.txt` outside the publishing folder.
    """
    written = []
    for slug, text in captions:
        caption.validate("caption", text, f"post {slug}")
        if not (text or "").strip():
            print(f"[caption] !! {slug}: no caption — the .txt comes out "
                  f"with the hashtags only. Fill it in decisions/posts.json.")
        base = os.path.join(output_dir, f"post_{file_slug(slug)}.png")
        written.append(caption.write(base, caption.compose(text, hashtags)))
    return written
