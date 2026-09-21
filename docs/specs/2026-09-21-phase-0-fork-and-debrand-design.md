# Talaria — fork, de-brand, and roadmap

Date: 2026-09-21
Status: Phase 0 design approved; Phases 1–4 sketched, each needs its own spec.

## Context

This repository started as `next-video-shorts-pacote`, a handover export of a
video-shorts pipeline built for the *Startups do Interior* podcast under the
*Next Squad* banner. The export was partially sanitized: no brand strings
survive, `NOME_PROGRAMA` and `CARD_ARROBA` ship as placeholders, `assets/` are
blank template images, and `prompts/*.md` are structure-only skeletons.

What did survive is the original project's production history and its editorial
format. The goal is a private, independent tool — English throughout, usable for
any channel format, publishing to several platforms.

## Decisions

| Question | Decision |
|---|---|
| Purpose | Generic reusable tool, not one channel's pipeline |
| Code language | 100% English — identifiers, comments, docs, error strings, prompts |
| Video language | English; `WHISPER_LANG = "en"` |
| Episode schema | Declared in the channel profile at setup, not hardcoded |
| Setup | Profile file is the source of truth; interactive wizard is a front-end |
| Editorial loop | Claude API proposes, operator approves before render |
| Platforms | YouTube Shorts, Instagram Reels + feed, TikTok, behind a publisher interface |
| Name | `talaria` — repo `talaria`, package `talaria/`, env `TALARIA_*` |
| Fonts | Vendored into the repo |

## Roadmap

Five subsystems, too much for one spec. Each phase ends with a green suite and a
usable tool, and gets its own spec → plan → implementation cycle.

- **Phase 0 — fork and foundation.** Private repo, rename off `nvshorts`, strip
  the old project's history references, fix font handling, write the missing
  `scripts/youtube_auth.py`. Detailed below.
- **Phase 1 — full English.** 30 modules, 334 tests, prompts, docs, error
  strings. The PT-phonetics table in `utils.py` is replaced, not translated: its
  vowel and `y`/`i` equivalences only hold for Portuguese.
- **Phase 2 — channel profile.** `channel.toml` carrying declared episode
  schema, identity, fonts, timezone, platform selection; `setup` wizard writing
  it. Replaces most of `config.py` and all of `episodio.py`'s field list.
  Prompts become templates referencing declared fields.
- **Phase 3 — pluggable publishers.** Extract a validate → upload → record
  interface from `publish.py` / `publish_youtube.py` / `publish_instagram.py`;
  add a TikTok adapter (Content Posting API, direct binary upload, so no bucket).
- **Phase 4 — Claude API with review gate.** Client, structured-output parsing,
  a review step between proposal and render.

Ordering constraints: Phase 1 precedes Phase 2 (don't design a profile format in
Portuguese and then translate it). Phase 2 precedes Phase 4 (the API layer
consumes prompts that reference declared schema fields). Phase 3 is independent.

## Phase 0 design

### Repository

This directory is not a git repository. `git init` in place, commit the package
exactly as received, then land the cleanup as separate commits so the
de-branding diff stays inspectable. `gh repo create talaria --private
--source=.` (authenticated as `fernandoduro`, `repo` scope present).

Directory rename `next-video-shorts-pacote` → `talaria` is the last step,
because it changes the working directory of any running session.

### Renaming

`nvshorts/` → `talaria/`, `NVSHORTS_CAPTION_BACKEND` → `TALARIA_CAPTION_BACKEND`.
Intra-package imports are relative (`from . import config`), so the blast radius
outside the directory is: `run.py`, `from nvshorts import ...` in 20 test files,
and a `nvshorts_thumb_` temp-file prefix in `run.py:133`.

The trap is 24 `mock.patch("nvshorts.<module>.<attr>")` string targets in the
tests. A rename that misses one patches a module that no longer exists, which
errors rather than passing silently — but it will not be caught by grepping for
import statements.

### De-branding: keep the measurement, drop the label

The history references are not decoration. `BASE_Y = 1560` is justified by a
recorded observation that a 5-line caption reached y=1128 and invaded the video
frame; `audio.py` records that a defective clip measures −31/−28/−31 dB. The
episode numbers are meaningless outside the original project; the observations
are load-bearing and stay.

