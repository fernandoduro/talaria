# Talaria Phase 1 — full English translation

Date: 2026-09-21
Status: design approved. Phase 0 complete (see
`2026-09-21-phase-0-fork-and-debrand-design.md`).

## Context

Phase 0 left a working, de-branded `talaria` whose code, comments, docstrings,
strings, prompts and on-disk file format are all Portuguese. The decision taken
at the outset was 100% English, for English-language video. Phase 1 executes
that, and must land before Phase 2 so the channel profile is not designed in
one language and translated into another.

Surface: 8,681 lines across 27 modules, 23 test modules, `run.py` and
`scripts/youtube_auth.py`. 388 tests, green.

## Decisions

| Question | Decision |
|---|---|
| Sequencing | A declared old→new rename map applied mechanically, then prose, then strings |
| Proper-noun correction | English equivalence table, same regex machinery |
| Caption cleanup | English fillers and discourse markers; contractions preserved |
| `calendario` | becomes `schedule`, not `calendar` |
| `FUSO_PUBLICACAO` | stays `America/Sao_Paulo` — the operator's timezone, not the content's language |
| Episode schema | untouched; Phase 2 owns it |

## The rename map

The map is written first, as a reviewable data file, and applied
mechanically. This is the phase's main control: a declared rename can be
checked as a list of decisions, where a 4,000-line diff cannot, and Phase 0
demonstrated repeatedly that improvised consistency is where things slip.

Four kinds of entry, roughly 145 in total:

- **Functions, classes, parameters and locals.** About 60 of the 183
  top-level definitions, plus — added after the fact — Portuguese parameters
  and locals. The first draft of this map enumerated only top-level names and
  constants, which left `fix_proper_nouns(txt, nomes)` and
  `clean_quote(texto, nomes)` with Portuguese parameters that are settable by
  keyword and therefore part of the API, and roughly 30 Portuguese locals with
  no row at all. When extending this map, enumerate `def` signatures and
  assignment targets, not just top-level names.
  `corrige_nomes` → `fix_proper_nouns`, `cauda_vaza` → `tail_leaks`,
  `valida_corte` → `validate_clip`, `sugere_frames` → `suggest_frames`.
- **Constants** — about 45. `CORTE_MIN_S` → `CLIP_MIN_S`,
  `FALA_CONVIDADO_MIN` → `GUEST_SPEECH_MIN`, `POST_CIT_*` → `POST_QUOTE_*`,
  `CAMPOS_OBRIGATORIOS` → `REQUIRED_FIELDS`.
- **Modules** — 7 of 27: `episodio` → `episode`, `curadoria` → `curation`,
  `ambiente` → `environment`, `publicado` → `published`, `encerramento` →
  `end_card`, `textos` → `texts`, `calendario` → `schedule`. The other 20
  already have English names.
- **On-disk format** — 4 directory names (`decisoes/` → `decisions/`,
  `publicar/` → `publish/`, `fonte/` → `source/`, `briefs/` unchanged) and
  about 30 JSON keys (`empresa` → `company`, `convidados` → `guests`,
  `temporada` → `season`, `aprovados` → `approved`, `rejeitados` →
  `rejected`, `motivo` → `reason`, `plataforma` → `platform`).

`projetos/` does not exist on disk, so there is no data to migrate and no
backwards compatibility to preserve.

**Keys that must NOT be renamed** because they are set by external APIs, not by
this code: `snippet`, `title`, `description`, `id`, `status`, `permalink`,
`message`, `error`. Renaming any of them breaks a real request or response.

### Two naming decisions with reasons

`calendario` becomes `schedule` rather than the literal `calendar`. A package
module named `calendar` shares its name with a stdlib module; Python 3's
absolute imports mean it would not actually break, but a reader cannot tell
which `import calendar` resolves to without checking. `schedule` also matches
the CLI verb (`agenda` → `schedule`). The same reasoning keeps `textos` →
`texts` rather than `copy`.

`FUSO_PUBLICACAO` keeps the value `America/Sao_Paulo`. It encodes where the
operator publishes from, which English-language video does not change. Phase 2
makes it configurable.

## Three passes

Each pass ends with the suite back at 388 green and is its own commit series.

1. **The map.** Identifiers, module filenames, CLI verbs (`curar` → `curate`,
   `agenda` → `schedule`), JSON keys, on-disk directory names. Mechanical. A
   missed `mock.patch` string target or JSON key fails loudly rather than
   silently — the same property that made Phase 0's rename safe.
2. **Prose.** Comments and docstrings. No behavioural risk; the largest
   volume.
3. **Strings.** User-facing messages, `prompts/*.md` including the
   `{{METADADOS}}` → `{{METADATA}}` placeholders, `README.md`, and the neutral
   placeholders: `NOME_PROGRAMA` → `"MY PODCAST"`, `CARD_ARROBA` →
   `"@yourhandle"`, `hashtags.FIXAS` → English tags, `PREFIXO_EPISODIO` →
   `"▶ Full episode: "`. Also `WHISPER_LANG = "en"`.

