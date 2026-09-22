# Talaria Phase 1 — English Translation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Translate `talaria` to 100% English — identifiers, module names, CLI verbs, JSON keys, on-disk directory names, comments, docstrings, user-facing strings, prompts and README — and replace the two components whose logic is Portuguese-specific rather than merely Portuguese-named.

**Architecture:** Two analysis artifacts are produced and gated before any code changes: a declared rename map, and a classification of every assertion site whose expected content could change meaning. Then three mechanical passes (map, prose, strings) with two rewrites in between. The suite returns to 388 green after every task.

**Tech Stack:** Python 3.12 (3.9+ floor), stdlib `unittest`, Pillow, ffmpeg/ffprobe, `google-auth-oauthlib`, `google-api-python-client`, `boto3`, `requests`, `yt-dlp`, `faster-whisper`.

## Global Constraints

- Spec: `docs/specs/2026-09-21-phase-1-english-translation-design.md`. Read it before starting.
- Phase 0 spec, for the verification lessons that shaped this plan: `docs/specs/2026-09-21-phase-0-fork-and-debrand-design.md`, section `## Verification lessons for Phases 1-4`.
- Input artifact, already committed: `docs/plans/phase-1-inputs/content-assertion-sites.md` — 94 assertion sites across 75 tests, plus 13 width-dependent sites added in Task 2's fix round. See that file's `## Known gap in this enumeration` for why the original scan was incomplete.
- Run tests as `.venv/bin/python -m unittest discover -s tests`. Never pytest. Never bare `python`.
- **Baseline: `Ran 388 tests` / `OK`.** Every task ends here or better. A changed count is only acceptable where a task explicitly adds or removes a test, and it must say so.
- Work on `main`, directly. The human has consented; do not branch or create a worktree.
- Never squash. Never force-push.
- Every commit message ends with exactly these two lines:
  `Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_01FYUKtLNnaBxLFdweWDYo4g`
- Do not write list items as `#1`/`#2` — GitHub autolinks `#N` to unrelated issues. Use `1.` or bullets.
- Comments earn their place only by stating a constraint the code cannot show. Translation is not licence to expand: a translated comment should be about as long as the original, and a comment that was noise in Portuguese is noise in English — delete it rather than translating it.
- **Do not rename these JSON keys.** They are set by external APIs: `snippet`, `title`, `description`, `id`, `status`, `permalink`, `message`, `error`. Renaming any breaks a real request or response.
- Out of scope, owned by Phase 2: the episode schema (`CAMPOS_OBRIGATORIOS`, `"uf": "SP"`, the `T[N]E[NN]` code), the channel profile, making fonts/palette/timezone configurable.
- `FUSO_PUBLICACAO` keeps the value `America/Sao_Paulo`. Only its name changes.
- Never edit anything under `docs/specs/` — those record the Portuguese originals deliberately.

---

### Task 1: Build the rename map

**Files:**
- Create: `docs/plans/phase-1-inputs/rename-map.tsv`
- Modify: none
- Test: none — this task produces a reviewable document, not code

**Interfaces:**
- Consumes: the current tree.
- Produces: `rename-map.tsv`, five tab-separated columns: `kind`, `old`, `new`, `scope`, `note`. `scope` is `global` (every occurrence means the same thing, safe to substitute tree-wide) or `manual` (the word carries more than one sense, or the rename is valid only for one kind, module or call site). Task 3 substitutes the `global` entries mechanically and applies the `manual` ones site by site. Every later task refers to symbols by their NEW name.

- [ ] **Step 1: Enumerate every candidate**

```bash
cd /data/Code/talaria
grep -rhoE '^(def|class) [a-zA-Z_][a-zA-Z0-9_]*' talaria/*.py run.py scripts/*.py | sed 's/^\(def\|class\) //' | sort -u
grep -rhoE '^[A-Z][A-Z0-9_]{2,}' talaria/*.py run.py scripts/*.py | sort -u
ls talaria/*.py | xargs -n1 basename
grep -rhoE '"[a-z_áéíóúâêôãõç]+"\s*:' talaria/*.py | sort -u
grep -nE '^[A-Z_]+ = "' talaria/layout.py
```

Expect 184 definitions, 130 constants, 27 modules. Many are already English — `acquire`, `build`, `clean_caption`, `detect_source`, `extract_frame`, `group_words_into_segments`, `render_cut`, `wrap_by_pixels` and others need no entry.

- [ ] **Step 2: Name each Portuguese symbol by reading what it does**

Open each definition before naming it. Do not translate the Portuguese word literally — name the thing the function actually does. Two worked examples from this codebase:

- `cauda_vaza` is literally "tail leaks". Read it: it returns True when a clip's final words are still at high volume, meaning the cut landed mid-word. `tail_leaks` is a fair name; `clips_mid_word` would be better. Either is acceptable; `leaky_tail` is not, because it reads as a property rather than a test.
- `vale_antes` is literally "valley before". It finds the nearest audio-envelope valley preceding a timestamp, used to move a cut off a word boundary. `valley_before` is correct here — the literal translation happens to be the right name.

Where the literal translation is wrong, the map records the better name. Where it is right, say so; do not invent novelty.

- [ ] **Step 3: Apply these naming rules**

- **Portuguese-named modules** (7 of 27): `episodio`→`episode`, `curadoria`→`curation`, `ambiente`→`environment`, `publicado`→`published`, `encerramento`→`end_card`, `textos`→`texts`, `calendario`→`schedule`.
  `calendario` becomes `schedule`, NOT `calendar`: a package module sharing a stdlib module's name leaves a reader unable to tell which `import calendar` resolves to. Same reason `textos`→`texts`, not `copy`.
- **CLI verbs**: `curar`→`curate`, `agenda`→`schedule`. The other nine are already English. `cmd_curar`→`cmd_curate`, `cmd_agenda`→`cmd_schedule`.
- **On-disk directories**: `decisoes`→`decisions`, `publicar`→`publish`, `fonte`→`source`. `briefs` is already English. `youtube_shorts`, `instagram_reels`, `instagram_posts` unchanged.
- **Collisions are the hazard.** Several Portuguese names would collide with an existing English name if translated literally: `monta`/`montar` would both become `build`, which `hashtags.build` already occupies; `sobe` would become `upload`, which `publish_youtube.upload` already occupies; `carrega` would become `load`, which `episodio.load` already occupies; `segmentos_no_corte` would become `segments_in_cut`, which already exists as a private `_segments_in_cut`. A collision inside one module is an error; across modules it is legal but confusing. **For every proposed name, grep the whole tree for it before writing the entry**, and record a distinct name where it collides:

