"""The weekly job (run by GitHub Actions every Sunday, or by hand).

  python3 weekly.py            make and schedule the next theme's week
  python3 weekly.py --dry-run  make the cards only: no GitHub push, nothing sent to Buffer
  python3 weekly.py --check    check every pre-written week in the quote bank for repeats

The quotes are written ahead of time (the "quote bank"): weeks/<date>-<theme>/lines.txt.
If the next theme has no lines.txt, the job fails, and GitHub emails Lat to say so.
"""
import os
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import make_week          # noqa: E402
import push_to_buffer     # noqa: E402

THEMES = HERE / "themes.txt"
LOW_BANK_WEEKS = 2        # warn when this many written weeks or fewer are left


def pending_themes():
    """[(line, folder Path)] for themes not yet marked [done], in order."""
    out = []
    for line in THEMES.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.endswith("[done]"):
            continue
        date, _, theme = s.partition(" ")
        out.append((line, HERE / "weeks" / f"{date}-{'-'.join(theme.lower().split())}"))
    return out


def check_bank():
    """Every written week must not repeat anything posted or anything earlier in the bank."""
    seen = make_week.read_used()
    ok, written = True, 0
    for _, week in pending_themes():
        lines = week / "lines.txt"
        if not lines.exists():
            break
        written += 1
        quotes = make_week.read_blocks(lines)
        if len(quotes) != 7:
            print(f"{week.name}: has {len(quotes)} quotes, expected 7")
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

    themes = pending_themes()
    if not themes:
        sys.exit("No themes left in themes.txt. Ask Claude to add more themes and quotes.")
    theme_line, week = themes[0]
    print(f"Next theme: {theme_line.strip()}  ->  {week.name}")

    if (week / "buffer.json").exists():
        print("Already scheduled. Nothing to do.")
        return
    if not (week / "lines.txt").exists():
        sys.exit(f"The quote bank is empty: no {week.name}/lines.txt. "
                 "Ask Claude to write the next batch of weeks.")

    if os.environ.get("GITHUB_ACTIONS") == "true":
        git("config", "user.name", "github-actions[bot]")
        git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")

    make_week.make(week)
    if dry:
        print("Dry run: cards made, nothing pushed or scheduled.")
        return

    push_to_buffer.push(week)                    # pushes images, schedules 21 posts (exits non-zero on failure)
    make_week.mark_used(week)
    text = THEMES.read_text(encoding="utf-8")
    THEMES.write_text(text.replace(theme_line, theme_line.rstrip() + " [done]", 1), encoding="utf-8")
    git("add", "--", "quotes_used.txt", "themes.txt", f"weeks/{week.name}")
    git("commit", "-q", "-m", f"Scheduled {week.name}")
    git("pull", "--rebase", "--autostash", "-q")
    git("push", "-q")

    _, left = check_bank()
    if left <= LOW_BANK_WEEKS:
        (HERE / "bank_low.txt").write_text(
            f"Only {left} week(s) of quotes left after {week.name}. "
            "Ask Claude to write the next batch.\n", encoding="utf-8")
        print("Quote bank is running low.")


if __name__ == "__main__":
    main()
