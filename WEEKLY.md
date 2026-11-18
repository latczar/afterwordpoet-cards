# How the weekly posting runs

Everything runs on GitHub, in the public repo `latczar/afterwordpoet-cards`. Lat's PC can be off.

**Every Sunday at 11:00 UTC** (6pm Thailand, 11am UK), the GitHub workflow `.github/workflows/weekly.yml` runs `python3 weekly.py`, which:
1. takes the first theme in `themes.txt` without `[done]`
2. makes that week's cards from the pre-written `weeks/<date>-<theme>/lines.txt` (the quote bank)
3. pushes them to the repo and schedules 21 posts in Buffer: Instagram and Facebook at 9pm UK, TikTok at midnight UK as a phone reminder
4. marks the quotes as used and the theme as `[done]`, then commits

If something fails, GitHub emails Lat. When 2 or fewer written weeks are left, it opens a GitHub issue called "Quote bank running low".

The Buffer key is stored as the repo secret `BUFFER_API_KEY`. Locally it's in `.env`, which is never committed.

## Refilling the quote bank (a job for Claude, every couple of months)
1. Add new themes to the end of `themes.txt`, one per week (`YYYY-MM-DD theme`, Mondays).
2. For each one, write `weeks/<date>-<theme-with-dashes>/lines.txt` with 7 quotes, one block per card and a blank line between blocks.
   - Above all, super relatable: everyday moments people recognise in themselves. Mostly love or hope, but not every quote has to be.
   - Match the voice in `quotes_used.txt`: first person, plain everyday words, 2–4 short lines of at most about 28 characters each, with a quiet turn at the end.
   - British spelling, no emojis, no hashtags.
   - No clichés or filler: no "journey", "tapestry", "embrace", "healing isn't linear", "you are enough" or "the universe".
   - If a quote sounds like a greeting card, rewrite it.
3. Run `py -3.13 weekly.py --check` until it passes. Show Lat the quotes, then commit and push.

## Running by hand
- In GitHub, go to Actions > Weekly posts > Run workflow. "Dry run" is ticked by default, which only makes the cards.
- Locally: `py -3.13 weekly.py --dry-run`