```bash
grep -rnE "\b<proposed_name>\b" --include='*.py' talaria/ tests/ run.py scripts/
```

Add a fourth column `note` for any entry where you chose a non-literal name, saying why in under ten words.

- [ ] **Step 4: Write the file**

Tab-separated, one entry per line, sorted by kind then old name. Header row: `kind	old	new	note`. Valid `kind` values: `module`, `function`, `constant`, `json_key`, `dir`, `cli_verb`, `cli_flag`.

- [ ] **Step 6: Verify the map is complete and self-consistent**

```bash
cd /data/Code/talaria
awk -F'\t' 'NR>1{print $3}' docs/plans/phase-1-inputs/rename-map.tsv | sort | uniq -d
awk -F'\t' 'NR>1{print $2}' docs/plans/phase-1-inputs/rename-map.tsv | sort | uniq -d
awk -F'\t' 'NR>1 && $3 ~ /[^a-zA-Z0-9_]/ {print "non-identifier new name: " $0}' docs/plans/phase-1-inputs/rename-map.tsv
grep -cP '[\x{00C0}-\x{00FF}]' <(awk -F'\t' 'NR>1{print $3}' docs/plans/phase-1-inputs/rename-map.tsv) || echo "no accents in new names: OK"
```

The first two must print nothing: a duplicated `new` name means two symbols map to one, a duplicated `old` means two entries disagree. The third must print nothing. The fourth confirms no new name carries an accent.

- [ ] **Step 7: Commit the map, do not apply it**

```bash
cd /data/Code/talaria
git add docs/plans/phase-1-inputs/rename-map.tsv
git commit -m "docs: declare the Phase 1 rename map

Every identifier, module, CLI verb, JSON key and on-disk directory name
that changes, as data rather than as a diff. Reviewing 145 decisions as a
list is the point; reviewing them inside a 4,000-line diff is not."
```

Report the entry count per `kind`, and every entry where you chose a non-literal name.

---

### Task 2: Classify the content-assertion sites

**Files:**
- Create: `docs/plans/phase-1-inputs/assertion-classification.tsv`
- Modify: none
- Test: none — a reviewable document

**Interfaces:**
- Consumes: `docs/plans/phase-1-inputs/content-assertion-sites.md` (94 sites, 75 tests, plus 13 width-dependent additions) and the rename map from Task 1.
- Produces: `assertion-classification.tsv` — columns `file`, `line`, `test`, `class`, `proves`, `derivation`. Tasks 4, 5, 6 and 8 consult it for every site they touch.

This is the safety-critical artifact of the phase. Phase 0 lost a test to a symmetric edit: `nossa` was a genuine near-miss for the old pattern and fails the new one at its first character, so the assertion passed for any input and proved nothing. That edit looked correct in review.

- [ ] **Step 1: Read the input and the classification rule**

`docs/plans/phase-1-inputs/content-assertion-sites.md` lists all 94 sites and states the rule. The test is: **does the assertion compare against text this codebase generates for a human to read?**

- `A` — the value is a fixture slug, a filename derived from one, a placeholder token, a JSON key, or a literal the test itself supplied as input. Renaming both sides preserves what the test proves.
- `B` — the value is output this code produces: a cleaned caption, an error message's wording, a readable report's prose, a hashtag string, a thumbnail line.

- [ ] **Step 2: Classify every site, opening each one**

Do not classify from the one-line excerpt in the input file. Open the test, and open the code under test, and decide from what the assertion actually compares.

Worked examples:

- `tests/test_caption.py::test_troca_extensao_da_peca` asserting `"corte1_short.txt"` is **A**. The value is a filename built from a fixture slug the test supplied; renaming `corte`→`clip` in the fixture changes both sides and the test still proves the extension swap.
- `tests/test_caption.py::test_numero_e_rejeitado_citando_o_campo_e_a_peca` asserting `assertIn("legenda", msg)` is **B**. It pins a word in a user-facing error message. The English message must be checked to genuinely contain the chosen word — and the chosen word must be unique to that message, or the assertion stops discriminating. Phase 0 shipped exactly this defect with `assertIn("Console", ...)`, which also matched a sibling message.
- `tests/test_utils.py` assertions over `clean_caption` output are **B**, all of them. That function is being rewritten in Task 5, so its expectations cannot be translated at all — they must come from running the new implementation.

- [ ] **Step 3: For every `B` site, fill `proves` and leave `derivation` empty**

`proves` is one sentence: what property this assertion establishes. Write it now, while reading the Portuguese, because after translation the original intent is harder to recover. `derivation` is filled in later, by whichever task changes the site, with how the new expectation was obtained.

- [ ] **Step 4: Verify the classification covers every input site**

```bash
cd /data/Code/talaria
awk -F'\t' 'NR>1' docs/plans/phase-1-inputs/assertion-classification.tsv | wc -l
grep -c '^  - L' docs/plans/phase-1-inputs/content-assertion-sites.md
awk -F'\t' 'NR>1{print $4}' docs/plans/phase-1-inputs/assertion-classification.tsv | sort | uniq -c
awk -F'\t' 'NR>1 && $4=="B" && $5=="" {print "B site with no proves: " $1":"$2}' docs/plans/phase-1-inputs/assertion-classification.tsv
```

The first two counts must match at 94. The third reports the A/B split. The fourth must print nothing.

- [ ] **Step 5: Commit**

```bash
cd /data/Code/talaria
git add docs/plans/phase-1-inputs/assertion-classification.tsv
git commit -m "docs: classify the Phase 1 assertion sites A/B

94 sites split into symmetric-safe renames and expectations that must be
re-derived by running the new code. The B sites carry a one-sentence
statement of what each proves, recorded while the Portuguese is still
readable."
```

Report the A/B split and any site you found genuinely ambiguous.

---

