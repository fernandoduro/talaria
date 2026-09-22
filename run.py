#!/usr/bin/env python3
"""Talaria — CLI orchestrator.

Per-video flow (driven by a language model, with manual curation):

  1. ingest     : downloads the video + converts the .txt transcript -> transcript.json
                  (or acquire + transcribe, when the transcript comes from Whisper)
  2. [episode.json]: the manager fills in the episode metadata
  3. brief      : composes the reading packet (--clips or --materials) for the model
  4. curate     : iterative curation state; --export writes moments.json
  5. render     : produces the 9:16 clips with captions for the chosen platforms
  6. thumb      : produces the thumbnail (texts from the JSON, flags override)
  7. post       : Instagram quote posts; --clips composes the packet,
                  --generate renders the PNGs from posts.json

Examples:
  python run.py acquire  --project ep2 --src "https://youtu.be/VIDEO_ID"
  python run.py transcribe --project ep2 --src "https://youtu.be/VIDEO_ID"
  python run.py render   --project ep2 --youtube --instagram
  python run.py ingest   --project ep2 --src "https://youtu.be/VIDEO_ID" \\
      --transcript ~/Downloads/ep2.txt
  python run.py brief    --project ep2 --clips
  python run.py curate   --project ep2 --target 5
  python run.py thumb    --project ep2 --frame-at 1745       # texts from the JSON
  python run.py post     --project ep2 --clips 1,3
  python run.py post     --project ep2 --generate

  # acquire + transcribe in one go (for before curation):
  python run.py prep     --project ep2 --src "https://youtu.be/VIDEO_ID"
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

from talaria import (acquire, environment, brief, schedule, curation,
                      episode, layout, post_instagram, published, publish,
                      render, texts, thumbnail, transcribe, txt_parse)

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECTS = os.path.join(ROOT, "projects")

# `.env` enters the environment before any command: the publishing modules read
# credentials from os.environ, and without this the filled-in file never reached
# them — publish complained about a missing variable with the answer open on the
# manager's screen.
environment.load()


def project_dir(slug: str) -> str:
    """The project path, reorganising the old layout when needed.

    Every command passes through here, so an episode created before the split by
    nature (source/decisions/briefs/publish) is migrated on the first run,
    without being asked. `layout.migrate` is idempotent: later runs move nothing
    and print nothing.
    """
    pd = os.path.join(PROJECTS, slug)
    moved = layout.migrate(pd)
    if moved:
        print(f"[layout] project reorganised ({len(moved)} items):")
        for origin, destination in moved:
            print(f"         {origin} -> {destination}")
    return pd


def platforms_from_args(args) -> list[str]:
    p = []
    if args.youtube:
        p.append("youtube")
    if args.instagram:
        p.append("instagram")
    if not p:  # default: both
        p = ["youtube", "instagram"]
    return p


def cmd_acquire(args):
    pd = project_dir(args.project)
    acquire.acquire(args.src, pd)


def cmd_transcribe(args):
    pd = project_dir(args.project)
    video = layout.video(pd)
    if not os.path.exists(video):
        sys.exit(f"{video} does not exist. Run 'acquire' first.")
    transcribe.transcribe(args.src, video, pd, model=args.whisper_model)


def cmd_prep(args):
    pd = project_dir(args.project)
    acquire.acquire(args.src, pd)
    video = layout.video(pd)
    transcribe.transcribe(args.src, video, pd, model=args.whisper_model)
    print(f"\n>>> Ready for curation. Read {layout.transcript_txt(pd)} and "
          f"create {layout.moments(pd)}, then run 'render'.")


def cmd_render(args):
    pd = project_dir(args.project)
    if not os.path.exists(layout.moments(pd)):
        sys.exit(f"{layout.moments(pd)} does not exist. Do the curation first.")
    render.render_all(pd, platforms_from_args(args),
                      only=args.only.split(",") if args.only else None)


def cmd_thumb(args):
    """Builds the thumbnail: the base comes from the JSON, flags override."""
    pd = project_dir(args.project)

    # Without --frame-at it suggests instants inside the approved clips: that is
    # where the guest is speaking with energy. The choice stays visual.
    if args.frame_at is None:
        mpath = layout.moments(pd)
        if os.path.exists(mpath):
            with open(mpath, encoding="utf-8") as f:
                sug = thumbnail.suggest_frames(json.load(f))
            if sug:
                print("[thumb] candidates (inside the approved clips): "
                      + ", ".join(f"{t:.0f}s" for t in sug))
                print("[thumb] extract one and choose: "
                      f"python run.py thumb --project {args.project} --frame-at <s>")
        sys.exit("[thumb] pass --frame-at <seconds>")
    video = layout.video(pd)

    # The extracted frame is intermediate, not product — it goes to a real temp
    # file instead of littering the project root (the old `_thumb_frame.jpg`).
    fd, frame = tempfile.mkstemp(suffix=".jpg", prefix="talaria_thumb_")
    os.close(fd)
    try:
        thumbnail.extract_frame(video, args.frame_at, frame)

        # The base comes from episode.json/texts.json; explicit flags override.
        try:
            base = texts.build_kwargs(pd)
        except FileNotFoundError:
            base = {"badge": "", "headline_l1": "", "headline_l2": "",
                    "credits": "", "subtitle": ""}
        for flag, field in (("badge", "badge"), ("l1", "headline_l1"), ("l2", "headline_l2"),
                            ("credits", "credits"), ("subtitle", "subtitle")):
            value = getattr(args, flag, "")
            if value:
                base[field] = value

        thumbnail.build_thumbnail(frame, layout.ensure_dir(layout.thumbnail(pd)), **base)
    finally:
        if os.path.exists(frame):
            os.remove(frame)


def cmd_ingest(args):
    """Downloads the video and converts the .txt transcript to transcript.json."""
    pd = project_dir(args.project)

    # Validates the transcript BEFORE downloading: a wrong path used to waste
    # the whole video download only to fail later in parse_txt.
    if args.transcript and not os.path.exists(args.transcript):
        sys.exit(f"transcript not found: {args.transcript}")

    os.makedirs(pd, exist_ok=True)

    acquire.acquire(args.src, pd)

    if args.transcript:
        video = layout.video(pd)
        dur = None
        try:
            out = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "csv=p=0", video],
                capture_output=True, text=True, check=True).stdout.strip()
            dur = float(out)
        except Exception:  # noqa: BLE001
            print("[ingest] could not measure the duration; last segment "
                  "estimated.")
        segs = txt_parse.parse_txt(args.transcript, total_duration=dur)
        transcript_path = layout.ensure_dir(layout.transcript(pd))
        with open(transcript_path, "w", encoding="utf-8") as f:
            json.dump({"segments": segs}, f, ensure_ascii=False, indent=2)
        print(f"[ingest] {len(segs)} segments -> {transcript_path}")
    else:
        print("[ingest] no --transcript; run 'transcribe' to use Whisper.")

    ep_path = layout.episode(pd)
    if not os.path.exists(ep_path):
        episode.save(pd, episode.template())
        print(f"[ingest] template created -> {ep_path} (fill it in before "
              f"the brief)")


def cmd_brief(args):
    """Assembles the reading packet (materials or clips) for the model."""
    pd = project_dir(args.project)
    # --clips and --materials are mutually exclusive (see the mutually exclusive
    # group); with neither, the default is 'materials'.
    kind = "clips" if args.clips else "materials"
    out = brief.build(pd, kind)
    print(f"[brief] {kind} -> {out}")


def _segments(pd):
    """The transcript segments, or [] when the project has none yet."""
    path = layout.transcript(pd)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f).get("segments", [])


def cmd_curate(args):
    """Shows the curation state and exports moments.json once it closes."""
    pd = project_dir(args.project)
    already_existed = os.path.exists(layout.curation(pd))
    state = curation.load(pd, target=args.target)

    # An already-written state governs the target — --target only counts when
    # the curation is created. Without this warning, `curate --target 8` over a
    # state with target 5 silently carried on with the old target.
    if already_existed and state["target"] != args.target:
        print(f"[curate] warning: the recorded state has target "
              f"{state['target']}, ignoring --target {args.target}")

    if args.export:
        try:
            path = curation.save_moments(pd, state)
        except ValueError as e:   # nothing approved yet: operator error, not a bug
            sys.exit(f"[curate] {e}")
        print(f"[curate] {len(state['approved'])} clips -> {path}")
        return

    # Revalidates what is already approved: the state may have been written
    # before a new rule existed (end on a complete sentence, overlap between
    # approved clips). Without this the problem only shows in the rendered video.
    segs = _segments(pd)
    if segs:
        if not curation.attribution_trustworthy(segs):
            print("[curate] warning: speaker attribution is inconsistent in "
                  "this episode — prominence and opening were not checked; "
                  "check them in the rendered video.")
        for c in state.get("approved", []):
            ok, msgs = curation.validate_clip((c["start"], c["end"]), segs, {})
            if not ok:
                print(f"[curate] !! {c.get('slug')}: {'; '.join(msgs)}")
            for a in curation.clip_warnings((c["start"], c["end"]), segs):
                print(f"[curate] ?  {c.get('slug')}: {a}")

    comp = curation.composition(state)
    print(f"[curate] round {state['rounds']} | "
          f"{len(state['approved'])}/{state['target']} approved | "
          f"{len(state['rejected'])} rejected")
    print("[curate] composition: "
          + ", ".join(f"{t}={n}" for t, n in comp.items()))
    missing = curation.missing_kinds(state)
    if missing:
        print(f"[curate] missing kinds: {', '.join(missing)}")
    ms = curation.reasons(state)
    if ms:
        print(f"[curate] accumulated rejection reasons: {'; '.join(ms)}")
    if curation.is_closed(state):
        print("[curate] target met — run with --export to generate "
              "moments.json")
    else:
        print(f"[curate] {curation.slots_left(state)} clips to go")
    curation.save(pd, state)


def cmd_post(args):
    """Two steps: --clips composes the reading packet, --generate renders."""
    pd = project_dir(args.project)

    if args.generate:
        try:
            generated = post_instagram.generate(pd)
        except (FileNotFoundError, ValueError) as e:
            sys.exit(str(e))
        print(f"\n{len(generated)} image(s) in {layout.posts_png(pd)}/")
        return

    moments_path = layout.moments(pd)
    if not os.path.exists(moments_path):
        sys.exit(f"{moments_path} does not exist. Run 'curate --export' first.")
    with open(moments_path, encoding="utf-8") as f:
        moments = json.load(f)

    if args.clips:
        try:
            wanted = {int(n) for n in args.clips.split(",") if n.strip()}
        except ValueError:
            sys.exit(f"--clips takes comma-separated numbers "
                     f"(e.g. 1,3) — got {args.clips!r}")
        chosen = [m for i, m in enumerate(moments, start=1) if i in wanted]
        if not chosen:
            sys.exit(f"no clip with the numbers {sorted(wanted)} "
                     f"(the episode has {len(moments)})")
    else:
        chosen = moments

    out = brief.build_posts(pd, chosen)
    print(f"\n>>> Read {out}, choose the quotes with me and write "
          f"{layout.posts(pd)}. Then run 'post --generate'.")


def cmd_publish(args):
    """Publishes what the schedule calls for today (or --only, off-date)."""
    pd = project_dir(args.project)
    only = ([s.strip() for s in args.only.split(",") if s.strip()]
            if args.only else None)
    platforms = ([s.strip() for s in args.platform.split(",") if s.strip()]
                   if args.platform else None)
    try:
        results = publish.execute(pd, only=only, platforms=platforms)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        sys.exit(str(e))

    if not results:
        print(f"[publish] nothing scheduled for today "
              f"({schedule.today().isoformat()})")
        return

    today = schedule.today().isoformat()
    for r in results:
        if r["date"] < today:
            # Shows the ORIGINAL date: the manager needs to see it ran late.
            print(f"[publish]    ({r['slug']} was scheduled for {r['date']})")
    for pl in ("youtube_shorts", "instagram_reels", "instagram_posts"):
        by_pl = [r for r in results if r["platform"] == pl]
        if not by_pl:
            continue
        ok = [r for r in by_pl if r["ok"]]
        bad = [r for r in by_pl if not r["ok"]]
        line = f"[publish] {pl}: {len(ok)} ok, {len(bad)} failed"
        if bad:
            line += " (" + "; ".join(f"{r['slug']}: {r['error']}"
                                      for r in bad) + ")"
        print(line)

    # A live piece whose record failed: published.json does not know about it,
    # so the next publish would send it again. It is the most important warning
    # of the run and comes last, where the manager looks.
    no_record = [r for r in results if r.get("record_failed")]
    if no_record:
        print(f"\n[publish] !! {len(no_record)} piece(s) LIVE and absent "
              f"from {layout.published(pd)}:")
        for r in no_record:
            print(f"[publish]    {r['platform']} {r['slug']} -> id {r['id']}"
                  f" ({r['url'] or 'no url'})")
        print("[publish]    Add these ids to published.json BEFORE running "
              "publish again, or the pieces go out twice.")

    if any(not r["ok"] for r in results) or no_record:
        sys.exit(1)


def cmd_schedule(args):
    """Shows the schedule with each item's status, publishing nothing."""
    pd = project_dir(args.project)
    try:
        items = schedule.load(pd)
        reg = published.load(pd)
    except (FileNotFoundError, ValueError, RuntimeError) as e:
        sys.exit(str(e))
    today = schedule.today()
    for item in items:
        pls = schedule.platforms_of(item)
        done = [pl for pl in pls
                  if published.is_published(reg, pl, item["slug"])]
        d = schedule.date_of(item)
        if len(done) == len(pls):
            status = "✓ published"
        elif done:
            missing = [p for p in pls if p not in done]
            status = f"partial — {', '.join(missing)} missing"
        elif d < today:
            status = "OVERDUE"
        elif d == today:
            status = "pending today"
        else:
            status = "future"
        print(f"  {item['date']}  {item['kind']:<5}  "
              f"{item['slug']:<32}  {status}")


