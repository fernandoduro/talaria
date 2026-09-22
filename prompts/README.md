# Prompts

The pipeline's prompts, versioned so they evolve with a history.

- `materials.md` — title, YouTube description and thumbnail text
- `clips.md` — selecting stretches for Reels/Shorts
- `posts.md` — choosing the quotes for the Instagram posts

The `brief --materials` and `brief --clips` commands assemble the reading
packet (prompt + episode metadata + transcript) the model consumes in a
session. `post --clips` does the same with `posts.md`, handing over the speech
of the already approved clips instead of the whole transcript.

## Placeholders

`brief` substitutes these markers before handing over the packet:

| Marker | Where | Content |
|---|---|---|
| `{{METADATA}}` | `materials.md`, `posts.md` | metadata from `episode.json` |
| `{{TRANSCRIPT}}` | `materials.md`, `clips.md` | transcript with `[mm:ss]` per segment |
| `{{CURATION}}` | `clips.md` | round state: approved, rejected, reasons, slots left |
| `{{CLIPS}}` | `posts.md` | literal speech of each approved clip that was selected |

## About these files

The prompts in this package are **generic skeletons**: they carry the
structure and the placeholders the code expects, but they bring no
ready-made editorial criteria. Every channel has to write its own — what
makes a clip good, what kind of quote works in the feed, what tone the
description takes. That content is what makes the difference in the result,
and it is built through use.

When adjusting a prompt, commit the change separately and record the reason
in the message: the history is what lets a change of prompt be correlated
with a change of result.