### Task 3: Apply the rename map

**Files:**
- Modify: all 27 modules, 23 test modules, `run.py`, `scripts/youtube_auth.py`
- Modify: `talaria/layout.py` (on-disk directory constants)
- Test: whole suite

**Interfaces:**
- Consumes: `rename-map.tsv` from Task 1.
- Produces: the English identifier surface. Every later task uses the new names.

- [ ] **Step 1: Count references before touching anything**

```bash
cd /data/Code/talaria
awk -F'\t' 'NR>1{print $2}' docs/plans/phase-1-inputs/rename-map.tsv | while read old; do
  printf "%-34s %s\n" "$old" "$(grep -rowE "\b$old\b" --include='*.py' talaria/ tests/ run.py scripts/ | wc -l)"
done | sort -k2 -rn | head -25
grep -rohE 'mock\.patch\("talaria\.[a-z_.]+' tests/*.py | sort -u | wc -l
```

Record the `mock.patch` count. Those are string literals naming modules and attributes; they are invisible to an identifier grep and to any IDE rename. Phase 0's rename had 24 of them and they were the single highest-risk item.

- [ ] **Step 2: Rename the module files with git**

```bash
cd /data/Code/talaria
git mv talaria/episodio.py talaria/episode.py
git mv talaria/curadoria.py talaria/curation.py
git mv talaria/ambiente.py talaria/environment.py
git mv talaria/publicado.py talaria/published.py
git mv talaria/encerramento.py talaria/end_card.py
git mv talaria/textos.py talaria/texts.py
git mv talaria/calendario.py talaria/schedule.py
for f in tests/test_episodio.py tests/test_curadoria.py tests/test_ambiente.py tests/test_publicado.py tests/test_encerramento.py tests/test_textos.py tests/test_calendario.py; do
  git mv "$f" "$(echo $f | sed 's/episodio/episode/; s/curadoria/curation/; s/ambiente/environment/; s/publicado/published/; s/encerramento/end_card/; s/textos/texts/; s/calendario/schedule/')"
done
git status --short
```

`git mv` so history follows each file, as in Phase 0.

- [ ] **Step 3a: Apply the `global` entries mechanically, longest `old` first**

Order matters: renaming `corte` before `corte_min_s` would corrupt the longer name. Sort by descending length of `old`. **Only `scope == global` entries go through this loop.**

```bash
cd /data/Code/talaria
awk -F'\t' 'NR>1 && $4=="global"{print length($2)"\t"$2"\t"$3}' docs/plans/phase-1-inputs/rename-map.tsv \
  | sort -rn | cut -f2,3 | while IFS=$'\t' read old new; do
  grep -rlZ --include='*.py' -E "\b$old\b" talaria/ tests/ run.py scripts/ \
    | xargs -0 -r sed -i "s/\b$old\b/$new/g"
done
```

- [ ] **Step 3b: Apply the `manual` entries one site at a time**

These exist because the Portuguese word carries more than one sense, and a tree-wide substitution corrupts the other one. Four verified examples, which are why this step exists:

- `data` → `date` is correct for the Portuguese date key, and WRONG at `talaria/textos.py`'s `def save(project_dir, data: dict)`, where `data` is the English word. Global substitution produces `date: dict` and `json.dump(date, f)`.
- `fonte` → `source` is correct for the `fonte/` directory, and WRONG in `post_instagram`, where *fonte* means **font**.
- `caminho` → its mapped name applies to one function; the other ~80 occurrences are ordinary local path variables.
- `meta` → `target` is correct for the goal count, and WRONG for the `"meta"` string inside the common-words list, where it is a company name that happens to be a common word.

For each `manual` entry: list its occurrences, read each one, and change only those matching the sense the `note` column describes.

```bash
cd /data/Code/talaria
awk -F'\t' 'NR>1 && $4=="manual"{print $2"\t"$3"\t"$5}' docs/plans/phase-1-inputs/rename-map.tsv
# then, per entry:
grep -rnE "\b<old>\b" --include='*.py' talaria/ tests/ run.py scripts/
```

Record, per `manual` entry, how many occurrences you changed and how many you deliberately left. A `manual` entry where you changed every occurrence was probably mis-scoped — say so rather than assuming the map was wrong.

Word boundaries do more work here than they look like they do, and it is worth knowing exactly what they protect:

- A fixture slug such as `corte1_mar_azul` is **not** matched by `\bcorte\b`, because `e`→`1` is not a word boundary. That is the desired outcome: Phase 0 ruled those slugs out of scope, and they stay untouched for free.
- A directory name inside a path string **is** matched — `"decisoes/schedule.json"` hits `\bdecisoes\b`, since `/` is a non-word character. So paths and JSON keys are handled correctly by the same pass.

Verify both after the loop runs:

```bash
grep -rn '"decisions"\|"publish"\|"source"' --include='*.py' talaria/ tests/
grep -rn 'corte1_mar_azul\|corte3_b2b' --include='*.py' tests/
```

The first should show the renamed directory constants. The second must still show the old fixture slugs, unchanged — if they were rewritten, the boundary assumption broke and the substitution was too loose.

- [ ] **Step 4: Verify nothing Portuguese-named survives from the map**

```bash
cd /data/Code/talaria
echo "--- global entries must be fully gone ---"
awk -F'\t' 'NR>1 && $4=="global"{print $2}' docs/plans/phase-1-inputs/rename-map.tsv | while read old; do
  hits=$(grep -rowE "\b$old\b" --include='*.py' talaria/ tests/ run.py scripts/ | wc -l)
  [ "$hits" != "0" ] && echo "SURVIVED: $old ($hits)"
done
echo "--- manual entries: surviving occurrences are expected; confirm each is the other sense ---"
awk -F'\t' 'NR>1 && $4=="manual"{print $2}' docs/plans/phase-1-inputs/rename-map.tsv | while read old; do
  hits=$(grep -rowE "\b$old\b" --include='*.py' talaria/ tests/ run.py scripts/ | wc -l)
  echo "$old: $hits remaining"
done
echo "--- mock.patch targets all point at real modules? ---"
grep -rohE 'mock\.patch\("talaria\.[a-z_]+' tests/*.py | sed 's/.*"talaria\.//' | sort -u | while read m; do
  [ -f "talaria/$m.py" ] || echo "BROKEN patch target: talaria.$m"
done
```