- `EP2` / `EP8` / `EP9` / `corte1` labels removed, surrounding facts kept.
- `AP-03` / `AP-06` / `AP-13` / `AP-21` and `CA-1`…`CA-6` deleted. They cite a checklist
  document that is not in the package, so they are dead cross-references. The
  rule each comment states stays; the code does not.
- "a casa" / "prompt da casa" / "fuso da casa" / "volume da casa" / "desta casa"
  → neutral phrasing. Note `casa` is also an ordinary Portuguese verb
  (`utils.py:134` "Regex que casa o nome", `utils.py:213`) and a legitimate
  `_PALAVRAS_COMUNS` entry (`utils.py:158`); only the possessive-idiom uses are
  in scope.
- The originating project's real names are **not** confined to comments, as an
  earlier draft of this spec assumed. `Norvik` is the fixture company name
  across 12 test files (~45 occurrences); `txt_parse.py`'s module docstring
  carries what reads as a verbatim episode excerpt ("estamos aqui hoje em São
  Gonçalo... sobre a Norvik"); and there are real guest names (`Renata
  Silveira`, `Gustavo Reis`, `Daniel`), cities (`São Gonçalo`, `Bauru`) and a
  regional nickname for the interior-São Paulo startup belt (`Sanduíche
  Valley`). All are replaced.

  Each substitution preserves what its tests prove, verified against the live
  code before being chosen. `Norvik` → `Zarvik`: `_padrao_fonetico` yields
  `nl?[oua]rv[yieu][ckq]` for the first and `[sz]l?arv[yieu][ckq]` for the
  second, the same shape, so the three transcription variants still match and
  word-boundary and lowercase handling are unchanged. The near-miss example
  `nossa` → `zarpa`, a real word that fails only at the literal `v` — a sharper
  illustration than the original, which failed at the third character. `São
  Gonçalo` → `Ribeirão Açaí`, because `test_inclui_cidade_e_empresa` asserts
  `#SaoGoncalo` to prove accent stripping, and the replacement slugs to
  `#RibeiraoAcai`, covering `ã`, `ç` and `í` — more coverage, not less. Guest
  names are replaced at identical character length so nothing layout-sensitive
  shifts.

  Deliberate placeholders stay: `Fulano de Tal`, `Nome Errado`, `X`,
  `A.B.C. Tech`, `Empreendedorismo`.
- "o gestor" stays. It names a role, not a brand; Phase 1 makes it "operator".

`test_render.py:215 CITACAO_DO_DESIGN` and the Instagram fixtures contain "sair
do interior", but that string's rendered *width* is what the 5-line fit test
asserts. Replacement text must be of equivalent width, or the test silently
stops testing anything.

### Fonts

Text is burned into video frames and rasterized into PNGs, so font resolution
determines whether output is reproducible. Two defects today:

- `encerramento.py:21` hardcodes `/System/Library/Fonts/Supplemental/Arial
  Bold.ttf` with no fallback. On Linux the closing card cannot be built at all —
  9 errors in `test_encerramento`, 5 in `test_render`, plus the render
  integration test.
- `POST_FONT` and `POST_MONO` have no Linux candidates, and `find_font`'s
  `fc-match` fallback never fails: probed on this machine it substituted Noto
  Sans for both `Poppins:semibold` and `Montserrat:semibold`. On Linux
  `POST_FONT` therefore falls through to DejaVu Sans Bold, which is wider than
  the design font, and `test_citacao_do_design_cabe_em_5_linhas` fails.

The design font is not what `config.py`'s comment claims. The comment names
Poppins/Montserrat, but neither is present on the machine the package was built
on: `test_quebra_do_design_com_a_fonte_do_design` guards its assertion with
`fnt.getname() != ("Avenir Next", "Demi Bold") -> skipTest`, so the approved
5-line break was validated against **Avenir Next Demi Bold**, the macOS
fallback. That test is the 1 skip in the baseline.

Fix: vendor three fonts under `assets/fonts/` with their license files, and
point config at repo-relative paths — Poppins SemiBold (OFL 1.1) for the quote
and name, DejaVu Sans Bold for burned captions and thumbnail, DejaVu Sans Mono
Bold for the role line. A missing font file aborts with a clear message;
nothing substitutes silently. `encerramento.py` takes its font from config
rather than a module-level literal.

Vendoring Poppins does not preserve the measured layout, it swaps Avenir Next's
metrics for Poppins'. Measured, with the 96-character reference quote at
`POST_LARGURA_UTIL = 1800`:

| Font | @160 | @150 | @140 |
|---|---|---|---|
| Poppins SemiBold | 6 lines | 5 lines | 5 lines |
| Montserrat SemiBold | 6 lines | 5 lines | — |
| DejaVu Sans Bold | 6 lines | 6 lines | 5 lines |

Both fonts `config.py`'s comment names overflow to 6 lines at the configured
size, and a 6th line crosses the rule at y=2242 — which is precisely what
`test_citacao_nao_invade_o_filete` exists to forbid. The comment was
aspirational: the layout was tuned to Avenir Next Demi Bold, which is narrower
and macOS-only.

Decision: keep Poppins SemiBold and lower `POST_CIT_SIZE` from 160 to 150. That
holds the quote at 5 lines with 83px of headroom on the tightest line and costs
no quote capacity. The alternatives were measured and rejected — staying at 160
caps the quote at 89 characters (−7), and DejaVu Sans Bold at 140 leaves only
20px of headroom, so a quote containing one long word overflows.

`POST_CIT_PASSO`, `POST_CIT_ALTURA` and `POST_FILETE_Y` are unaffected: they are
slot geometry, not glyph metrics, and `test_citacao_nao_invade_o_filete` is pure
arithmetic over them.

The expected line split and the skip guard in
`test_quebra_do_design_com_a_fonte_do_design` are re-derived from this
measurement, and the guard asserts Poppins SemiBold instead of skipping.

Making the layout font-relative (measure and reflow instead of hardcoding
`POST_CIT_MAX_LINHAS = 5`) is deliberately deferred to Phase 2, where fonts
become part of `channel.toml`.

### `scripts/youtube_auth.py`

README and `.env.example` both instruct running this file; it does not exist,
and it is the only documented route to `YT_REFRESH_TOKEN`. Installed-app OAuth2
via `google_auth_oauthlib.flow.InstalledAppFlow`, scope
`https://www.googleapis.com/auth/youtube.upload`, with `access_type=offline`
and `prompt=consent` — without both, Google returns no refresh token.

### Documentation

README corrections: the Personalizar table (now also fonts), and a note that
the codebase is still Portuguese with English planned.

The README's "São 377 testes" is **correct** — verified 377 collected with
dependencies installed. An earlier reading of 334 was an artifact of running
without a venv, where four test modules failed to import and contributed no
tests. The count still needs updating at the end of Phase 0 because Task 4 and
Task 7 each add a test module, not because it was ever wrong.

## Done criteria

- venv created, `requirements.txt` installed, full suite green on Arch.
  Measured baseline in the venv: `Ran 377 tests — FAILED (failures=1,
  errors=15, skipped=1)`. All 15 errors and the 1 failure are the macOS font
  defect; the 1 skip is the Avenir Next guard. (Without the venv the suite
  reports 334 tests and 19 errors — four modules fail to import and their
  tests are never collected. That reading is an artifact, not a baseline.)
- These return nothing over `talaria/`, `tests/`, `run.py`, `README.md` and
  `prompts/` (never over `docs/`, which quotes the removed strings as the
  record of what was removed, nor `.venv/`):
  - `grep -rnE '\bEP[0-9]+\b|\bAP-[0-9]+\b|\bCA-[0-9]+\b'` — **case-sensitive
    on purpose.** The uppercase form was the originating project's episode and
    checklist label; the lowercase `ep1`/`ep2`/`ep8` that remain are generic
    project-directory slugs in CLI examples and a path test, and renaming them
    would buy nothing. Case is what separates the two.
  - `grep -rniE 'nvshorts|next.?video.?shorts|next.?squad|nextsquad|norvik|norvic|norvyk|norvyc|ilusen|eosen|yusen|gon[cç]alo|bauru|sandu[ií]che|renata|silveira|gustavo|daniel|interior'`
    — must match inside identifiers, not just strings and comments: an earlier,
    narrower version of this grep passed while two test-method names and a
    caption fixture still carried the old city name.

    The `next.?video.?shorts` and `next.?squad` alternatives matter on their
    own. The rename task searched only for the package identifier `nvshorts`
    and its uppercase env-var form, so the originating project's hyphenated
    human-readable name survived the rename and all four de-branding rounds in
    three places — including `run.py`'s `argparse` description, which printed
    it to anyone running `--help`. A project's own display name is not
    necessarily spelled the way its import path is.

    Two known false positives to keep: `talaria/config.py` names the font
    "Avenir Next Demi Bold" (load-bearing — it is why `POST_CIT_SIZE` is 150),
    and `talaria/vtt_parse.py` uses the `next()` builtin.
  - `grep -rniE '(d[ae]|desta) casa\b'`. A bare `casa` grep can never come
    clean — it is also an ordinary verb and a legitimate data value — and is
    not a criterion.
  - No real URL or media ID. This one needs to be runnable, not prose — the
    CLI help in `run.py` carried a genuine 11-character YouTube video ID
    through two de-branding rounds precisely because this criterion had no
    command behind it:

    ```bash
    grep -rnoE 'https?://[^ "'"'"')]+' --include='*.py' --include='*.md' \
      talaria/ tests/ run.py README.md prompts/ \
      | grep -viE '\.example\b|googleapis|google\.com|github|python\.org|example\.com|exemplo|localhost|cloudflarestorage|myaccount\.google|graph\.facebook|graph\.instagram|youtube\.com/shorts|s3\.amazonaws|youtu\.be/(XYZ|VIDEO_ID)|linkedin\.com/in/x|https://x|assinada|instagr\.am/p/x|https://(yt|ig|a|b)[/.]'
    ```

    Anything it prints is either a new placeholder to add to the allow-list or
    a real leftover. Judge each one; do not widen the allow-list to silence a
    hit without reading it.
- Repository pushed private, directory renamed.

## Out of scope for Phase 0

Translation, the channel profile, the publisher interface, TikTok, and the
Claude API integration. Phase 0 changes no render output except where the font
fix corrects a crash.

## Risks

- Vendored fonts add ~1.2MB to the repository (DejaVu Sans Bold 709KB, DejaVu
  Sans Mono Bold 334KB, Poppins SemiBold ~150KB). Accepted: it is the only
  option that makes rendered output reproducible across machines, which matters
  because the text is burned into the video and cannot be corrected after
  upload.
- Poppins must be fetched from Google Fonts at implementation time; DejaVu and
  its LICENSE are already on this machine under `/usr/share/fonts/TTF/` and
  `/usr/share/licenses/ttf-dejavu/`.
- The de-branding pass edits comments across 30 files. The test suite does not
  cover comments, so review is the only check. Keeping it in its own commits is
  what makes that review possible.


## Verification lessons for Phases 1-4

Phase 0 needed four fix rounds on the de-branding task and a further wave after
the whole-branch review. Not one of those rounds was caused by faulty
execution: every one closed a hole in this document's own acceptance criteria.
The criteria were thorough about the categories already imagined and blind to
the rest. Recorded here because the later phases touch the same files.

- **A grep that returns nothing proves only that it ran.** Each round's
  verification was accurate and useless in equal measure.
- **Identifiers are not the only spelling of a name.** The rename searched
  `nvshorts` and `NVSHORTS` and came back clean while the package still
  introduced itself as "Next-Video-Shorts" in three docstrings and an
  `argparse` description that printed on `--help`.
- **A pattern has a prose form as well as a code form.** The criteria matched
  `AP-\d+` and `CA-\d+` and never `seção N`, `ver spec`, `ver relato no
  commit`, or `corte1` inside a sentence. Twenty-three citations pointed at
  prompt sections that do not exist in the shipped skeletons; two reconstructed
  the withheld prompt's editorial rules verbatim.
- **Test data carries brand.** The company name was the fixture company across
  12 test files, and a regional nickname for one startup belt sat in a slug
  assertion. Nothing in the first criteria looked at fixtures.
- **A criterion with no command behind it is a wish.** The URL criterion was
  prose for two rounds, and a real 11-character YouTube video ID sat in
  `run.py`'s CLI help the whole time.
- **Substituting a value can silently disarm the test that guarded it.**
  `nossa` was a genuine near-miss for `Norvik`'s phonetic pattern and fails at
  the first character against `Zarvik`'s, so the assertion passed for any
  input. Replacing a fixture means re-deriving what its tests prove, not just
  confirming they still pass.
- **A comment can become false without being touched.** Four comments
  described a template that no longer ships; one docstring asserted a
  concatenation strategy the code documents as broken, in the same call path.

The general form: verify the *property*, not the spelling you happen to have
thought of, and prefer a criterion that fails loudly over one that comes back
empty.
