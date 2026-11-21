"""Daily job (GitHub Actions runs it every day): keep the next 3 days of posts queued in Buffer.

  python3 weekly.py            queue anything due in the next 72 hours that isn't queued yet
  python3 weekly.py --dry-run  make any needed cards and show the plan; push and schedule nothing
  python3 weekly.py --check    check the quote bank for repeats and missing quotes

One theme per week: weeks/<date>-<theme>/lines.txt holds 1 quote per day (normally 7):
Instagram + Facebook at 9pm UK, TikTok at midnight UK. days = gap to the next theme in themes.txt.
Only ~3 days are queued at a time, so Buffer's free plan (10 queued posts per account) is never full.
If the quotes for an upcoming week are missing, the job fails and GitHub emails Lat.
Phone alerts go through the ntfy app (topic in the NTFY_TOPIC secret): one when each new theme is
queued, plus failures and a low quote bank (sent from the workflow). Nothing else, to keep it quiet.
"""
import json
import os
import subprocess
import sys
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_week          # noqa: E402
import push_to_buffer as pb  # noqa: E402

THEMES = HERE / "themes.txt"
HORIZON = timedelta(hours=72)
LOW_BANK_WEEKS = 2        # open a GitHub issue when this many written weeks or fewer are left


def all_themes():
    """[(line, start date, folder)] for every theme, in order, done or not."""
    out = []
    for line in THEMES.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        d, _, theme = s.replace("[done]", "").strip().partition(" ")
        out.append((line, date.fromisoformat(d), HERE / "weeks" / f"{d}-{'-'.join(theme.lower().split())}"))
    return out


def notify(title, message, tags=""):
    """Send a phone alert through ntfy. Skipped when NTFY_TOPIC isn't set; never stops the job."""
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        return
    headers = {"Title": title}
    if tags:
        headers["Tags"] = tags
    try:
        req = urllib.request.Request("https://ntfy.sh/" + topic, data=message.encode("utf-8"),
                                     headers=headers, method="POST")
        urllib.request.urlopen(req, timeout=15).read()
    except Exception as e:
        print(f"  (phone alert not sent: {e})")


def last_post_day(themes):
    """Last day with quotes written: the end of the last week in a row that has a lines.txt."""
    last = None
    for i, (_, start, week) in enumerate(themes):
        if not (week / "lines.txt").exists():
            break
        last = start + timedelta(days=week_days(themes, i) - 1)
    return last


def week_days(themes, i):
    start = themes[i][1]
    nxt = themes[i + 1][1] if i + 1 < len(themes) else start + timedelta(days=7)
    return max(1, min(7, (nxt - start).days))


def slots(start, days, quotes):
    """[(card, service, due UTC, quote index)] for a week: one quote a day on every platform."""
    out = []
    for d in range(min(days, len(quotes))):
        day = start + timedelta(days=d)
        for svc in ("instagram", "facebook", "tiktok"):
            out.append((f"{d + 1:02d}.png", svc, pb.uk_to_utc(day, *pb.POST_TIMES[svc]), d))
    return out


def check_bank():
    """Upcoming weeks: right number of quotes, no repeats of anything posted or earlier in the bank."""
    themes = all_themes()
    seen = make_week.read_used()
    ok, written = True, 0
    for i, (line, start, week) in enumerate(themes):
        if line.strip().endswith("[done]"):
            continue
        lines = week / "lines.txt"
        if not lines.exists():
            break
        written += 1
        quotes = make_week.read_blocks(lines)
        want = week_days(themes, i)
        if len(quotes) != want:
            print(f"{week.name}: has {len(quotes)} quotes, needs {want} (1 a day)")
            ok = False
        for n, o, r in make_week.find_clashes(quotes, seen):
            print(f"{week.name}: {int(r * 100)}% close\n  NEW: {n!r}\n  OLD: {o!r}")
            ok = False
        seen += quotes
    print(f"Quote bank: {written} week(s) written ahead.")
    return ok, written


def git(*args):
    subprocess.run(["git", *args], cwd=HERE, check=True)