The `mock.patch` check must print nothing. The `global` check is EXPECTED to report survivors — around 23 — because the map's `scope` column separates one-sense words from two-sense words but does not separate an identifier from the same word inside a Portuguese sentence. Substituting one word of a sentence that Tasks 7 and 8 translate wholesale produces `"nao fits na largura"`. Confirm each survivor sits inside prose or a regex alternation, not in an identifier, and leave it. They are gone only after the prose and string passes. The `manual` listing will show remaining occurrences — that is expected, and you confirm each surviving one is genuinely the other sense of the word. A broken `mock.patch` target fails loudly at test time, but this catches it before the suite runs and tells you which one.

- [ ] **Step 5: Run the suite**

Run: `.venv/bin/python -m unittest discover -s tests 2>&1 | tail -3`
Expected: `Ran 388 tests` / `OK`. Identical count. A rename changes no behaviour; a different count or any failure means a symbol was over- or under-substituted. Do not adjust a test to make it pass — find the bad substitution.

- [ ] **Step 6: Check the CLI still works**

```bash
cd /data/Code/talaria
.venv/bin/python run.py --help
```

Expected: subcommands `acquire transcribe prep render thumb ingest brief curate post publish schedule` — `curar` and `agenda` replaced, the other nine unchanged.

- [ ] **Step 8: Commit**

```bash
cd /data/Code/talaria
git add -A
git commit -m "refactor: apply the Phase 1 rename map

Identifiers, module filenames, CLI verbs, JSON keys and on-disk directory
names, from the declared map. No behaviour change: the suite reports the
same 388 tests passing as before."
```

---

### Task 4: Rewrite `fix_proper_nouns` for English

**Files:**
- Modify: `talaria/utils.py` (the equivalence table, the pattern builder, the common-word list)
- Modify: `tests/test_utils.py` (the phonetic tests)
- Modify: `docs/plans/phase-1-inputs/assertion-classification.tsv` (fill `derivation` for the B sites you touch)
- Test: `tests/test_utils.py`, whole suite

**Interfaces:**
- Consumes: the renamed surface from Task 3.
- Produces: `utils.fix_proper_nouns(txt, names)` with English phonetic equivalences. Signature unchanged: takes the caption text and the official spellings from the episode metadata, returns the text with mis-heard variants corrected.

Why this exists: the caption is burned into the video, so a mis-heard company name ships permanently. The Portuguese table mapped vowel classes (`o/u/a`, `i/y/e`), `s/z`, `c/k/q` and an optional inserted `l`.

- [ ] **Step 1: Write the failing tests first**

Replace the Portuguese phonetic tests with English ones. Choose the fixture name and its variants from how English ASR actually errs — consonant clusters and vowel digraphs, not Portuguese vowel classes:

```python
class TestFixProperNouns(unittest.TestCase):
    """The caption is burned into the video: a mis-heard name ships forever."""

    def test_variant_round_trips_to_official_spelling(self):
        for variant in ("Kolbee", "Colby", "Kolby"):
            self.assertEqual(
                utils.fix_proper_nouns(f"we built {variant} in a garage", ["Colbee"]),
                "we built Colbee in a garage")

    def test_word_boundary_is_respected(self):
        self.assertEqual(utils.fix_proper_nouns("Colbeeish", ["Colbee"]), "Colbeeish")

    def test_lowercase_occurrence_is_capitalised(self):
        self.assertEqual(utils.fix_proper_nouns("at colbee today", ["Colbee"]),
                         "at Colbee today")

    def test_near_miss_dictionary_word_is_left_alone(self):
        txt = "the colder months came"
        self.assertEqual(utils.fix_proper_nouns(txt, ["Colbee"]), txt)
```

The last test is the one that matters and the one Phase 0 broke. `colder` must match the pattern *partway* and then diverge — that is what proves the pattern is tight enough to leave real words alone. **Derive it, do not assume it**: build the pattern, print it, and confirm where `colder` diverges. If it fails at the first character the test is worthless, exactly as `nossa` became against `[sz]l?arv…`.

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/bin/python -m unittest tests.test_utils -v 2>&1 | tail -15`
Expected: the four new tests fail — the table is still Portuguese, so `Kolbee`/`Colby` do not match `Colbee`.

- [ ] **Step 3: Replace the equivalence table**

In `talaria/utils.py`, replace the Portuguese classes with English ones:

```python
# Phonetic swaps automatic transcription makes on proper nouns. The same
# company comes back as Colbee, Kolbee, Colby and Kolby -- the c/k and the
# ee/y are the axes that actually vary in English.
_PHONETIC_EQUIV = [
    ("c", "[ck]"),
    ("k", "[ck]"),
    ("q", "[ckq]"),
    ("s", "[sz]"),
    ("z", "[sz]"),
    ("f", "(?:f|ph)"),
    ("i", "[iy]"),
    ("y", "[iy]"),
]
```

`ee`/`ea`/`ie` and `ou`/`ow` are digraphs, not single characters, so they cannot go in a per-character table. Handle them in the pattern builder as a pre-pass over the name, or leave them out — **measure which choice makes the four tests pass without matching a dictionary word**, and record what you chose and why in the report. Leaving them out is an acceptable outcome if including them makes the pattern too loose.

- [ ] **Step 4: Replace the common-word exclusion list**

The Portuguese list held words that are also company names (`matriz`, `praia`, `ponte`). The English equivalent: `apple`, `orange`, `amazon`, `oracle`, `square`, `stripe`, `slack`, `meta`, `shell`, `sun`, `gap`, `target`, `chase`, `visa`, `delta`, `arc`, `bolt`, `lime`. Keep the list short and explicit, and keep the comment's point: guessing "is this a common word?" without a dictionary errs more often than it helps, and a missing entry only loses automatic capitalisation.

- [ ] **Step 5: Run the tests until they pass, then the whole suite**

```bash
cd /data/Code/talaria
.venv/bin/python -m unittest tests.test_utils -v 2>&1 | tail -5
.venv/bin/python -m unittest discover -s tests 2>&1 | tail -3
```
Expected: `tests.test_utils` green, then `Ran 388 tests` / `OK`. The count holds: you replaced tests rather than adding them. If it moved, say so and why.

- [ ] **Step 6: Record the derivation**

For every `B` site in `assertion-classification.tsv` belonging to `tests/test_utils.py`'s phonetic tests, fill `derivation` with how the expectation was obtained — the printed pattern, and where the near-miss word diverges from it.

- [ ] **Step 7: Commit**

```bash
cd /data/Code/talaria
git add talaria/utils.py tests/test_utils.py docs/plans/phase-1-inputs/assertion-classification.tsv
git commit -m "feat: English phonetic equivalences for proper-noun correction