The em-dash check in `caption.py` stays. It flags a caption containing an
em-dash because that reads as machine-written text — as true in English as in
Portuguese, arguably more so. Only its message is translated.

## Scope is not the same as context

The rename map's `scope` column separates words with one sense from words with
two. It does **not** separate an identifier from the same word appearing inside
a Portuguese sentence, and that distinction turned out to matter: a mechanical
substitution of a single-sense word inside prose produces
`"'{line}' nao fits na largura do card"`. Roughly 23 such occurrences were
reverted during Task 3 and left for the prose and string passes, which
translate the whole sentence rather than one word of it.

One of those substitutions was a functional bug, not merely ugly: the
first-person marker regex had `"minha empresa"` rewritten to `"minha company"`,
which silently breaks speaker-attribution detection. A word-boundary
substitution is safe for identifiers and unsafe for regex alternations and
prose, and nothing in the map's shape expressed that.

Consequence for verification: between the map pass and the string pass, a
"every map entry is gone" check is expected to report survivors. They are only
all gone once the prose and string passes have run.

## The five language-bound rewrites

These are not translations. All five are rewrites whose properties must be
re-derived by measurement, because a replacement that reads plausibly can
silently stop working — Phase 0 lost a near-miss test exactly this way, when
`nossa` was replaced by a word that failed the pattern at its first character
instead of its fourth.

An earlier draft of this spec named only the first two. The other three were
found when a blind substitution corrupted one of them, which is its own lesson:
**grep for `re.compile` before assuming you have found every piece of
language-specific logic.** Timestamp and punctuation patterns
(`RE_TS`, `RE_CUE`, `RE_INLINE`, `RE_TS_LINE`, `RE_SENTENCE_END`) are
language-neutral and need no rewrite.

### `utils.corrige_nomes` → `fix_proper_nouns`

The Portuguese table maps vowel classes (`o/u/a`, `i/y/e`), `s/z`, `c/k/q`, and
inserts an optional `l` after the first character. English equivalents:
`c/k/ck/q`, `f/ph`, `s/z`, `i/y`, `ee/ea/ie`, `ou/ow`, plus silent `e` and `h`.

Requirements the replacement must still satisfy, each already covered by a
test: a mis-heard variant round-trips to the official spelling; a word boundary
is respected (`Zarvikzinho` keeps its suffix — the English fixture needs an
equivalent case); a lowercase occurrence is capitalised; and a real dictionary
word that nearly matches is left alone. That last one is the near-miss test,
and its fixture pair must be re-derived: pick the name first, then find a real
English word that the new pattern matches partway and rejects, and record where
it diverges.

### `utils.clean_caption`

Portuguese behaviour: strip fillers `eh/ah/uhum/hã`, remove `né` tag questions
at end and mid-sentence, expand contractions (`tá` → `está`, `pra`/`pro` →
`para`) behind a guard so `pro labore`, `pro rata`, `pro forma`, `pro bono` and
`pro indiviso` survive.

English behaviour:

- Strip `uh`, `um`, `er`, `ah`, `hmm`.
- Strip `you know`, `I mean`, and `like` **when used as filler**. `like` is the
  hard case — it is also an ordinary verb and preposition, so the pattern must
  be bounded (comma-delimited or sentence-initial) and its false-positive
  behaviour tested, not assumed.
- Expand only spoken-only forms: `gonna` → `going to`, `wanna` → `want to`,
  `gotta` → `got to`, `kinda` → `kind of`.
- **Leave real contractions alone.** `don't`, `it's`, `we're` are correct
  written English; expanding them would make a burned-in caption read worse,
  which is the opposite of this function's purpose. This is the one place the
  English behaviour deliberately diverges from the Portuguese rather than
  mirroring it.
- Keep the word-repetition dedup unchanged — it is language-neutral.
- The Latin-phrase guard and its tests are deleted. English has no `pro`
  collision, so the guard would protect against nothing.

### `curation.RE_FIRST_PERSON`

Portuguese: `a gente|nosso|nossa|nossos|nossas|eu vim|meu sócio|minha empresa`.
It gates `attribution_trustworthy`, which warns the operator when a clip's
speaker labels look wrong — the host talking about "our company" is a signal
the transcript attributed guest speech to the host.

English needs the equivalent first-person-plural and possessive markers: `we`,
`our`, `us`, `my company`, `my co-founder`, `I joined`, `I started`. `we` and
`our` are far more frequent in English than `a gente` is in Portuguese, so the
threshold this feeds (`SUSPECT_ATTRIBUTION_THRESHOLD`) may need re-deriving
against a real transcript rather than carried over. Say so if it does; do not
silently keep a number that was tuned for a different base rate.

### `curation.RE_HEDGED_NUMBER`

