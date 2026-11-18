"""Make a week of afterwordpoet quote cards (no image AI: text drawn by code).

Usage:
  py make_week.py weeks/2026-11-23-letting-go              render cards from lines.txt
  py make_week.py --mark-used weeks/2026-11-23-letting-go  add the week's quotes to quotes_used.txt

Each card is a small HTML page saved as a PNG by Microsoft Edge in headless mode.
Output: <week>/tiktok/NN.png (1080x1920), <week>/ig/NN.png (1080x1350),
        <week>/caption.txt and <week>/preview.html to check everything at a glance.
"""
import difflib
import html
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
USED = HERE / "quotes_used.txt"
CAPTION = HERE / "caption.txt"
BACKGROUNDS = HERE / "backgrounds"   # optional: drop your own background photos here
PROMO = HERE / "promo"               # optional: book promo images, one used per week
SIMILAR = 0.72                       # 0-1: how close a line may get to an old one
FONT = "Patrick Hand"                # any Google Font name, e.g. "Gaegu", "Short Stack"

SIZES = {"tiktok": (1080, 1920), "ig": (1080, 1350)}
PAPER = ["#b9cbb0", "#f2c3a7", "#f1c1cc", "#cdbfe6", "#bcd3ec"]  # sage, peach, pink, lilac, blue (old look)
# Card looks: (background, text colour). STYLE picks which set the cards rotate through.
STYLES = {
    "pastel": [(c, "#1f1c1c") for c in PAPER],
    "warm":   [("#efe7da", "#2a2522"), ("#ddd3c4", "#2a2522"), ("#e8d8c3", "#2a2522")],   # linen, stone, sand
    "moody":  [("#2f3b32", "#efe8dc"), ("#1f2a3a", "#efe8dc"), ("#3b2c2a", "#efe8dc")],   # forest, navy, oxblood
}
STYLES["mix"] = [STYLES["warm"][0], STYLES["moody"][0], STYLES["warm"][1], STYLES["moody"][1],
                 STYLES["warm"][2], STYLES["moody"][2]]
PHOTO_LIST = HERE / "photos.txt"   # STYLE "photo": real, free Unsplash photo links, one per line
PHOTO_SHADE = "linear-gradient(180deg, rgba(14,11,9,.55) 0%, rgba(14,11,9,.68) 100%)"   # dimmed so text stands out
STYLE = "mix-photo"   # photos on Mon/Thu/Sat, muted colours (linen, sage, terracotta...) on other days
SUNSET = ("radial-gradient(ellipse 55% 9% at 28% 20%, rgba(255,240,228,.55), transparent 70%),"
          "radial-gradient(ellipse 45% 8% at 74% 31%, rgba(255,222,210,.5), transparent 70%),"
          "radial-gradient(ellipse 65% 10% at 40% 74%, rgba(255,232,210,.45), transparent 70%),"
          "radial-gradient(ellipse 40% 7% at 80% 86%, rgba(255,236,214,.4), transparent 70%),"
          "linear-gradient(180deg,#e7a2b7 0%,#efb0ae 38%,#f5c3a2 72%,#f8d4aa 100%)")
GRAIN = ("url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='300' height='300'>"
         "<filter id='n'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='3' stitchTiles='stitch'/>"
         "<feColorMatrix values='0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.16 0'/></filter>"
         "<rect width='100%' height='100%' filter='url(%23n)'/></svg>\")")
MOTTLE = ("url(\"data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='1080' height='1920'>"
          "<filter id='m'><feTurbulence type='fractalNoise' baseFrequency='0.004' numOctaves='2'/>"
          "<feColorMatrix values='0 0 0 0 1  0 0 0 0 1  0 0 0 0 1  0 0 0 0.22 0'/></filter>"
          "<rect width='100%' height='100%' filter='url(%23m)'/></svg>\")")

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<link rel="preconnect" href="https://fonts.gstatic.com">
<link href="https://fonts.googleapis.com/css2?family={font_url}&display=block" rel="stylesheet">
<style>
html,body{{margin:0;width:{w}px;height:{h}px;overflow:hidden}}
body{{background:{bg};background-size:cover;background-position:center;position:relative;
  font-family:'{font}',cursive;color:{fg}}}