def main():
    dry = "--dry-run" in sys.argv
    if "--check" in sys.argv:
        ok, _ = check_bank()
        sys.exit(0 if ok else 1)
    if "--render-test" in sys.argv:          # prove this machine can draw a photo card and a colour card
        import tempfile
        with tempfile.TemporaryDirectory() as t:
            tmp = Path(t)
            b = make_week.find_browser()
            make_week.check_font(b, tmp)
            make_week.check_photos(b, tmp, "render-test-hoping")
            for i in (0, 1):
                out = tmp / f"test{i}.png"
                make_week.render(b, make_week.card_html("Render test. Still here.", i, 1080, 1920, "render-test-hoping"),
                                 out, 1080, 1920, tmp)
                print(f"  render test: {'photo' if i == 0 else 'colour'} card OK ({out.stat().st_size // 1024} KB)")
        return

    if os.environ.get("GITHUB_ACTIONS") == "true":
        git("config", "user.name", "github-actions[bot]")
        git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")

    channels = json.loads(pb.CHANNELS_FILE.read_text(encoding="utf-8"))
    caption = pb.CAPTION.read_text(encoding="utf-8").strip() if hasattr(pb, "CAPTION") else \
        (HERE / "caption.txt").read_text(encoding="utf-8").strip()
    now = datetime.now(timezone.utc)
    themes = all_themes()
    failures, scheduled = 0, 0

    for i, (line, start, week) in enumerate(themes):
        days = week_days(themes, i)
        if pb.uk_to_utc(start + timedelta(days=days), 1, 0) < now:
            continue                                   # week is over
        if pb.uk_to_utc(start, 0, 0) > now + HORIZON:
            break                                      # too far ahead for now
        if not (week / "lines.txt").exists():
            sys.exit(f"The quote bank is empty: no {week.name}/lines.txt. Ask Claude to write the next weeks.")
        quotes = make_week.read_blocks(week / "lines.txt")
        record_file = week / "buffer.json"
        record = json.loads(record_file.read_text(encoding="utf-8")) if record_file.exists() else []
        have = {(r["card"], r["service"]) for r in record}
        todo = [s for s in slots(start, days, quotes)
                if now + timedelta(minutes=15) < s[2] <= now + HORIZON
                and (s[0], s[1]) not in have and s[1] in channels]
        if not todo:
            continue
        print(f"{week.name}: {len(todo)} post(s) to queue")

        cards = sorted((week / "tiktok").glob("[0-9][0-9].png")) if (week / "tiktok").exists() else []
        if len(cards) != len(quotes):
            make_week.make(week)                       # checks repeats + font, draws the cards
        if dry:
            for card, svc, due, _ in todo:
                print(f"  would queue {card} -> {svc} at {due:%a %d %b %H:%M} UTC")
            continue

        make_week.mark_used(week)
        new_theme = not line.strip().endswith("[done]")
        if new_theme:
            text = THEMES.read_text(encoding="utf-8")
            THEMES.write_text(text.replace(line, line.rstrip() + " [done]", 1), encoding="utf-8")
        urls = pb.publish_images(week)
        for card, svc, due, qi in sorted(todo, key=lambda s: s[2]):
            try:
                pid = pb.create_post(svc, channels[svc]["id"], week, card, quotes[qi], due, urls, caption)
                record.append({"card": card, "service": svc, "postId": pid,
                               "dueAt": due.strftime("%Y-%m-%dT%H:%M:%SZ")})
                record_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
                scheduled += 1
                print(f"  queued {card} -> {svc} at {due:%a %d %b %H:%M} UTC")
            except Exception as e:                     # keep going; report at the end
                failures += 1
                print(f"  FAILED {card} -> {svc}: {e}")
        if new_theme:
            name = week.name[11:].replace("-", " ")
            end = last_post_day(themes)
            notify(f"New theme queued: {name}",
                   f"Starts {start:%a %d %b}, {min(days, len(quotes))} posts on Instagram, Facebook and TikTok. "
                   f"Quotes are written up to {end:%a %d %b %Y}." if end else f"Starts {start:%a %d %b}.",
                   tags="memo")
        git("add", "--", "quotes_used.txt", "themes.txt", f"weeks/{week.name}")
        git("commit", "-q", "-m", f"Queue posts for {week.name}")
        git("pull", "--rebase", "--autostash", "-q")
        git("push", "-q")

    print(f"Done: {scheduled} queued, {failures} failed.")
    _, left = check_bank()
    if left <= LOW_BANK_WEEKS and not dry:
        (HERE / "bank_low.txt").write_text(
            f"Only {left} week(s) of quotes are written ahead. Ask Claude to write the next batch "
            "(see WEEKLY.md).\n", encoding="utf-8")
    if failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