The Portuguese table mapped vowel classes and an inserted l, which do not
transfer. English errs on c/k, s/z, f/ph and i/y instead. The near-miss
test's fixture was derived by printing the pattern and confirming where
the dictionary word diverges from it, not by translating the old pair."
```

---

### Task 5: Rewrite `clean_caption` for English

**Files:**
- Modify: `talaria/utils.py` (`clean_caption` and its filler/contraction regexes)
- Modify: `tests/test_utils.py` (the caption-cleanup tests)
- Modify: `docs/plans/phase-1-inputs/assertion-classification.tsv`
- Test: `tests/test_utils.py`, whole suite

**Interfaces:**
- Consumes: Task 4's `utils.py`.
- Produces: `utils.clean_caption(txt) -> str` with English behaviour. Signature unchanged.

Portuguese behaviour being replaced: strip `eh/ah/uhum/hã`; remove `né` tag questions at end and mid-sentence; expand `tá`→`está` and `pra`/`pro`→`para` behind a guard protecting `pro labore`, `pro rata`, `pro forma`, `pro bono`, `pro indiviso`.

- [ ] **Step 1: Write the failing tests**

```python
    def test_strips_hesitation_fillers(self):
        self.assertEqual(utils.clean_caption("so uh we um shipped it"),
                         "so we shipped it")

    def test_strips_discourse_filler(self):
        self.assertEqual(utils.clean_caption("we shipped it, you know, fast"),
                         "we shipped it, fast")

    def test_expands_spoken_only_forms(self):
        self.assertEqual(utils.clean_caption("we gonna ship it"),
                         "we going to ship it")

    def test_keeps_real_contractions(self):
        txt = "we don't ship what we haven't tested"
        self.assertEqual(utils.clean_caption(txt), txt)

    def test_like_as_a_verb_survives(self):
        txt = "customers like the new flow"
        self.assertEqual(utils.clean_caption(txt), txt)

    def test_deduplicates_repeated_words(self):
        self.assertEqual(utils.clean_caption("we we shipped it"), "we shipped it")
```

`test_keeps_real_contractions` and `test_like_as_a_verb_survives` are the two that guard against over-reach, and they are the point of this task. The second is why `like` is dangerous: it is a verb and a preposition as often as a filler.

- [ ] **Step 2: Run them and watch them fail**

Run: `.venv/bin/python -m unittest tests.test_utils -v 2>&1 | tail -15`
Expected: the new tests fail; `clean_caption` still strips Portuguese fillers and expands Portuguese contractions.

- [ ] **Step 3: Implement**

- Fillers: `uh`, `um`, `er`, `ah`, `hmm`, as standalone words.
- Discourse fillers: `you know` and `I mean`, comma-delimited or sentence-initial.
- `like`: only when comma-delimited or sentence-initial. **If a bounded pattern cannot keep `test_like_as_a_verb_survives` green, drop `like` from the filler list entirely** — the spec says so explicitly, and a looser pattern that mangles real sentences is the worse outcome. Report which you did.
- Expand spoken-only forms only: `gonna`→`going to`, `wanna`→`want to`, `gotta`→`got to`, `kinda`→`kind of`.
- Leave real contractions untouched.
- Keep the existing two-pass word-repetition dedup exactly as it is; it is language-neutral.
- Delete `RE_NE_FIM`, `RE_NE_MEIO`, `RE_PRO_LATIM`, `_expande_contracoes`'s Portuguese body, and the Latin-phrase guard. English has no `pro` collision, so the guard protects nothing — delete its tests too rather than translating them.

- [ ] **Step 4: Run the tests, then the suite**

```bash
cd /data/Code/talaria
.venv/bin/python -m unittest tests.test_utils -v 2>&1 | tail -5
.venv/bin/python -m unittest discover -s tests 2>&1 | tail -3
```
Expected: `tests.test_utils` green. The full count will CHANGE here — the Latin-guard tests are deleted and six new tests added. Report the exact number and account for the delta.

- [ ] **Step 5: Confirm no caller depended on the Portuguese behaviour**

```bash
cd /data/Code/talaria
grep -rn 'clean_caption' --include='*.py' talaria/ tests/ run.py
```
Read each call site. If any downstream test asserts on cleaned output, it is a `B` site — classify it and re-derive its expectation rather than translating it.

- [ ] **Step 6: Record derivations and commit**

```bash
cd /data/Code/talaria
git add talaria/utils.py tests/test_utils.py docs/plans/phase-1-inputs/assertion-classification.tsv
git commit -m "feat: English filler and contraction handling for captions