.layer{{position:absolute;inset:0}}
.mottle{{background-image:{mottle};background-size:cover;opacity:{mottle_op}}}
.grain{{background-image:{grain}}}
.shade{{background:{shade}}}
.wrap{{position:absolute;left:{padx}px;top:{top}%;transform:translateY(-50%);max-width:{maxw}px;text-shadow:{tshadow}}}
.q{{font-size:{fs}px;line-height:1.3;margin:0;white-space:pre-line}}
.sig{{font-size:{sfs}px;text-align:right;margin-top:{gap}px}}
</style></head><body>
<div class="layer mottle"></div><div class="layer shade"></div><div class="layer grain"></div>
<div class="wrap"><p class="q">{text}</p><div class="sig">- afterwordpoet</div></div>
</body></html>"""


BOOKS_PAGE = """<!doctype html><html><head><meta charset="utf-8"><style>
html,body{{margin:0;width:{w}px;height:{h}px;overflow:hidden;background:#000;position:relative}}
.bg{{position:absolute;inset:-60px;background:url('{src}') center/cover;filter:blur(40px) brightness(.9)}}
.fg{{position:absolute;inset:0;background:url('{src}') center/contain no-repeat}}
</style></head><body><div class="bg"></div><div class="fg"></div></body></html>"""


FONT_CHECK = """<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family={font_url}&display=block" rel="stylesheet"></head>
<body style="font-family:'{font}'">x<script>
document.fonts.load("40px '{font}'").then(function () {{
  var ok = Array.from(document.fonts).some(function (f) {{
    return f.family.replace(/["']/g, '') === '{font}' && f.status === 'loaded'; }});
  document.body.setAttribute('data-font', ok ? 'ok' : 'missing');
}});
</script></body></html>"""


def check_font(browser, tmp):
    """Stop before making cards if the handwritten font can't be loaded (they'd look wrong)."""
    page = tmp / "font-check.html"
    page.write_text(FONT_CHECK.format(font=FONT, font_url=FONT.replace(" ", "+")), encoding="utf-8")
    cmd = [browser, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
           f"--user-data-dir={HERE / '.render-profile'}", "--virtual-time-budget=8000",
           "--dump-dom", page.as_uri()]
    if sys.platform != "win32":
        cmd.insert(1, "--no-sandbox")
    dom = subprocess.run(cmd, capture_output=True, text=True, timeout=120).stdout
    if 'data-font="ok"' not in dom:
        sys.exit(f"The {FONT} font didn't load, so no cards were made (they'd look wrong). Try again later.")
    print(f"  font check: {FONT} loaded")


def read_blocks(path):
    return parse_blocks(path.read_text(encoding="utf-8").splitlines())


def parse_blocks(lines):
    """Quotes separated by blank lines; '#' lines ignored."""
    blocks, cur = [], []
    for raw in lines:
        line = raw.rstrip()
        if line.lstrip().startswith("#"):
            continue
        if line.strip():
            cur.append(line.strip())
        elif cur:
            blocks.append("\n".join(cur))
            cur = []
    if cur:
        blocks.append("\n".join(cur))
    return blocks


def read_used(skip_week=None):
    """Posted quotes, leaving out the section a week added itself (so it can be re-made)."""
    if not USED.exists():
        return []
    keep, skipping = [], False
    for raw in USED.read_text(encoding="utf-8").splitlines():
        if raw.startswith("# "):
            skipping = skip_week is not None and raw[2:].strip() == skip_week
            continue
        if not skipping:
            keep.append(raw)
    return parse_blocks(keep)


def norm(text):
    text = text.lower().replace("\u2019", "'")
    return " ".join(re.sub(r"[^a-z' ]", " ", text).split())


STOP = set("""a an the and or but so to of in on at for with from by as is are was were be been am i
i'm i've i'd you you're your yours me my mine we us our it it's its this that these those there their
they them he she his her not no do does did don't didn't just only still even all some any more most
very can could would should will what who when where why how than then if like""".split())


def key_words(text):
    return {w.rstrip("'s") for w in norm(text).split() if w not in STOP and len(w) > 2}


def similarity(a, b):
    """Highest of: wording match, and share of key words (catches same idea, different words)."""
    r = difflib.SequenceMatcher(None, norm(a), norm(b)).ratio()
    ka, kb = key_words(a), key_words(b)
    if len(ka) >= 3 and len(kb) >= 3:
        overlap = len(ka & kb) / min(len(ka), len(kb))
        r = max(r, overlap * 0.9)   # e.g. 4 of 5 key words shared -> 0.72
    return r


def find_clashes(new, old):
    """Pairs that are too similar: against posted quotes and within this week."""
    out = []
    for i, n in enumerate(new):
        for o in old:
            r = similarity(n, o)
            if r >= SIMILAR:
                out.append((n, o, r))
        for m in new[i + 1:]:
            r = similarity(n, m)
            if r >= SIMILAR:
                out.append((n, m, r))
    return out


def find_browser():
    for p in (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
              r"C:\Program Files\Google\Chrome\Application\chrome.exe"):
        if Path(p).exists():
            return p
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):  # Linux / GitHub
        if shutil.which(name):
            return shutil.which(name)
    sys.exit("Could not find Microsoft Edge or Google Chrome to draw the cards.")


def png_size(path):
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


def photo_links(week_name=""):
    """Photo links for a week: those tagged with a word in the week's name, else the 'any' ones."""
    if not PHOTO_LIST.exists():
        return []
    rows = [l.split() for l in PHOTO_LIST.read_text(encoding="utf-8").splitlines()
            if l.strip() and not l.startswith("#") and len(l.split()) == 2]
    tagged = [u for t, u in rows if t != "any" and t in week_name and u not in BAD_PHOTOS]
    return tagged or [u for t, u in rows if t == "any" and u not in BAD_PHOTOS]


BAD_PHOTOS = set()
PHOTO_CHECK = """<!doctype html><html><body>{imgs}<script>
var imgs = Array.from(document.images), left = imgs.length;
function done() {{ if (--left === 0) document.body.setAttribute('data-done', '1'); }}
imgs.forEach(function (im) {{
  im.onload = function () {{ im.setAttribute('data-ok', im.naturalWidth > 0 ? '1' : '0'); done(); }};
  im.onerror = function () {{ im.setAttribute('data-ok', '0'); done(); }};
}});
</script></body></html>"""


def check_photos(browser, tmp, week_name):
    """Load this week's photos once; any that fail are dropped so those cards use a colour instead."""
    links = photo_links(week_name)
    if STYLE not in ("photo", "mix-photo") or not links:
        return
    imgs = "".join(f'<img src="{u}?w=1080&h=1920&fit=crop&q=80" data-u="{u}">' for u in links)
    page = tmp / "photo-check.html"
    page.write_text(PHOTO_CHECK.format(imgs=imgs), encoding="utf-8")
    cmd = [browser, "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
           f"--user-data-dir={HERE / '.render-profile'}", "--virtual-time-budget=15000", "--dump-dom", page.as_uri()]
    if sys.platform != "win32":
        cmd.insert(1, "--no-sandbox")
    dom = subprocess.run(cmd, capture_output=True, text=True, timeout=180).stdout
    for u in links:
        tail = dom.split(f'data-u="{u}"')[1].split('>')[0] if f'data-u="{u}"' in dom else ''
        if 'data-ok="1"' not in tail:
            BAD_PHOTOS.add(u)
    print(f"  photo check: {len(links) - len([u for u in links if u in BAD_PHOTOS])}/{len(links)} photos loaded")


PHOTO_DAYS = (0, 3, 5)   # in "mix-photo": Mon, Thu, Sat of each 7-day theme get a real photo
COLOURS = [("#efe7da", "#2a2522"), ("#a9b8a0", "#1f2420"), ("#c47b5f", "#f6efe4"), ("#9fb3c8", "#1d2430"),
           ("#d9b26a", "#2a2522"), ("#4a5a6a", "#f3ece0"), ("#6b7350", "#f3ece0")]
# linen, sage, terracotta, dusty blue, ochre, slate, olive (muted, no pinks)


def background(i, week_name=""):
    """(css background, mottle opacity, text colour, shade) for card number i (0-based)."""
    seed = sum(map(ord, week_name))
    use_photo = STYLE == "photo" or (STYLE == "mix-photo" and i % 7 in PHOTO_DAYS)
    links = photo_links(week_name) if use_photo else []
    if links:
        n = (i // 7) * len(PHOTO_DAYS) + (PHOTO_DAYS.index(i % 7) if i % 7 in PHOTO_DAYS else 0)
        # Real photo behind the text, dimmed so the cream text stands out.
        return f"url('{links[(n + seed) % len(links)]}?w=1080&h=1920&fit=crop&q=80')", 0.0, "#f6efe4", PHOTO_SHADE
    if STYLE == "pastel" and i % 3 == 2:
        return SUNSET, 0.25, "#1f1c1c", "transparent"
    if STYLE in ("photo", "mix-photo"):
        bg, fg = COLOURS[(i + seed) % len(COLOURS)]
    else:
        bg, fg = STYLES[STYLE][i % len(STYLES[STYLE])]
    return bg, 1.0, fg, "transparent"


def render(browser, html_text, out, w, h, tmp):
    page = tmp / (out.stem + f"-{w}x{h}.html")
    page.write_text(html_text, encoding="utf-8")
    cmd = [browser, "--headless=new", "--disable-gpu", "--hide-scrollbars",
           "--force-device-scale-factor=1", "--no-first-run", "--no-default-browser-check",
           f"--user-data-dir={HERE / '.render-profile'}", f"--window-size={w},{h}",
           "--virtual-time-budget=8000", f"--screenshot={out}", page.as_uri()]
    if sys.platform != "win32":
        cmd.insert(1, "--no-sandbox")   # needed on GitHub's Linux runners
    subprocess.run(cmd, capture_output=True, timeout=120)
    if not out.exists():
        sys.exit(f"Edge did not save {out}. Close any stuck Edge windows and try again.")
    got = png_size(out)
    if got != (w, h):
        print(f"  warning: {out.name} is {got[0]}x{got[1]}, expected {w}x{h}")


def card_html(text, i, w, h, week_name=""):
    lines = text.split("\n")
    longest = max(len(l) for l in lines)
    padx = 100
    maxw = w - 2 * padx
    fs = int(min(92, maxw / (longest * 0.44)))
    bg, mottle_op, fg, shade = background(i, week_name)
    top = 46 if h > w * 1.5 else 48
    tshadow = "0 2px 18px rgba(0,0,0,.45)" if shade != "transparent" else "none"
    return PAGE.format(font=FONT, font_url=FONT.replace(" ", "+"), fg=fg, shade=shade, tshadow=tshadow,
                       w=w, h=h, bg=bg, mottle=MOTTLE, mottle_op=mottle_op, grain=GRAIN,
                       padx=padx, maxw=maxw, top=top, fs=fs, sfs=int(fs * 0.42),
                       gap=int(fs * 0.25), text=html.escape(text))


def preview(week, quotes, has_books, caption):
    tiles = "".join(
        f'<figure><img src="tiktok/{i:02d}.png"><figcaption>post {i}, slide 1</figcaption></figure>'
        for i in range(1, len(quotes) + 1))
    if has_books:
        tiles += '<figure><img src="tiktok/books.png"><figcaption>last slide on every post</figcaption></figure>'
    page = f"""<!doctype html><html><head><meta charset="utf-8"><title>{week.name}</title>
<style>body{{font-family:system-ui,sans-serif;margin:24px;background:#f6f4f1;color:#222}}
.g{{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:14px}}
figure{{margin:0}} img{{width:100%;border-radius:8px;box-shadow:0 1px 4px #0002}}
figcaption{{font-size:13px;color:#666;margin-top:4px}} pre{{white-space:pre-wrap;background:#fff;padding:12px;border-radius:8px}}</style>
</head><body><h1>{html.escape(week.name)}</h1><div class="g">{tiles}</div>
<h2>Caption (same on every post)</h2><pre>{html.escape(caption)}</pre></body></html>"""
    (week / "preview.html").write_text(page, encoding="utf-8")


def make(week):
    lines_file = week / "lines.txt"
    if not lines_file.exists():
        sys.exit(f"No lines.txt in {week}")
    quotes = read_blocks(lines_file)
    if not quotes:
        sys.exit("lines.txt has no quotes in it.")
    old = read_used(skip_week=week.name)
    clashes = find_clashes(quotes, old)
    if clashes:
        print("Too close to something already posted (or to another card this week):")
        for n, o, r in clashes:
            print(f"  {int(r * 100)}%  NEW: {n!r}\n        OLD: {o!r}")
        sys.exit(2)

    browser = find_browser()
    for sub in SIZES:
        (week / sub).mkdir(exist_ok=True)
        for old in (week / sub).glob("[0-9][0-9].png"):   # drop cards left over from a longer lines.txt
            old.unlink()
    with tempfile.TemporaryDirectory() as t:
        tmp = Path(t)
        check_font(browser, tmp)
        check_photos(browser, tmp, week.name)
        for i, q in enumerate(quotes):
            for sub, (w, h) in SIZES.items():
                out = week / sub / f"{i + 1:02d}.png"
                out.unlink(missing_ok=True)
                render(browser, card_html(q, i, w, h, week.name), out, w, h, tmp)
            print(f"  card {i + 1:02d} done")

        # Books photo: the last slide of every post, fitted to each size.
        promos = sorted(p for p in PROMO.glob("*") if p.suffix.lower() in (".jpg", ".jpeg", ".png", ".webp")) \
            if PROMO.exists() else []
        has_books = bool(promos)
        if promos:
            pick = promos[sum(map(ord, week.name)) % len(promos)]
            for sub, (w, h) in SIZES.items():
                out = week / sub / "books.png"
                out.unlink(missing_ok=True)
                render(browser, BOOKS_PAGE.format(w=w, h=h, src=pick.as_uri()), out, w, h, tmp)
            print(f"  books slide made from {pick.name}")
        else:
            print("  no books slide: put your books photo in the 'promo' folder and run this again")

    caption = CAPTION.read_text(encoding="utf-8").strip()
    (week / "caption.txt").write_text(caption + "\n", encoding="utf-8")
    preview(week, quotes, has_books, caption)
    print(f"Done: {len(quotes)} cards. Check {week / 'preview.html'}")


def mark_used(week):
    """Add (or refresh) this week's section in quotes_used.txt."""
    quotes = read_blocks(week / "lines.txt")
    section = f"# {week.name}\n" + "".join(f"\n{q}\n" for q in quotes)
    lines = USED.read_text(encoding="utf-8").splitlines(keepends=True)
    out, skipping, replaced = [], False, False
    for line in lines:
        if line.startswith("# "):
            if line.strip() == f"# {week.name}":
                skipping, replaced = True, True
                out.append(section + "\n")
                continue
            skipping = False
        if not skipping:
            out.append(line)
    if not replaced:
        out.append("\n" + section)
    USED.write_text("".join(out), encoding="utf-8")
    print(f"Recorded {len(quotes)} quotes for {week.name} in {USED.name}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    if args[0] == "--mark-used" and len(args) == 2:
        mark_used((HERE / args[1]).resolve())
    else:
        make((HERE / args[0]).resolve())
