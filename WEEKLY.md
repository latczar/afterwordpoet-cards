# How the weekly posting runs

Everything runs on GitHub, in the public repo `latczar/afterwordpoet-cards`. Lat's PC can be off.

**Every day at 11:00 UTC** (6pm Thailand, 11am UK), the GitHub workflow `.github/workflows/weekly.yml` runs `python3 weekly.py`. It keeps the **next 3 days** of posts queued in Buffer, which keeps the free plan under its 10-post limit:
- One theme per week (`themes.txt`), with **1 quote a day** pre-written in `weeks/<date>-<theme>/lines.txt` (the quote bank). A theme lasts as many days as the gap to the next theme's date.
- Each day's quote goes to Instagram and Facebook at 9pm UK and to TikTok at midnight UK.
- From 1 Feb 2027 the "part 2" weeks reuse each theme with its second set of quotes. Spare Christmas and New Year quotes are in `weeks/_reserve/` for next December.
- TikTok posts go out as Buffer phone reminders so Lat can add a trending sound.
- When a week's cards are first needed, it makes them, records the quotes as used and marks the theme `[done]`.

If something fails, GitHub emails Lat. When 2 or fewer written weeks are left, it opens a GitHub issue called "Quote bank running low".

The Buffer key is stored as the repo secret `BUFFER_API_KEY`. Locally it's in `.env`, which is never committed.

## Refilling the quote bank (a job for Claude, every couple of months)
1. Add new themes to the end of `themes.txt`, one per week (`YYYY-MM-DD theme`), each starting the day after the last one ends.
2. For each one, write `weeks/<date>-<theme-with-dashes>/lines.txt` with 7 quotes (1 a day), one block per card and a blank line between blocks.
   - Above all, super relatable: everyday moments people recognise in themselves. Mostly love or hope, but not every quote has to be.
   - Match the voice in `quotes_used.txt`: first person, plain everyday words, 2–4 short lines of at most about 28 characters each, with a quiet turn at the end.
   - British spelling, no emojis, no hashtags.
   - No clichés or filler: no "journey", "tapestry", "embrace", "healing isn't linear", "you are enough" or "the universe".
   - If a quote sounds like a greeting card, rewrite it.
3. Run `py -3.13 weekly.py --check` until it passes. Show Lat the quotes, then commit and push.

## Running by hand
- In GitHub, go to Actions > Weekly posts > Run workflow. "Dry run" is ticked by default, which only makes the cards.
- Locally: `py -3.13 weekly.py --dry-run`
