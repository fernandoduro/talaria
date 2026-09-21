# Talaria Phase 0 — Fork and De-brand Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the `next-video-shorts-pacote` handover export into `talaria` — a private git repository with no trace of the originating project, whose full test suite passes on Arch Linux and whose YouTube path can be bootstrapped.

**Architecture:** No structural change. The package is renamed, font resolution stops depending on the host system, the originating project's production-history references are removed from comments while the empirical facts they carry are kept, and the one missing script referenced by the docs is written. Translation, the channel profile, the publisher interface and the Claude API integration are Phases 1–4 and are explicitly out of scope.

**Tech Stack:** Python 3.9+ (3.12.13 on this machine), `unittest` (stdlib, no pytest), Pillow, ffmpeg/ffprobe (system), `google-auth-oauthlib`, `google-api-python-client`, `boto3`, `requests`, `yt-dlp`, `faster-whisper`.

## Global Constraints

- Spec: `docs/specs/2026-09-21-phase-0-fork-and-debrand-design.md`. Read it before starting.
- Package name `talaria`, repo `talaria`, env prefix `TALARIA_*`.
- The codebase stays **Portuguese** in this phase. Do not translate identifiers, comments, docstrings or strings. Full English is Phase 1.
- Tests run with `unittest`, never pytest: `.venv/bin/python -m unittest discover -s tests`.
- Never squash. Never force-push. Commit after each task.
- Code comments: a comment earns its place only by stating a constraint the code cannot show. When removing a history label, do not replace it with a longer explanation — shorten.
- `run.py` is the only CLI entry point. Do not add new top-level commands in this phase.
- Render output changes only where the spec decided it: the vendored fonts, and `POST_CIT_SIZE` 160 → 150 (spec, Fonts section — Poppins at 160 overflows the quote to a 6th line that crosses the rule at y=2242). Any other change to rendered output is out of scope.

---

### Task 1: Git repository and private remote

**Files:**
- Create: none
- Modify: none
- Test: none (verification is `git` and `gh` output)

**Interfaces:**
- Consumes: nothing
- Produces: a git repository at the project root whose first commit is the package as received, and a private GitHub remote named `talaria`. Every later task commits into this repository.

- [ ] **Step 1: Confirm the directory is not already a repository**

Run: `git -C /data/Code/next-video-shorts-pacote rev-parse --git-dir`
Expected: `fatal: not a git repository`. If it *is* a repository, stop and report — the spec assumes a fresh init.

- [ ] **Step 2: Initialise and verify what would be committed**

```bash
git -C /data/Code/next-video-shorts-pacote init
git -C /data/Code/next-video-shorts-pacote add -A -n -- . ':!docs'
```

The existing `.gitignore` already excludes `projetos/`, `.env`, `__pycache__/` and `.venv/`. Confirm the dry-run output lists no `.env`, no `projetos/`, and no `.venv/`. If it does, stop — do not commit secrets.

- [ ] **Step 3: Commit the package exactly as received**

`docs/` is excluded here on purpose: the spec is our work, not the received package, and keeping it out of this commit is what makes the de-branding diff readable later.

```bash
cd /data/Code/next-video-shorts-pacote
git add -- . ':!docs'
git commit -m "chore: import next-video-shorts-pacote as received

Handover export of the video-shorts pipeline, unmodified. Committed as
its own baseline so every later change is a reviewable diff against what
actually arrived."
```

- [ ] **Step 4: Commit the spec**

```bash
cd /data/Code/next-video-shorts-pacote
git add docs/
git commit -m "docs: add Talaria phase 0 spec and five-phase roadmap"
```

- [ ] **Step 5: Create the private remote and push**

```bash
cd /data/Code/next-video-shorts-pacote
gh repo create talaria --private --source=. --remote=origin --push
```

- [ ] **Step 6: Verify the remote is private**

Run: `gh repo view talaria --json isPrivate,nameWithOwner`
Expected: `{"isPrivate":true,"nameWithOwner":"fernandoduro/talaria"}`. If `isPrivate` is false, run `gh repo edit talaria --visibility private` immediately and re-verify.

---

### Task 2: Virtualenv, dependencies, recorded baseline

**Files:**
- Create: `.venv/` (already git-ignored)
- Modify: none
- Test: `tests/` (whole suite, as a measurement)

**Interfaces:**
- Consumes: the repository from Task 1.
- Produces: `.venv/bin/python`, used by every later verification step. A recorded baseline test count that later tasks compare against.

- [ ] **Step 1: Create the venv and install dependencies**

