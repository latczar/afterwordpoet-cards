# afterwordpoet post generator

**This runs by itself on GitHub every day** (queues the next 3 days in Buffer). See `WEEKLY.md`. Quotes are written ahead in `weeks/*/lines.txt`, currently up to Fri 2 April 2027.

Phone alerts come through the ntfy app (topic in the `NTFY_TOPIC` repo secret): one when each new theme is queued, one if the daily job fails, one when the quotes are running low. Nothing else.

Makes a week of quote cards in the afterwordpoet style: handwritten font, pastel paper or soft sunset background, "- afterwordpoet" signature. The cards are drawn by code (Microsoft Edge saves each one as a PNG), not by an image AI, so the text is always exactly what's in `lines.txt`.

## Files
- `themes.txt`: one theme per week. Edit freely.
- `quotes_used.txt`: everything already posted. New quotes that come too close are refused.
- `caption.txt`: the caption used on every post.
- `promo/`: put your book images here (for example the three books on the bedsheet). One goes into each week.
- `backgrounds/` (optional): drop your own background photos here and the cards use them instead of the built-in paper and sunset looks.
- `weeks/<date>-<theme>/`: each week's `lines.txt`, `tiktok/` cards (1080x1920), `ig/` cards (1080x1350), `caption.txt` and `preview.html`.
- `WEEKLY.md`: the steps the weekly automatic run follows.

## Make a week by hand
```
py -3.13 make_week.py weeks/2026-11-23-letting-go
py -3.13 make_week.py --mark-used weeks/2026-11-23-letting-go
```
Run the second command once the week is posted, so those quotes are never repeated.

## Send a week to Buffer
```
py -3.13 push_to_buffer.py --setup                                 (once: finds your channels)
py -3.13 push_to_buffer.py --test weeks/2026-11-23-letting-go      (one draft per channel)
py -3.13 push_to_buffer.py weeks/2026-11-23-letting-go             (schedules the week)
```
- Needs `BUFFER_API_KEY=...` in `.env` here. Create the key at publish.buffer.com/settings/api. Never share it.
- Each post is the quote card, then the books slide, with `caption.txt`. One post a day, starting on the date in the week's folder name: Instagram and Facebook at 9pm UK (4pm New York), TikTok at midnight UK (7pm New York, 7am Thailand). Change `POST_TIMES` at the top of `push_to_buffer.py`.
- TikTok posts arrive on your phone as a Buffer reminder. Open it, tap Add sound (the Recommended list shows trending sounds) and post. Keep TikTok a personal or creator account: business accounts can't use trending songs.
- Buffer needs public image links. This folder *is* the public repo github.com/latczar/afterwordpoet-cards (it pushes with latczar's `gh` login), and the links point at the exact commit, so a re-made card is never served stale.
- `buffer.json` in a week's folder records what was sent, so a week can't go out twice by accident (use `--force` to override).

## Settings (top of make_week.py)
- `FONT`: any Google Font name.
- `SIMILAR`: how strict the repeat check is (0.72 by default; higher allows closer matches).

`.render-profile/` is Edge's scratch profile for drawing cards. You can safely delete it.

## Look (Lat's pick, 19 Nov 2026)
`STYLE = "mix-photo"` in `make_week.py`: a real, free Unsplash photo (dimmed, cream text) on Mon/Thu/Sat of each theme, muted colours (linen, sage, terracotta, dusty blue, ochre, slate, olive) on the other days. Photos are listed per theme in `photos.txt` (free licence only, no Unsplash+, uploaded before 2023).