Strips uh/um/er/ah/hmm and the you-know and I-mean discourse fillers, and
expands only the spoken-only forms. Real contractions stay: don't and it's
are correct written English, and expanding them in a burned-in caption
reads worse, which is the opposite of what this function is for. The
Portuguese Latin-phrase guard is deleted rather than translated -- English
has no pro collision for it to protect against."
```

---

### Task 6: Rewrite the three remaining language-bound regexes

**Files:**
- Modify: `talaria/curation.py` (`RE_FIRST_PERSON`, `RE_HEDGED_NUMBER`)
- Modify: `talaria/utils.py` (`RE_SOUND_TAG`)
- Modify: `tests/test_curadoria.py` (renamed by Task 3), `tests/test_utils.py`, `tests/test_txt_parse.py`
- Modify: `docs/plans/phase-1-inputs/assertion-classification.tsv`
- Test: the three test modules, then the whole suite

**Interfaces:**
- Consumes: Tasks 4 and 5's `utils.py`.
- Produces: `curation.RE_FIRST_PERSON`, `curation.RE_HEDGED_NUMBER`, `utils.RE_SOUND_TAG` matching English speech. `has_hedged_number(text) -> bool` and `attribution_trustworthy(...)` keep their signatures.

These three were not in the spec's original draft. They were found when Task 3's blind substitution rewrote `"minha empresa"` to `"minha company"` inside `RE_FIRST_PERSON` — a silent break of speaker-attribution detection. The lesson is recorded in the spec: grep for `re.compile` before assuming you have found every piece of language-specific logic.

- [ ] **Step 1: Confirm nothing else is language-bound**

```bash
cd /data/Code/talaria
grep -rnE 're\.compile' --include='*.py' talaria/
```

Five patterns are language-neutral and must NOT be touched: `RE_TS`, `RE_CUE`, `RE_INLINE` (WebVTT timestamps), `RE_TS_LINE` (`M:SS` timestamps), `RE_SENTENCE_END` (punctuation). If you find a sixth language-bound pattern this plan does not name, stop and report it rather than rewriting it unasked.

- [ ] **Step 2: Write the failing tests for `RE_HEDGED_NUMBER`**

This is the one with a near-miss guard, and the classification artifact flags it as this codebase's own `nossa` pair. Read its rows before writing anything.

```python
    def test_detects_approximate_figure(self):
        for txt in ("about 2005", "roughly 570 users", "I think 12 people"):
            self.assertTrue(curation.has_hedged_number(txt), txt)

    def test_exact_figure_does_not_warn(self):
        self.assertFalse(curation.has_hedged_number("founded in 2006"))

    def test_marker_without_a_number_does_not_warn(self):
        self.assertFalse(curation.has_hedged_number("I think this matters"))
```

`test_marker_without_a_number_does_not_warn` is the guard. `"I think"` MUST be a marker the new pattern recognises, or the test passes because there is no marker at all rather than because there is no number — which is exactly the defect Phase 0 shipped. **Verify it by printing the pattern and confirming `"I think"` matches the marker alternation on its own**, then confirming the full pattern does not match without a digit.

- [ ] **Step 3: Write the failing tests for `RE_FIRST_PERSON`**

```python
    def test_first_person_plural_is_detected(self):
        for txt in ("we built it here", "our first hire", "my co-founder left"):
            self.assertTrue(bool(curation.RE_FIRST_PERSON.search(txt)), txt)

    def test_third_person_is_not_detected(self):
        self.assertFalse(bool(curation.RE_FIRST_PERSON.search(
            "the company hired three people")))
```

- [ ] **Step 4: Write the failing test for `RE_SOUND_TAG`**

```python
    def test_strips_english_sound_tags(self):
        self.assertEqual(
            utils.strip_markup("[music] we shipped it [laughter]"),
            "we shipped it")

    def test_keeps_bracketed_content_that_is_not_a_sound_tag(self):
        txt = "[important] this stays"
        self.assertEqual(utils.strip_markup(txt), txt)
```

The second test already exists in Portuguese form and is the reason the tag list is an explicit alternation rather than "anything in brackets" — keep that property.

- [ ] **Step 5: Run them and watch them fail**

Run: `.venv/bin/python -m unittest tests.test_curation tests.test_utils -v 2>&1 | tail -20`
Expected: the new tests fail. The patterns still match Portuguese markers.

- [ ] **Step 6: Replace the three patterns**

```python
RE_FIRST_PERSON = re.compile(
    r"\b(we|our|us|my company|my co-?founder|I joined|I started)\b",
    re.IGNORECASE,
)

RE_HEDGED_NUMBER = re.compile(
    r"\b(about|around|approximately|roughly|some|maybe|I think|"
    r"if I remember|more or less|or so|give or take)\b"
    r"[^.!?]{0,40}?\d",
    re.IGNORECASE,
)

RE_SOUND_TAG = re.compile(
    r"\[\s*(music|laughter|applause|noise|silence|inaudible|crosstalk)\s*\]",
    re.IGNORECASE,
)
```

- [ ] **Step 7: Re-derive `SUSPECT_ATTRIBUTION_THRESHOLD`, or say why you did not**

`we` and `our` are far more frequent in English than `a gente` is in Portuguese, so the fraction-of-host-speech threshold this feeds was tuned against a different base rate. Read the constant, read `attribution_trustworthy`, and decide whether the number still means what it meant. Report your reasoning either way — **silently keeping a threshold tuned for another language is the failure mode here**, and it produces a warning that either never fires or always does.

If you conclude it needs changing but cannot derive a new value without a real English transcript, say exactly that and leave the number alone with a comment recording the open question. That is an acceptable outcome; pretending the number transferred is not.

- [ ] **Step 8: Run the tests, then the suite**

```bash
cd /data/Code/talaria
.venv/bin/python -m unittest tests.test_curation tests.test_utils tests.test_txt_parse -v 2>&1 | tail -6
.venv/bin/python -m unittest discover -s tests 2>&1 | tail -3
```
The count will change — you are replacing Portuguese-marker tests with English ones. Report the exact number and account for the delta.

- [ ] **Step 9: Record derivations and commit**

Fill `derivation` for every `B` row in the classification belonging to these three patterns.

```bash
cd /data/Code/talaria
git add talaria/curation.py talaria/utils.py tests/ docs/plans/phase-1-inputs/assertion-classification.tsv
git commit -m "feat: English markers for first-person, hedged-number and sound-tag detection

Three language-bound patterns the spec's first draft missed, found when a
blind substitution rewrote minha empresa to minha company inside the
first-person alternation and silently broke speaker-attribution detection.