Portuguese: `uns|umas|aproximadamente|cerca de|por volta de|acho que|se (eu)
não me engano|mais ou menos`, followed within 40 characters by a digit. It
warns that a clip states an approximate figure as if it were exact.

English: `about|around|approximately|roughly|some|maybe|I think|if I
remember|more or less|or so|give or take`, same digit proximity.

This is the regex behind the near-miss pair the classification artifact
identified as this codebase's own `nossa`: `test_texto_sem_numero_nao_alerta`
asserts that a hedging marker with **no** number does not warn. Its English
fixture must still contain a marker the new pattern recognises, or it passes
for the trivial reason and stops testing anything.

### `utils.RE_SOUND_TAG`

Already partly bilingual — `music|laughter|applause` sit alongside the
Portuguese terms. Drop the Portuguese alternatives and complete the English
set: `music`, `laughter`, `applause`, `noise`, `silence`, `inaudible`,
`crosstalk`. The cheapest of the five.

Note that `tests/test_txt_parse.py:61` asserts sound-tag stripping against a
fixture containing no sound tag, so it cannot fail today. Phase 0's spec records
it as carried forward; do not translate it into a test that looks like it proves
something.

## Test integrity

Renaming an identifier or a JSON key on both sides of an assertion is safe:
the test proves the same thing under a new name. Translating a **value** on
both sides is not — it stays green while no longer proving anything.

Therefore: every test whose expected *content* changes must have its property
re-verified explicitly, and the implementation plan must **enumerate those
tests by name** rather than leaving the distinction to judgement mid-edit.
There are roughly 40: every assertion over caption text, hashtag output, error
message text, and the phonetic variants.

For each, the plan states what the test proves and how the new expectation was
derived. A test whose expectation was obtained by translating the old one is
not acceptable evidence.

## Done criteria

Phase 0's criteria failed four times by checking the categories already
imagined. These are written to detect the property — "no Portuguese remains" —
rather than a list of known Portuguese words.

- `Ran 388 tests` / `OK`, from a rebuilt venv.
- **No accented characters in any source file.** Portuguese cannot be written
  without them, so this catches prose, strings and identifiers in one check
  and needs no vocabulary list:
  ```bash
  grep -rnP '[\x{00C0}-\x{00FF}]' --include='*.py' --include='*.md' \
    talaria/ tests/ run.py scripts/ prompts/ README.md
  ```
  Expected empty. `docs/` is excluded: it records the Portuguese originals.
- **No Portuguese function words**, which catches unaccented prose the first
  check cannot:
  ```bash
  grep -rniE '\b(que|nao|para|uma|dos|das|pelo|pela|sem|mais|ja|ao|aos|pra|nem|onde|quando|porque|entao|isso|este|esta|aquele|muito|entre|cada|todo|toda|seu|sua|dele|dela|foi|ser|ter|fazer|pode|deve|tem|sao|estao|com)\b' \
    --include='*.py' --include='*.md' talaria/ tests/ run.py scripts/ prompts/ README.md
  ```
  This pattern was tested against the current tree before being written here.
  Two deliberate exclusions: `no` and `so` are ordinary English words and were
  removed, or the criterion would never come clean. `com` is kept because
  Portuguese "com" is frequent, at the cost of matching every `.com` domain —
  expect roughly a dozen such hits and confirm each is a URL. Anything else it
  prints is untranslated prose.

  Do not widen the allow-list to silence a hit without reading it; that is how
  Phase 0's URL criterion stayed quiet for two rounds.
- No Portuguese module, function, constant, CLI verb, JSON key or on-disk
  directory name survives — verified against the rename map, every entry
  checked as applied.
- `python run.py --help` is entirely English.
- The two rewritten functions' properties are re-derived and recorded, not
  inherited.

## Out of scope

Phase 2 owns the episode schema (`CAMPOS_OBRIGATORIOS`, `"uf": "SP"`, the
`T[N]E[NN]` code), the channel profile, and making fonts, palette and timezone
configurable. Phase 3 owns the publisher interface and TikTok. Phase 4 owns the
Claude API integration.

The issues Phase 0 recorded as carried forward stay carried forward: the
`POST_FILETE_Y` mismatch against the shipped template, the closing-card cache
ignoring the font, and the ragged comment wrapping — which Phase 1's prose pass
will incidentally fix, since it rewrites those comments anyway.

## Risks

- **A green suite is weaker evidence in this phase than in Phase 0.** Most of
  the diff is prose the tests cannot police, and the parts they do police can
  be disarmed symmetrically. The enumerated-test requirement above is the
  mitigation; it is the one part of this spec that cannot be skipped.
- **`like` as a filler is genuinely ambiguous.** An over-broad pattern will
  mangle sentences where `like` is a verb. If a bounded pattern cannot be made
  safe, dropping `like` from the filler list is the correct outcome, not a
  looser pattern.
- **The map's size invites skimming.** 145 entries reviewed as a list is the
  point; reviewing it as a diff defeats the approach.