def main():
    p = argparse.ArgumentParser(
        description="Talaria — vertical clip pipeline")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_common(sp):
        sp.add_argument("--project", required=True,
                        help="project slug (folder under projects/)")

    sp = sub.add_parser("acquire", help="download/copy the video")
    add_common(sp); sp.add_argument("--src", required=True); sp.set_defaults(func=cmd_acquire)

    sp = sub.add_parser("transcribe",
                        help="transcribe (YouTube captions or Whisper)")
    add_common(sp); sp.add_argument("--src", required=True)
    sp.add_argument("--whisper-model", default=None); sp.set_defaults(func=cmd_transcribe)

    sp = sub.add_parser("prep",
                        help="acquire + transcribe (to run before curation)")
    add_common(sp); sp.add_argument("--src", required=True)
    sp.add_argument("--whisper-model", default=None); sp.set_defaults(func=cmd_prep)

    sp = sub.add_parser("render", help="render the clips in moments.json")
    add_common(sp)
    sp.add_argument("--youtube", action="store_true",
                    help="produce YouTube Shorts")
    sp.add_argument("--instagram", action="store_true",
                    help="produce Instagram Reels")
    sp.add_argument("--only", default=None,
                    help="render only these slugs (comma-separated)")
    sp.set_defaults(func=cmd_render)

    sp = sub.add_parser("thumb", help="produce the YouTube thumbnail")
    add_common(sp)
    sp.add_argument("--frame-at", type=float,
                    help="second of the background frame; without it, "
                         "candidates are suggested")
    sp.add_argument("--badge", default="")
    sp.add_argument("--l1", default="", help="first headline line (white)")
    sp.add_argument("--l2", default="", help="second headline line (orange)")
    sp.add_argument("--credits", default="")
    sp.add_argument("--subtitle", default="")
    sp.set_defaults(func=cmd_thumb)

    sp = sub.add_parser("ingest",
                        help="download the video + convert the .txt transcript")
    add_common(sp)
    sp.add_argument("--src", required=True,
                    help="Drive link to the file, or a local path")
    sp.add_argument("--transcript", default=None,
                    help="path of the .txt with timestamps")
    sp.set_defaults(func=cmd_ingest)

    sp = sub.add_parser("brief",
                        help="assemble the reading packet for the model")
    add_common(sp)
    g = sp.add_mutually_exclusive_group()
    g.add_argument("--materials", action="store_true",
                   help="title/description prompt (default)")
    g.add_argument("--clips", action="store_true",
                   help="clip-selection prompt")
    sp.set_defaults(func=cmd_brief)

    sp = sub.add_parser("curate", help="iterative curation state")
    add_common(sp)
    sp.add_argument("--target", type=int, default=5,
                    help="how many clips to approve")
    sp.add_argument("--export", action="store_true",
                    help="generate moments.json")
    sp.set_defaults(func=cmd_curate)

    sp = sub.add_parser("post", help="Instagram quote posts")
    add_common(sp)
    sp.add_argument("--clips", default="",
                    help="clip numbers, e.g. 1,3 (empty = all)")
    sp.add_argument("--generate", action="store_true",
                    help="render from posts.json")
    sp.set_defaults(func=cmd_post)

    sp = sub.add_parser("publish",
                        help="publish what the schedule calls for today")
    add_common(sp)
    sp.add_argument("--only", default="",
                    help="specific slugs, off the scheduled date "
                         "(e.g. clip1,quote_x) — never republishes what "
                         "already went out")
    sp.add_argument("--platform", default="",
                    help="publish only to these platforms (e.g. "
                         "youtube_shorts) — the rest of the clip stays "
                         "pending for later")
    sp.set_defaults(func=cmd_publish)

    sp = sub.add_parser("schedule",
                        help="show the schedule and each item's status")
    add_common(sp)
    sp.set_defaults(func=cmd_schedule)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