The hedged-number near-miss test's fixture was verified to contain a
marker the new pattern recognises, so it still fails for the right reason
rather than for the absence of a marker."
```

---

### Task 7: Translate comments, docstrings and test method names

**Files:**
- Modify: all 27 modules, 23 test modules, `run.py`, `scripts/youtube_auth.py`
- Test: whole suite

**Interfaces:**
- Consumes: the renamed, rewritten tree.
- Produces: no API change. Prose only.

This is the largest volume and the lowest behavioural risk. The suite cannot police it, so the constraint below is the only control.

**Before you start: some Portuguese comments are damaged.** Task 3's mechanical pass substituted renamed words inside Portuguese sentences — about 135 comment and docstring lines. The decision was to leave them, because this task rewrites all that prose anyway. But it means the Portuguese you translate from is in places mangled past recognising the part of speech: `schedule.py` reads "Le e validate a agenda", `environment.py` "who write o", `utils.py` "faz em name proprio", `caption.py` "e o mesmo reason do layout.py".

When a comment does not parse as Portuguese, recover the original rather than guessing:

```bash
git show adc1623:talaria/<module>.py | sed -n '<line>,<line+3>p'
```

`adc1623` is the commit immediately before the rename. Do this whenever a sentence reads oddly — a mistranslation founded on a corrupted source is worse than the corruption, because it looks deliberate.

- [ ] **Step 1: Translate, file by file**

Work module by module so each commit is reviewable. Carry the meaning, not the word order — these comments record real empirical findings and the findings must survive. `talaria/config.py`'s `BASE_Y` derivation, `talaria/audio.py`'s dB figures, `talaria/render.py`'s explanation of why `-c copy` is not used: all load-bearing.

- [ ] **Step 1b: Rename the Portuguese test method names**

`docs/plans/phase-1-inputs/test-name-snapshot.txt` lists all 388, snapshotted after Task 3. The large majority are Portuguese. They were excluded from the identifier inventory by mistake — see that file's header — and neither acceptance criterion can see them: zero contain an accent, and none is a function word.

A test name is a sentence stating what the test proves, so translate the meaning rather than substituting words. Do it per module, in the same commit as that module's comments, so each commit stays reviewable.

Two cases need judgement rather than translation:
- `test_nao_expande_pro_em_locucao` names the Latin-phrase guard that Task 5 deletes. If Task 5 has already removed it, there is nothing to rename; if not, leave it and say so.
- Where a name describes Portuguese-specific behaviour that Tasks 5 or 6 replaced, the English name should describe the NEW behaviour, not translate the old description.

Renaming is safe — no test is referenced by name as a string, no decorator is keyed on one, `subTest` takes keyword arguments. The suite count must stay 388 unless a task deleted a test and said so.

- [ ] **Step 2: Do not let translation inflate the prose**

A translated comment should be about the length of the original. A comment that was noise in Portuguese is noise in English — delete it instead of translating it. Phase 0's rule applies unchanged: a comment earns its place only by stating a constraint the code cannot show.

Check as you go:

```bash
cd /data/Code/talaria
git diff --stat
```
Insertions should be close to deletions. A large net gain means prose is being padded.

- [ ] **Step 3: Verify no accented character survives in the files you finished**

```bash
cd /data/Code/talaria
grep -rlP '[\x{00C0}-\x{00FF}]' --include='*.py' talaria/ tests/ run.py scripts/
```
This lists files still containing Portuguese. It shrinks as you go; use it to track progress. (Strings are Task 7's job, so files with user-facing messages will still appear here until then.)

- [ ] **Step 4: Run the suite and commit per module group**

Run: `.venv/bin/python -m unittest discover -s tests 2>&1 | tail -3`
Expected: the count from Task 5, unchanged, `OK`. Comment edits cannot change behaviour; if the count moves, an edit escaped a comment into code.

Commit in groups of related modules, not one commit for everything.

---

### Task 8: Translate user-facing strings, prompts and README

**Files:**
- Modify: every module with a user-facing message, `run.py`, `scripts/youtube_auth.py`
- Modify: `prompts/cortes.md`→`prompts/clips.md`, `prompts/materiais.md`→`prompts/materials.md`, `prompts/posts.md`, `prompts/README.md`
- Modify: `README.md`, `.env.example`
- Modify: `docs/plans/phase-1-inputs/assertion-classification.tsv`
- Test: whole suite

**Interfaces:**
- Consumes: the classification from Task 2 and the prose tree from Task 6.
- Produces: an entirely English user-facing surface.

- [ ] **Step 1: Translate the placeholders and channel-identity defaults**

- `NOME_PROGRAMA` (now renamed) → `"MY PODCAST"`
- `CARD_ARROBA` (now renamed) → `"@yourhandle"`
- `hashtags.FIXAS` (now renamed) → `["#MyPodcast", "#Entrepreneurship", "#Startups"]`
- `PREFIXO_EPISODIO` (now renamed) → `"▶ Full episode: "`
- `WHISPER_LANG` → `"en"`
- `FUSO_PUBLICACAO`'s NAME changes per the map; its VALUE stays `"America/Sao_Paulo"`.

- [ ] **Step 2: Translate the prompts and rename their placeholder tokens**

`git mv prompts/cortes.md prompts/clips.md` and `git mv prompts/materiais.md prompts/materials.md`. Translate all four files. Rename the tokens the code substitutes — `{{METADADOS}}`→`{{METADATA}}`, `{{TRANSCRICAO}}`→`{{TRANSCRIPT}}`, `{{CURADORIA}}`→`{{CURATION}}`, `{{CORTES}}`→`{{CLIPS}}` — and update every substitution site:

```bash
cd /data/Code/talaria
grep -rn 'METADADOS\|TRANSCRICAO\|CURADORIA\|CORTES\|cortes\.md\|materiais\.md' --include='*.py' --include='*.md' talaria/ tests/ run.py prompts/ README.md
```

The prompts are skeletons — structure and placeholders, no editorial criteria. Translate the structure; do not invent editorial rules. `prompts/README.md` says the criteria are the channel owner's to write, and that stays true.

- [ ] **Step 3: For every `B` site, re-derive the expectation by running the code**

Consult `assertion-classification.tsv`. For each `B` site: translate the message in the source, then run the code and read what it actually produces, then write the assertion from that output. Fill `derivation` with the command you ran.

Where a `B` site pins a single word in a message (`assertIn`), verify the word is unique to that message before using it:

```bash
cd /data/Code/talaria
grep -c '<chosen word>' talaria/<module>.py
```
Expect 1. Phase 0 shipped an assertion pinned on `"Console"` which also appeared in a sibling message; it passed only because the two raise sites were mutually exclusive, which the assertion did not verify.

- [ ] **Step 4: Update the README**

Retranslate it, and correct what the rename changed: the command list (`curar`→`curate`, `agenda`→`schedule`), the `## Personalizar`→`## Customising` table's paths and symbol names, the test count, and the `decisoes/calendario.json`→`decisions/schedule.json` example. Drop the note saying the codebase is Portuguese with English planned — it will no longer be true.