```bash
cd /data/Code/next-video-shorts-pacote
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

`faster-whisper` pulls a large CUDA-adjacent dependency tree; let it finish. If it fails to build, report the error and stop rather than removing it from `requirements.txt` — transcription is a real feature.

- [ ] **Step 2: Confirm every import named in requirements resolves**

```bash
cd /data/Code/next-video-shorts-pacote
.venv/bin/python -c "
import yt_dlp, faster_whisper, PIL, requests, boto3, googleapiclient, google_auth_oauthlib
print('all imports OK')
"
```

Expected: `all imports OK`. Before this task, `requests`, `boto3`, `googleapiclient`, `google_auth_oauthlib`, `yt_dlp` and `faster_whisper` were all absent, which is why 4 test modules failed to import.

- [ ] **Step 3: Record the baseline**

```bash
cd /data/Code/next-video-shorts-pacote
.venv/bin/python -m unittest discover -s tests 2>&1 | tail -3
```

Write the exact line into the task notes. Expected shape: `Ran 3NN tests` with roughly 15 errors and 1 failure remaining — the 4 import errors from the pre-venv baseline (`Ran 334 tests — FAILED (failures=1, errors=19, skipped=1)`) should now be gone and the collected count should *rise*, because those 4 modules now load their tests.

- [ ] **Step 4: Confirm the remaining failures are the known font defect**

```bash
cd /data/Code/next-video-shorts-pacote
.venv/bin/python -m unittest discover -s tests 2>&1 | grep -E '^(ERROR|FAIL):' | sed 's/ (.*//' | sort | uniq -c
```

Expected: the errors are concentrated in `test_encerramento`, `test_render` and `test_integracao`, and the single failure is `test_citacao_do_design_cabe_em_5_linhas`. Any error outside those modules is a new finding — report it before proceeding, do not fix it silently.

- [ ] **Step 5: Commit nothing, record the baseline in the task notes**

There is nothing to commit: `.venv/` is git-ignored. Carry the recorded numbers forward — Task 4 must return this suite to zero errors and zero failures.

---

### Task 3: Rename the package to `talaria`

**Files:**
- Modify: `nvshorts/` → `talaria/` (directory, 26 modules, via `git mv`)
- Modify: `run.py:40` (package import), `run.py:133` (temp-file prefix)
- Modify: `nvshorts/config.py` env var name (now `talaria/config.py:74`)
- Modify: all 20 test modules under `tests/` — import statements and 24 `mock.patch` string targets
- Modify: `README.md`, `requirements.txt` header, `.env.example` (any `nvshorts`/`NVSHORTS` mentions)
- Test: whole suite

**Interfaces:**
- Consumes: the venv from Task 2.
- Produces: the import root `talaria`. Every later task imports `from talaria import ...`; the env override is `TALARIA_CAPTION_BACKEND`.

- [ ] **Step 1: Enumerate every reference before touching anything**

```bash
cd /data/Code/next-video-shorts-pacote
grep -rn 'nvshorts\|NVSHORTS' --include='*.py' --include='*.md' --include='*.txt' --include='.env.example' . | grep -v '^./.venv/' | wc -l
grep -rno 'mock\.patch("nvshorts\.[a-z_.]*' tests/*.py | wc -l
```

Record both counts. The second must be 24. This is the number that matters: `mock.patch` targets are string literals, so they are invisible to an import-statement grep and to any IDE rename.

- [ ] **Step 2: Move the directory with git so history follows**

```bash
cd /data/Code/next-video-shorts-pacote
git mv nvshorts talaria
```

- [ ] **Step 3: Rewrite every remaining reference**

Intra-package imports are relative (`from . import config`), so they need no change. Everything else is a literal substitution. `.venv/` is excluded because it contains installed third-party code.

```bash
cd /data/Code/next-video-shorts-pacote
grep -rlZ 'nvshorts\|NVSHORTS' --include='*.py' --include='*.md' --include='*.txt' --include='.env.example' . \
  | grep -zv '^./.venv/' | grep -zv '^./docs/' \
  | xargs -0 -r sed -i 's/NVSHORTS/TALARIA/g; s/nvshorts/talaria/g'

`docs/` is excluded deliberately: the spec and this plan quote `nvshorts`, `NVSHORTS_CAPTION_BACKEND` and `mock.patch("nvshorts...")` when explaining what is being renamed. Rewriting them turns the spec into "`talaria/` → `talaria/`" and destroys the record of what changed.
```

- [ ] **Step 4: Verify no reference survives**

```bash
cd /data/Code/next-video-shorts-pacote
grep -rn 'nvshorts\|NVSHORTS' --include='*.py' --include='*.md' --include='*.txt' --include='.env.example' . | grep -v '^./.venv/' | grep -v '^./docs/'
```

Expected: no output. Then confirm the renamed env var and the temp prefix landed:

```bash
grep -n 'TALARIA_CAPTION_BACKEND' talaria/config.py
grep -n 'talaria_thumb_' run.py
grep -c 'mock\.patch("talaria\.' tests/*.py | grep -v ':0' | awk -F: '{s+=$2} END {print s}'
```

Expected: one hit for the env var, one for the temp prefix, and `24` for the patch targets.

- [ ] **Step 5: Run the suite**

Run: `.venv/bin/python -m unittest discover -s tests 2>&1 | tail -3`
Expected: the *same* counts recorded in Task 2 Step 3 — identical tests run, identical errors and failures. A rename must not change any result. A changed count means a `mock.patch` target or an import was missed or over-substituted.

- [ ] **Step 6: Commit**

```bash
cd /data/Code/next-video-shorts-pacote
git add -A
git commit -m "refactor: rename package nvshorts to talaria

Pure rename, no behaviour change: directory, imports, the 24 mock.patch
string targets in the tests, the NVSHORTS_CAPTION_BACKEND override and
the temp-file prefix in run.py. Suite result is unchanged from before."
```

---

### Task 4: Vendor fonts and fix font resolution

**Files:**
- Create: `assets/fonts/DejaVuSans-Bold.ttf`, `assets/fonts/DejaVuSansMono-Bold.ttf`, `assets/fonts/Poppins-SemiBold.ttf`
- Create: `assets/fonts/LICENSE-DejaVu.txt`, `assets/fonts/LICENSE-Poppins.txt`
- Create: `tests/test_fontes.py`
- Modify: `talaria/config.py:10-48` (font resolution), `talaria/config.py:163-167` (`_RAIZ` moves up)
- Modify: `talaria/encerramento.py:21,44` (macOS literal → config)
- Modify: `tests/test_post_instagram.py:211-216`, `tests/test_render.py:238-262` (re-derived assertions)
- Test: `tests/test_fontes.py`, `tests/test_encerramento.py`, `tests/test_render.py`, `tests/test_post_instagram.py`, `tests/test_integracao.py`

**Interfaces:**
- Consumes: `talaria.config` from Task 3.
- Produces: `config.FONT`, `config.POST_FONT`, `config.POST_MONO` — absolute paths to repo-relative `.ttf` files, each guaranteed to exist or an exception at import. `config.find_font()` and `config._primeira_fonte()` no longer exist; `config.POST_FONT_INDEX` and `config.POST_MONO_INDEX` still exist and are both `0` (Task 5 removes them).

- [ ] **Step 1: Vendor the font files**

DejaVu and its licence are already on this machine (`pacman -Qo` reports `ttf-dejavu`). Poppins is fetched from Google's own repository — an inbound download of an OFL-licensed font, nothing is uploaded.

```bash
cd /data/Code/next-video-shorts-pacote
mkdir -p assets/fonts
cp /usr/share/fonts/TTF/DejaVuSans-Bold.ttf assets/fonts/
cp /usr/share/fonts/TTF/DejaVuSansMono-Bold.ttf assets/fonts/
cp /usr/share/licenses/ttf-dejavu/LICENSE assets/fonts/LICENSE-DejaVu.txt
curl -fsSL -o assets/fonts/Poppins-SemiBold.ttf \
  https://github.com/google/fonts/raw/main/ofl/poppins/Poppins-SemiBold.ttf
curl -fsSL -o assets/fonts/LICENSE-Poppins.txt \
  https://github.com/google/fonts/raw/main/ofl/poppins/OFL.txt
chmod 644 assets/fonts/*
ls -l assets/fonts/
```

- [ ] **Step 2: Verify each file is a real font of the expected identity**

```bash
cd /data/Code/next-video-shorts-pacote
.venv/bin/python -c "
from PIL import ImageFont
for f in ('DejaVuSans-Bold','DejaVuSansMono-Bold','Poppins-SemiBold'):
    print(f, ImageFont.truetype(f'assets/fonts/{f}.ttf', 40).getname())
"
```

Expected: `('DejaVu Sans', 'Bold')`, `('DejaVu Sans Mono', 'Bold')`, `('Poppins', 'SemiBold')`. A stray HTML error page from a moved URL fails here rather than silently rendering wrong type — if Poppins does not report `('Poppins', 'SemiBold')`, stop and report the URL.

- [ ] **Step 3: Write the failing test**

Create `tests/test_fontes.py`:

```python
import os
import unittest

from PIL import ImageFont

from talaria import config

ESPERADAS = {
    "FONT": ("DejaVu Sans", "Bold"),
    "POST_FONT": ("Poppins", "SemiBold"),
    "POST_MONO": ("DejaVu Sans Mono", "Bold"),
}


class TestFontesVersionadas(unittest.TestCase):
    """As fontes vêm do repositório, não do sistema.

    O texto é queimado no vídeo: fonte resolvida pelo fontconfig muda com a
    máquina e o erro só aparece no vídeo publicado, que não se corrige.
    """

    def test_cada_fonte_e_um_arquivo_do_repositorio(self):
        raiz = os.path.dirname(os.path.dirname(os.path.abspath(config.__file__)))
        esperado = os.path.join(raiz, "assets", "fonts")
        for nome in ESPERADAS:
            caminho = getattr(config, nome)
            self.assertTrue(os.path.isfile(caminho), f"{nome}: {caminho}")
            self.assertEqual(os.path.dirname(caminho), esperado, nome)

    def test_cada_fonte_tem_a_identidade_esperada(self):
        for nome, identidade in ESPERADAS.items():
            fnt = ImageFont.truetype(getattr(config, nome), 40)
            self.assertEqual(fnt.getname(), identidade, nome)

    def test_fonte_ausente_aborta_com_mensagem_util(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            config._fonte_versionada("NaoExiste-Bold.ttf")
        self.assertIn("NaoExiste-Bold.ttf", str(ctx.exception))
        self.assertIn("assets/fonts", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 4: Run it to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_fontes -v`
Expected: FAIL. `test_cada_fonte_e_um_arquivo_do_repositorio` fails because `config.FONT` still points into `/usr/share/fonts/TTF/`, and `test_fonte_ausente_aborta_com_mensagem_util` errors with `AttributeError: module 'talaria.config' has no attribute '_fonte_versionada'`.

- [ ] **Step 5: Replace the font block in `talaria/config.py`**

Delete lines 10–48 — the `_FONT_CANDIDATES` list, `find_font()` and `FONT = find_font()` — and put this in their place. `_RAIZ` moves here from its current definition further down the file; delete the later duplicate (it sits just above `POST_TEMPLATE`) and leave `POST_TEMPLATE` and `LOGO_PATH` using it unchanged.

```python
# ---------------------------------------------------------------------------
# Fontes — versionadas em assets/fonts/.
#
# O texto é queimado no vídeo e rasterizado nos PNG, então a fonte decide o
# resultado publicado. Resolver pelo sistema substitui em silêncio: nesta
# máquina o fc-match devolve Noto Sans quando se pede Poppins, e o layout sai
# errado sem nenhum erro. Arquivo no repositório = mesmo render em qualquer
# máquina, e falta de arquivo aborta na importação.
# ---------------------------------------------------------------------------
_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DIR_FONTES = os.path.join(_RAIZ, "assets", "fonts")


def _fonte_versionada(nome: str) -> str:
    caminho = os.path.join(_DIR_FONTES, nome)
    if not os.path.exists(caminho):
        raise FileNotFoundError(
            f"fonte {nome} não encontrada em assets/fonts — o arquivo é "
            f"versionado; restaure com 'git checkout assets/fonts/{nome}'."
        )
    return caminho


FONT = _fonte_versionada("DejaVuSans-Bold.ttf")
```

`import shutil` stays — `has_drawtext()` still uses it.

- [ ] **Step 6: Point `POST_FONT` and `POST_MONO` at vendored files**

Replace `_POST_FONT_CANDIDATES`, `_POST_MONO_CANDIDATES`, `_primeira_fonte()` and the two tuple-unpacking assignments (`config.py:196-221` before this task's edits) with:

```python
# Fonte da citação e do rodapé do post. Índice 0 em .ttf — a distinção só
# importava enquanto a cadeia de candidatas podia cair num .ttc do macOS.
POST_FONT = _fonte_versionada("Poppins-SemiBold.ttf")
POST_FONT_INDEX = 0
POST_MONO = _fonte_versionada("DejaVuSansMono-Bold.ttf")
POST_MONO_INDEX = 0
```

The `*_INDEX` constants stay for now so this task changes font resolution only; Task 5 removes them and their call sites together.

Then change `POST_CIT_SIZE` from `160` to `150` where it is defined (currently `config.py:188`), with the reason the number is not the design's:

```python
# 150 e não 160: a Poppins é mais larga que a Avenir Next Demi Bold em que o
# layout foi medido, e a 160 a citação de referência vira 6 linhas — a 6ª
# cruzaria o filete em y=2242. A 150 sobram 83px na linha mais cheia.
POST_CIT_SIZE = 150
```

`POST_CIT_PASSO`, `POST_CIT_ALTURA` and `POST_FILETE_Y` are untouched — they are slot geometry, not glyph metrics.

- [ ] **Step 7: Fix the macOS literal in `talaria/encerramento.py`**

Delete line 21 (`_FONT_ARROBA = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"`) and change line 44 to take the font from config:

```python
    fonte = ImageFont.truetype(config.FONT, _TAMANHO_ARROBA)
```

`_TAMANHO_ARROBA = 50` stays — it is a layout constant, not a path. `config` is already imported at module level.

- [ ] **Step 8: Run the font and closing-card tests**

```bash
cd /data/Code/next-video-shorts-pacote
.venv/bin/python -m unittest tests.test_fontes tests.test_encerramento -v 2>&1 | tail -5
```

Expected: PASS for all of `tests.test_fontes`, and `test_encerramento`'s 9 errors gone. These 9 were the single largest block in the baseline.

- [ ] **Step 9: Confirm the measured wrap reproduces**

The approved 5-line break was validated on Avenir Next Demi Bold, which is not vendored and does not exist on Linux. The vendored-font wrap was already measured when this plan was written; this step confirms it reproduces rather than re-deciding it.

```bash
cd /data/Code/next-video-shorts-pacote
.venv/bin/python - <<'PY'
from PIL import ImageFont
from talaria import config, render
fnt = ImageFont.truetype(config.POST_FONT, config.POST_CIT_SIZE)
txt = ("A gente descobriu que não precisava mudar de cidade "
       "para construir algo grande. Precisava ficar.")
linhas = render.wrap_by_pixels(txt, fnt=fnt, largura=config.POST_LARGURA_UTIL)
print("fonte:", fnt.getname(), "size:", config.POST_CIT_SIZE)
print("linhas:", len(linhas))
for l in linhas:
    print(f"   {int(fnt.getlength(l)):>5}px  {l!r}")
PY
```

Expected, exactly:

```
fonte: ('Poppins', 'SemiBold') size: 150
linhas: 5
    1717px  'A gente descobriu que'
    1650px  'não precisava mudar'
    1161px  'de cidade para'
    1695px  'construir algo grande.'
    1172px  'Precisava ficar.'
```

If the output differs, stop and report — either the vendored file is not the font that was measured (check `getname()`), or `POST_CIT_SIZE` did not get changed in Step 6. Do not adjust the expected values to match; these numbers are what the spec's font decision rests on.

- [ ] **Step 10: Update the two font-dependent assertions**

In `tests/test_render.py`, the guard in `test_quebra_do_design_com_a_fonte_do_design` currently skips unless the font is Avenir Next. Replace the guard and the expected split with the measured result, and rewrite the docstring to describe the vendored font rather than a candidate chain:

```python
    def test_quebra_do_design_com_a_fonte_do_design(self):
        """A citação de referência quebra em 5 linhas na fonte versionada.

        Não há mais cadeia de candidatas: a fonte vem de assets/fonts/, então
        a quebra é a mesma em qualquer máquina e o teste cobra o layout em vez
        de pular.
        """
        from PIL import ImageFont
        from talaria import config, render
        fnt = ImageFont.truetype(config.POST_FONT, config.POST_CIT_SIZE)
        self.assertEqual(fnt.getname(), ("Poppins", "SemiBold"))
        linhas = render.wrap_by_pixels(self.CITACAO_DO_DESIGN, fnt=fnt,
                                       largura=config.POST_LARGURA_UTIL)
        self.assertEqual(linhas, ["A gente descobriu que",
                                  "não precisava mudar",
                                  "de cidade para",
                                  "construir algo grande.",
                                  "Precisava ficar."])
```

This split assumes `CITACAO_DO_DESIGN` already holds the de-branded text, so **make that one-line fixture change now, in this task**, rather than waiting for Task 6:

```python
    CITACAO_DO_DESIGN = ("A gente descobriu que não precisava mudar de cidade "
                         "para construir algo grande. Precisava ficar.")
```

Apply the identical string to `tests/test_post_instagram.py:212-213`. Task 6 Step 6 then finds this already done and moves on to the fixtures that carry no width constraint. No task may end with a knowingly-failing test.

The `skipTest` call and the `familia, estilo = fnt.getname()` unpacking are both deleted — with a vendored font there is no legitimate reason to skip.

- [ ] **Step 11: Run the full suite**

Run: `.venv/bin/python -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK` — zero errors, zero failures, zero skips. The skip is gone because the font it waited for is now in the repository. If `test_citacao_do_design_cabe_em_5_linhas` still fails, `POST_CIT_SIZE` is not 150 or the fixture text does not match Step 9's — recheck Step 6 and Step 9 before changing any assertion.

- [ ] **Step 12: Commit**

```bash
cd /data/Code/next-video-shorts-pacote
git add assets/fonts tests/test_fontes.py talaria/config.py talaria/encerramento.py tests/test_render.py tests/test_post_instagram.py
git commit -m "fix: resolve fonts from the repository instead of the host system

encerramento.py loaded a macOS-only path with no fallback, so the closing
card could not be built on Linux at all. POST_FONT and POST_MONO had no
Linux candidates and fell through find_font's fc-match fallback, which
never fails -- it substitutes. On this machine it returns Noto Sans for
Poppins, so the layout broke with no error.

Three fonts are now versioned under assets/fonts with their licences and
a missing file aborts at import. The approved line break had been
validated against Avenir Next Demi Bold, which is not vendored, so both
font-dependent assertions were re-derived by measurement against Poppins
SemiBold rather than carried over."
```

---

### Task 5: Remove the dead font-resolution machinery

**Files:**
- Modify: `talaria/config.py` (`has_drawtext` untouched; remove `POST_FONT_INDEX`, `POST_MONO_INDEX`)
- Modify: `talaria/post_instagram.py:20-21,72,155,159`
- Modify: `tests/test_render.py:227-228,251-252`
- Test: whole suite

**Interfaces:**
- Consumes: `config.POST_FONT`, `config.POST_MONO` from Task 4.
- Produces: `post_instagram._fonte(caminho, tamanho)` — a two-argument signature. `config.POST_FONT_INDEX` and `config.POST_MONO_INDEX` no longer exist.

This is separated from Task 4 so a reviewer can accept the font fix and reject the cleanup independently.

- [ ] **Step 1: Confirm both index constants are now always zero**

```bash
cd /data/Code/next-video-shorts-pacote
grep -rn 'POST_FONT_INDEX\|POST_MONO_INDEX' --include='*.py' . | grep -v '^./.venv/'
```

Expected: the two definitions in `config.py` plus call sites in `talaria/post_instagram.py` and `tests/test_render.py`. The `index=` argument only ever mattered for macOS `.ttc` collections, where Avenir Next's Demi Bold face sits at index 2. Every vendored file is a single-face `.ttf`.

- [ ] **Step 2: Drop the index parameter from `post_instagram.py`**

At lines 20–21:

```python
    return ImageFont.truetype(config.POST_FONT, config.POST_CIT_SIZE)
```

At line 72, change the helper signature from `def _fonte(caminho, tamanho, idx)` to:

```python
def _fonte(caminho, tamanho):
    return ImageFont.truetype(caminho, tamanho)
```

At lines 155 and 159, drop the third argument:

```python
    fnome = _fonte(config.POST_FONT, config.POST_NOME_SIZE)
    fcargo = _fonte(config.POST_MONO, config.POST_CARGO_SIZE)
```

- [ ] **Step 3: Drop it from the tests too**

In `tests/test_render.py`, both `ImageFont.truetype(config.POST_FONT, config.POST_CIT_SIZE, index=config.POST_FONT_INDEX)` calls (around lines 227 and 251) lose the `index=` argument. The comment at the old line 243 describing a candidate chain is now false — delete it; Task 4 Step 10 already rewrote the docstring that replaced it.

- [ ] **Step 4: Delete the constants**

Remove `POST_FONT_INDEX = 0` and `POST_MONO_INDEX = 0` from `talaria/config.py`, and shorten the comment above them to drop the `.ttc` explanation, which no longer describes anything in the file.

- [ ] **Step 5: Verify nothing references them**

```bash
cd /data/Code/next-video-shorts-pacote
grep -rn 'POST_FONT_INDEX\|POST_MONO_INDEX\|_primeira_fonte\|find_font\|_FONT_CANDIDATES\|_POST_FONT_CANDIDATES\|_POST_MONO_CANDIDATES\|_FONT_ARROBA' --include='*.py' . | grep -v '^./.venv/'
```

Expected: no output.

- [ ] **Step 6: Run the full suite**

Run: `.venv/bin/python -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`, with the same test count as Task 4 Step 11.

- [ ] **Step 7: Commit**

```bash
cd /data/Code/next-video-shorts-pacote
git add talaria/config.py talaria/post_instagram.py tests/test_render.py
git commit -m "refactor: drop the font index parameter

index= existed to reach Avenir Next Demi Bold at index 2 inside a macOS
.ttc collection. Every vendored font is a single-face .ttf, so the
parameter and both constants were always zero."
```

---

### Task 6: Remove the originating project's history references

**Files:**
- Modify: comments and docstrings across `talaria/` (26 modules), `tests/` (20 modules), `run.py`
- Modify: `tests/test_render.py:215`, `tests/test_post_instagram.py:30,212-213`, `tests/test_episodio.py:121`, `tests/test_textos.py:53,56` (fixture text)
- Test: whole suite

**Interfaces:**
- Consumes: the green suite from Task 5.
- Produces: no API change. Comments only, plus fixture strings whose rendered width is preserved.

**The rule: keep the measurement, drop the label.** These comments record real findings — `BASE_Y = 1560` is justified by an observed 5-line caption reaching y=1128 and invading the video; `audio.py:128` records that a defective clip measures −31/−28/−31 dB. The episode number is meaningless outside the originating project; the observation is why the constant has its value. Remove the label, keep the fact, and do not expand the comment to compensate.

- [ ] **Step 1: Enumerate every site**

```bash
cd /data/Code/next-video-shorts-pacote
grep -rnE '\bEP[0-9]+\b' --include='*.py' . | grep -v '^./.venv/'
grep -rnE '\bAP-[0-9]+\b|\bCA-[0-9]+\b' --include='*.py' . | grep -v '^./.venv/'
grep -rnE '(d[ae]|desta) casa\b|^.*\bA casa\b' --include='*.py' . | grep -v '^./.venv/'
grep -rniE 'norvik|norvic|ilusen|eosen|yusen|interior' --include='*.py' . | grep -v '^./.venv/'
```

Work through the lists file by file. Expect roughly 35 `EP[0-9]+` sites, 18 code-reference sites, 7 `casa` idiom sites.

- [ ] **Step 2: Strip the `EP` labels**

Delete the episode label, keep the sentence. Examples of the transformation, from the actual files:

- `talaria/config.py:1` — `"""Configuração central do pipeline. Valores validados no EP2.` → `"""Configuração central do pipeline.`
- `talaria/config.py:114` — `WHISPER_MODEL = "small"   # seguro p/ GPUs de 4GB; 'medium' estourou a GTX 1650 no EP2` → `WHISPER_MODEL = "small"   # seguro p/ GPUs de 4GB; 'medium' estourou uma GTX 1650`
- `talaria/audio.py:128` — `# Medido no EP8: corte defeituoso fica em -31/-28/-31 dB (estável); os` → `# Corte defeituoso fica em -31/-28/-31 dB (estável); os`
- `talaria/render.py:135` — `corte não alcança: no EP8 o último segmento ficava 1.4s na tela exibindo os` → `corte não alcança: o último segmento ficava 1.4s na tela exibindo os`
- `talaria/config.py:153` — the two lines `# Validado em protótipo manual e aprovado pelo gestor (EP9, corte1) antes de` / `# virar padrão do pipeline.` carry no constraint the code cannot show. Delete both.
- `talaria/encerramento.py:9-10` — same, delete both lines of `Formato validado em protótipo manual e aprovado pelo gestor antes de virar padrão (EP9, corte1).`

Where a comment's only content was the approval record, remove the comment rather than rewriting it. Where it records a measurement, keep the measurement.

- [ ] **Step 3: Delete the `AP-` and `CA-` codes**

These cite a checklist document that is not in the package, so they are dead cross-references. Delete the code, keep the rule. Examples:

- `talaria/publicado.py:5` — `faltou (AP-06 — pendência por item republicaria a que já foi).` → `faltou: pendência por item republicaria a que já foi.`
- `talaria/publicado.py:22` — `"""Lê o registro. Arquivo corrompido ABORTA — fail closed (AP-21).` → `"""Lê o registro. Arquivo corrompido ABORTA — fail closed.`
- `talaria/config.py:227` — `# mudaria o dia da publicação em silêncio (AP-13: data sempre com zona).` → `# mudaria o dia da publicação em silêncio — data sempre com zona.`
- `talaria/publish.py:18` — `# Limites das plataformas (AP-13): validados aqui, antes de chamar a API.` → `# Limites das plataformas: validados aqui, antes de chamar a API.`
- `tests/test_post_instagram.py:284` — `# AP-03: mesmo contrato do corte — não some em silêncio.` → `# Mesmo contrato do corte — não some em silêncio.`
- `tests/test_render.py:334` — `# CA-4 / AP-03: ausência não pode passar silenciosa.` → `# Ausência não pode passar silenciosa.`

- [ ] **Step 4: Neutralise the `casa` idiom — and only the idiom**

`casa` is also an ordinary Portuguese verb and a legitimate data entry. **Do not touch** `talaria/utils.py:134` (`"""Regex que casa o nome...`), `talaria/utils.py:213` (`RE_NE_* casa a forma falada`), or the `"casa"` string inside `_PALAVRAS_COMUNS` at `talaria/utils.py:158` — that entry is the Portuguese word for house appearing as a company name, which is exactly what the list is for.

Change only the possessive idiom:

- `talaria/caption.py:53` — `'{campo}' tem travessão — a casa não ` → `'{campo}' tem travessão — o canal não ` (a user-visible string; keep it one line and keep the length close)
- `talaria/calendario.py:29` — `"""A data corrente no fuso da casa — nunca a data ingênua da máquina."""` → `"""A data corrente no fuso configurado — nunca a data ingênua da máquina."""`
- `talaria/publish_youtube.py:5` — `no volume da casa` → `no volume típico`
- `talaria/ambiente.py:8` — `o `.env` desta casa tem uma dúzia de linhas` → `o `.env` tem uma dúzia de linhas`
- `talaria/episodio.py:17,103` and `tests/test_episodio.py:98` — `prompt da casa` → `prompt de materiais` (that is the prompt actually being referenced: `prompts/materiais.md`)
- `tests/test_caption.py:103` — `"""A casa não usa travessão em legenda: sai com cara de texto de IA."""` → `"""O canal não usa travessão em legenda: sai com cara de texto de IA."""`

- [ ] **Step 5: Replace the real company names in `talaria/utils.py`**

Lines 117–119 and 170 name actual guest companies. Replace with an invented name that still demonstrates the three variations the pattern handles — initial vowel, `y`/`i`, and the inserted `l`:

```python
# Trocas fonéticas que a transcrição automática faz em nome próprio. A mesma
# empresa sai como Vynka, Vinka, Vinca e Ilvinca — varia na vogal inicial, no
# y/i, e no `l` que a transcrição insere.
```

And at line 170, inside the `corrige_nomes` docstring:

```python
    o erro vai ao ar (Vinca/Ilvinca no lugar de Vynka).
```

- [ ] **Step 6: Replace the fixture text, preserving rendered width**

`tests/test_render.py:215` `CITACAO_DO_DESIGN` and `tests/test_post_instagram.py:212-213` hold the same quote, and its rendered *width* is what the 5-line assertions prove. Use the `neutro` variant measured in Task 4 Step 9 — identical in both files:

```python
    CITACAO_DO_DESIGN = ("A gente descobriu que não precisava mudar de cidade "
                         "para construir algo grande. Precisava ficar.")
```

The remaining fixtures carry no width constraint and can be reworded freely: `tests/test_post_instagram.py:30`, `tests/test_episodio.py:121` (`"temas": ["ecossistema do interior"]`), `tests/test_textos.py:53,56` (the `temas` entry and the `l1` assertion must stay equal to each other).

- [ ] **Step 7: Verify the greps come clean**

```bash
cd /data/Code/next-video-shorts-pacote
grep -rniE '\bEP[0-9]+\b|\bAP-[0-9]+\b|\bCA-[0-9]+\b|norvik|norvic|ilusen|eosen|yusen|nvshorts' --include='*.py' --include='*.md' . | grep -v '^./.venv/' | grep -v '^./docs/'
grep -rniE '(d[ae]|desta) casa\b' --include='*.py' . | grep -v '^./.venv/'
grep -rni 'interior' --include='*.py' . | grep -v '^./.venv/'
```

Expected: no output from any of the three. `docs/` is excluded from the first because the spec quotes these strings deliberately when explaining what was removed.

- [ ] **Step 8: Run the full suite**

Run: `.venv/bin/python -m unittest discover -s tests 2>&1 | tail -3`
Expected: `OK`, same count as Task 5. Comment edits cannot change behaviour; a changed result means an edit escaped a comment into code.

- [ ] **Step 9: Verify only comments and fixtures changed**

```bash
cd /data/Code/next-video-shorts-pacote
git diff --stat
git diff -U0 | grep -E '^[+-]' | grep -vE '^[+-]{3}' | grep -vE '^[+-]\s*(#|"""|\s*$)' | head -40
```

Review what this prints. Every line should be inside a docstring, a fixture string, or the one user-visible `caption.py` message. Any other executable change is unintended — revert it.

- [ ] **Step 10: Commit**

```bash
cd /data/Code/next-video-shorts-pacote
git add -A
git commit -m "docs: remove the originating project's history references

The comments cited episode numbers, an AP-/CA- checklist that is not in
this package, 'a casa' as an organisation, and five real guest company
names. The empirical facts they carried are kept -- the dB figures, the
y=1128 caption overflow, the 1.4s trailing segment -- because they are
why several constants have the values they do. Approval records were
deleted outright rather than reworded.

The reference quote in the render and Instagram fixtures was replaced
with text of equivalent rendered width, since the 5-line assertions
measure it."
```

---

### Task 7: Write `scripts/youtube_auth.py`

**Files:**
- Create: `scripts/youtube_auth.py`
- Create: `tests/test_youtube_auth.py`
- Test: `tests/test_youtube_auth.py`

**Interfaces:**
- Consumes: `google_auth_oauthlib` from Task 2.
- Produces: `scripts/youtube_auth.py` with `ESCOPO`, `valida_client_secret(caminho) -> dict` and `main(argv) -> int`. `talaria/publish_youtube.py` is not modified — this script exists to satisfy the instruction that module's error message already prints.

`talaria/publish_youtube.py:57` reads `json.load(f)["installed"]`, so a **Desktop** OAuth client is required. A Web-type client secret would complete the auth flow and then fail at first publish with a `KeyError`. The script must reject it up front.

- [ ] **Step 1: Write the failing test**

Create `tests/test_youtube_auth.py`:

```python
import importlib.util
import json
import os
import tempfile
import unittest

_RAIZ = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SPEC = importlib.util.spec_from_file_location(
    "youtube_auth", os.path.join(_RAIZ, "scripts", "youtube_auth.py"))
youtube_auth = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(youtube_auth)


def _escreve(d, conteudo):
    caminho = os.path.join(d, "cs.json")
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(conteudo)
    return caminho


class TestValidaClientSecret(unittest.TestCase):
    """O publish lê client_secret["installed"]: um client Web passa pelo
    consentimento e só quebra no primeiro upload. Falhar aqui é o ponto."""

    def test_aceita_client_desktop(self):
        with tempfile.TemporaryDirectory() as d:
            dados = {"installed": {"client_id": "x", "client_secret": "y",
                                   "token_uri": "https://oauth2.example/token"}}
            caminho = _escreve(d, json.dumps(dados))
            self.assertEqual(youtube_auth.valida_client_secret(caminho),
                             dados["installed"])

    def test_recusa_client_web_dizendo_o_que_fazer(self):
        with tempfile.TemporaryDirectory() as d:
            caminho = _escreve(d, json.dumps({"web": {"client_id": "x"}}))
            with self.assertRaises(SystemExit) as ctx:
                youtube_auth.valida_client_secret(caminho)
            self.assertIn("Desktop", str(ctx.exception))

    def test_recusa_json_invalido(self):
        with tempfile.TemporaryDirectory() as d:
            caminho = _escreve(d, "nao e json {")
            with self.assertRaises(SystemExit):
                youtube_auth.valida_client_secret(caminho)

    def test_recusa_arquivo_ausente(self):
        with self.assertRaises(SystemExit):
            youtube_auth.valida_client_secret("/nao/existe.json")

    def test_escopo_e_exatamente_o_do_publish(self):
        from talaria import publish_youtube
        self.assertEqual(youtube_auth.ESCOPO, publish_youtube.ESCOPO)


class TestMain(unittest.TestCase):
    def test_sem_argumento_explica_o_uso(self):
        with self.assertRaises(SystemExit):
            youtube_auth.main([])


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m unittest tests.test_youtube_auth -v`
Expected: collection error — `FileNotFoundError` from `spec_from_file_location`, because `scripts/youtube_auth.py` does not exist.

- [ ] **Step 3: Write the script**

Create `scripts/youtube_auth.py`:

```python
"""Autorização única do canal: imprime o YT_REFRESH_TOKEN para o .env.

Roda uma vez, na máquina de quem é dono do canal — o pipeline nunca abre
browser. O `publish` só recebe o refresh token pelo ambiente.
"""
from __future__ import annotations

import json
import os
import sys

ESCOPO = ["https://www.googleapis.com/auth/youtube.upload"]


def valida_client_secret(caminho: str) -> dict:
    """Devolve o bloco `installed`, ou sai explicando o que baixar.

    O publish lê client_secret["installed"]: um client do tipo Web passa pelo
    consentimento inteiro e só quebra no primeiro upload, depois de a agenda
    já contar com ele.
    """
    if not os.path.exists(caminho):
        raise SystemExit(f"{caminho} não existe.")
    try:
        with open(caminho, encoding="utf-8") as f:
            dados = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        raise SystemExit(f"{caminho} não é um JSON legível: {e}") from None
    if "installed" not in dados:
        tipo = ", ".join(sorted(dados)) or "vazio"
        raise SystemExit(
            f"{caminho} não é um client Desktop (tem: {tipo}). No Google "
            f"Cloud Console, crie a credencial OAuth com tipo de aplicativo "
            f"'Desktop app' e baixe o JSON dela."
        )
    return dados["installed"]


def main(argv: list) -> int:
    if len(argv) != 1:
        raise SystemExit(
            "uso: python scripts/youtube_auth.py <client_secret.json>"
        )
    caminho = argv[0]
    valida_client_secret(caminho)

    from google_auth_oauthlib.flow import InstalledAppFlow

    flow = InstalledAppFlow.from_client_secrets_file(caminho, ESCOPO)
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
    print(f"YT_CLIENT_SECRET_PATH={os.path.abspath(caminho)}")
    print(f"YT_REFRESH_TOKEN={creds.refresh_token}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run the tests**

Run: `.venv/bin/python -m unittest tests.test_youtube_auth -v`
Expected: PASS, 6 tests. No network is touched — every test stops at validation or argument handling, before the flow is imported.

- [ ] **Step 5: Confirm the usage string matches what `publish_youtube` tells the user to run**

```bash
cd /data/Code/next-video-shorts-pacote
grep -n 'youtube_auth' talaria/publish_youtube.py README.md .env.example
.venv/bin/python scripts/youtube_auth.py; echo "exit=$?"
```

Expected: `publish_youtube.py:54` prints `'python scripts/youtube_auth.py <client_secret.json>'`, and running the script with no argument prints exactly that usage and exits non-zero. If the two disagree, change the script to match the existing message — that message is already in a released error path.

- [ ] **Step 6: Run the full suite and commit**

```bash
cd /data/Code/next-video-shorts-pacote
.venv/bin/python -m unittest discover -s tests 2>&1 | tail -3
git add scripts/youtube_auth.py tests/test_youtube_auth.py
git commit -m "feat: add scripts/youtube_auth.py

README, .env.example and publish_youtube's own error message all tell the
operator to run this file; it was not in the package, and it is the only
documented route to YT_REFRESH_TOKEN.

Validates that the client secret is a Desktop client before opening the
browser, because publish_youtube reads client_secret['installed'] -- a Web
client would complete consent and then fail at the first upload."
```

---

### Task 8: Documentation, directory rename, final verification

**Files:**
- Modify: `README.md`, `requirements.txt:1`
- Test: whole suite, from the renamed directory

**Interfaces:**
- Consumes: everything above.
- Produces: the finished Phase 0 deliverable at `/data/Code/talaria`.

- [ ] **Step 1: Correct the README's false claims**

Three are known:

- The test count: it says `São 377 testes`. Replace with the real number from the final run in Step 4 below. Do this *after* Step 4 so the number is measured, not guessed.
- The `## Personalizar` table lists three customisation points. Add a fourth row for the vendored fonts: `| Fontes do render e do post | assets/fonts/ |`.
- Retitle the project from `# Video Shorts Pipeline` to `# Talaria`, with one line saying what it is.

Also state Portuguese is the current language and English is planned, so the next reader is not surprised — one sentence, linking `docs/specs/2026-09-21-phase-0-fork-and-debrand-design.md`.

The README already instructs `python scripts/youtube_auth.py <client_secret.json>` under `## Publicação`; that line was correct all along and only the file was missing. Do not add a second mention. Do check that it now also says the client must be a **Desktop** OAuth client, since that is the failure Task 7 guards.

- [ ] **Step 2: Fix the requirements header**

`requirements.txt:1` reads `# Pipeline Next-Video-Shorts — dependências Python`. Change to `# Talaria — dependências Python`.

- [ ] **Step 3: Verify the documented commands match the CLI**

```bash
cd /data/Code/next-video-shorts-pacote
grep -oE 'run\.py [a-z]+' README.md | sort -u
.venv/bin/python run.py --help 2>&1 | head -30
```

Every command named in the README must appear in `--help`. Report any mismatch rather than editing `run.py` — adding or renaming commands is out of scope for this phase.

- [ ] **Step 4: Full suite, and record the number the README will quote**

```bash
cd /data/Code/next-video-shorts-pacote
.venv/bin/python -m unittest discover -s tests 2>&1 | tail -3
```

Expected: `OK`, zero failures, zero errors, zero skips. Put this count into the README per Step 1.

- [ ] **Step 5: Commit the documentation**

```bash
cd /data/Code/next-video-shorts-pacote
git add README.md requirements.txt
git commit -m "docs: retitle to Talaria and correct the README

Test count was wrong (claimed 377), the customisation table did not
mention the vendored fonts, and nothing said the codebase is still
Portuguese with English planned."
```

- [ ] **Step 6: Push and confirm the remote is current**

```bash
cd /data/Code/next-video-shorts-pacote
git push
git status --short --branch
```

Expected: `## main...origin/main` with no divergence and a clean tree.

- [ ] **Step 7: Rename the directory**

This invalidates the working directory of any running shell, so it goes last and every command after it uses the new path.

```bash
mv /data/Code/next-video-shorts-pacote /data/Code/talaria
```

- [ ] **Step 8: Verify from the new location, in a fresh venv path**

The venv records absolute paths, so it must be rebuilt after the move rather than trusted.

```bash
cd /data/Code/talaria
rm -rf .venv
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m unittest discover -s tests 2>&1 | tail -3
git -C /data/Code/talaria status --short --branch
```

Expected: `OK` with the same count as Step 4, and a clean tree tracking `origin/main`.

- [ ] **Step 9: Final Phase 0 acceptance check**

```bash
cd /data/Code/talaria
grep -rniE '\bEP[0-9]+\b|\bAP-[0-9]+\b|\bCA-[0-9]+\b|norvik|norvic|ilusen|eosen|yusen|nvshorts|NVSHORTS' \
  --include='*.py' --include='*.md' --include='*.txt' . | grep -v '^./.venv/' | grep -v '^./docs/'
grep -rniE '(d[ae]|desta) casa\b' --include='*.py' . | grep -v '^./.venv/'
gh repo view talaria --json isPrivate --jq .isPrivate
ls assets/fonts/
```

Expected: no grep output, `true` for private, and five files in `assets/fonts/` (three fonts, two licences). Report the final test count and the commit list (`git log --oneline`) as the Phase 0 result.