- [ ] **Step 5: Run the suite**

Run: `.venv/bin/python -m unittest discover -s tests 2>&1 | tail -3`
Expected: the count from Task 5, `OK`.

- [ ] **Step 6: Commit**

```bash
cd /data/Code/talaria
git add -A
git commit -m "feat: English user-facing strings, prompts and README

Every B-classified assertion's expectation was obtained by running the
translated code and reading its output, not by translating the old
expected string. Derivations are recorded in the classification file."
```

---

### Task 9: Final acceptance

**Files:**
- Modify: `README.md` (test count only, after measuring)
- Test: whole suite, from a rebuilt venv

**Interfaces:**
- Consumes: everything above.
- Produces: the Phase 1 deliverable.

- [ ] **Step 1: Rebuild the venv and run the suite**

```bash
cd /data/Code/talaria
rm -rf .venv && python3 -m venv .venv
.venv/bin/python -m pip install -q --upgrade pip
.venv/bin/pip install -q -r requirements.txt
.venv/bin/python -m unittest discover -s tests 2>&1 | tail -3
```
Expected: `OK`. Record the count and put it in the README.

- [ ] **Step 2: No accented characters anywhere**

```bash
cd /data/Code/talaria
grep -rnP '[\x{00C0}-\x{00FF}]' --include='*.py' --include='*.md' \
  talaria/ tests/ run.py scripts/ prompts/ README.md
```
Expected: empty. Portuguese cannot be written without accents, so this one check covers identifiers, prose and strings together. `docs/` is excluded — it records the originals.

One legitimate exception to judge, not to wave through: `PREFIXO_EPISODIO`'s `▶` is U+25B6, outside this range, so it will not match. If any hit turns out to be a deliberate non-Portuguese character, say which and why.

- [ ] **Step 3: No Portuguese function words**

```bash
cd /data/Code/talaria
grep -rniE '\b(que|nao|para|uma|dos|das|pelo|pela|sem|mais|ja|ao|aos|pra|nem|onde|quando|porque|entao|isso|este|esta|aquele|muito|entre|cada|todo|toda|seu|sua|dele|dela|foi|ser|ter|fazer|pode|deve|tem|sao|estao|com)\b' \
  --include='*.py' --include='*.md' talaria/ tests/ run.py scripts/ prompts/ README.md
```
Expected: only `.com` URL hits, roughly a dozen. Confirm each is a URL. `no` and `so` are deliberately absent from this pattern — they are ordinary English words. Read every other hit; do not widen the pattern to silence one.

- [ ] **Step 4: No Portuguese identifier survives, mapped or not**

The two checks above cannot see an unaccented Portuguese identifier: neither
`estado` nor `texto` nor `pasta` contains an accent or appears in any
function-word list. Roughly 727 occurrences of that class existed after the
first rename pass, and nothing in this plan detected them. So the criterion is
the inventory, not a word list.

```bash
cd /data/Code/talaria
# Re-extract and confirm every identifier we define has a verdict recorded.
grep -c '' docs/plans/phase-1-inputs/identifier-inventory.txt
awk -F'\t' 'NR>1 && $2!=""{print $2}' docs/plans/phase-1-inputs/rename-map.tsv | sort -u | wc -l
```

**The verdicts file must not be trusted, only checked.** It is produced by the
same pass it certifies, so a wrong verdict is invisible to a criterion that
consults it. Two rows in its first version claimed a rename that was never
applied (`todo`→`combined`, `segundo`→`second` — neither new name existed
anywhere), and seven Portuguese identifiers sat in it verdicted `english`.
A gate that reads those rows and believes them gates nothing.

So verify the claims mechanically instead:

```bash
cd /data/Code/talaria
python3 docs/plans/phase-1-inputs/check-renamed-verdicts.py
```

Exit 0 and "0 false 'renamed' verdict(s)" is the pass condition.

That script is AST-based, and it has to be. A grep for the old word counts its
legitimate appearances in Portuguese prose, which survive until the string pass
— the first draft of this check fired on `arquivo` (67), `antes` (50) and
`palavra` (41), all comments, and buried the two real failures among thirty
false ones. The question is whether the old name is still an **identifier**,
and only a parse can answer it.

Then re-extract identifiers from the current tree by AST, exactly as
`identifier-inventory.txt`'s header describes, and confirm every one is either
in the verdicts file or newly introduced and English. A new Portuguese
identifier added during the prose or string passes is the other failure this
catches.

- [ ] **Step 5: Every map entry applied**

```bash
cd /data/Code/talaria
awk -F'\t' 'NR>1{print $2}' docs/plans/phase-1-inputs/rename-map.tsv | while read old; do
  hits=$(grep -rowE "\b$old\b" --include='*.py' --include='*.md' talaria/ tests/ run.py scripts/ prompts/ README.md | wc -l)
  [ "$hits" != "0" ] && echo "SURVIVED: $old ($hits)"
done
```
Expected: empty.

- [ ] **Step 5: Every `B` site has a derivation**

```bash
cd /data/Code/talaria
awk -F'\t' 'NR>1 && $4=="B" && $6=="" {print "B site with no derivation: " $1":"$2}' \
  docs/plans/phase-1-inputs/assertion-classification.tsv
```
Expected: empty. A `B` site with no recorded derivation means an expectation was translated rather than measured — which is the one failure mode this plan exists to prevent.

- [ ] **Step 6: The CLI is entirely English**

```bash
cd /data/Code/talaria
.venv/bin/python run.py --help
.venv/bin/python run.py curate --help
.venv/bin/python run.py schedule --help
```
Read the output. Every word the user sees must be English.

- [ ] **Step 7: Commit, push, report**

```bash
cd /data/Code/talaria
git add README.md
git commit -m "docs: update the test count after the English translation"
git push
git log --oneline | head -20
```

Report: the final test count, the A/B split from Task 2, whether `like` survived as a filler, and any map entry whose name you would revisit.
