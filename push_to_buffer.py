"""Send a week of afterwordpoet cards to Buffer (TikTok, Instagram, Facebook).

Usage:
  py -3.13 push_to_buffer.py --setup               find your Buffer channels and save their ids
  py -3.13 push_to_buffer.py --schema              print Buffer's post fields (for fixing this script)
  py -3.13 push_to_buffer.py --test weeks/<week>   upload images, then make ONE draft per channel
  py -3.13 push_to_buffer.py weeks/<week>          upload images, then schedule one post a day

Each post = the quote card, then the books slide (if the week has one), with caption.txt.
TikTok posts go out as reminders: Buffer pings your phone and you add a sound in the TikTok app.
Instagram and Facebook post on their own.

Buffer only takes images from public links, so the cards are pushed to the public GitHub repo
latczar/afterwordpoet-cards first (cloned in ./cards-repo).
Needs BUFFER_API_KEY=... in .env next to this file (create it at publish.buffer.com/settings/api).
"""
import json
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
API = "https://api.buffer.com"
ENV = HERE / ".env"
CHANNELS_FILE = HERE / "buffer_channels.json"
REPO = HERE                  # this folder is the public repo latczar/afterwordpoet-cards
RAW = "https://raw.githubusercontent.com/latczar/afterwordpoet-cards/main/"
# UK time each post goes out on its day (hour 24 = midnight at the end of that day).
# Audience is US + UK. TikTok is a phone reminder, so it's timed for when Lat is awake (7am Thailand).
POST_TIMES = {
    "instagram": (21, 0),   # 9pm UK = 4pm New York, 1pm Los Angeles
    "facebook":  (21, 0),
    "tiktok":    (24, 0),   # midnight UK = 7pm New York, 7am Thailand
}

# Which card size and publishing style each service gets.
SERVICES = {
    "tiktok":    {"size": "tiktok", "scheduling": "notification", "metadata": {}},
    "instagram": {"size": "ig", "scheduling": "automatic",
                  "metadata": {"instagram": {"type": "post", "shouldShareToFeed": True}}},
    "facebook":  {"size": "ig", "scheduling": "automatic",
                  "metadata": {"facebook": {"type": "post"}}},
}

CREATE_POST = """mutation CreatePost($input: CreatePostInput!) {
  createPost(input: $input) {
    ... on PostActionSuccess { post { id dueAt } }
    ... on MutationError { message }
  }
}"""


# ---------- Buffer API ----------

def api_key():
    import os
    if os.environ.get("BUFFER_API_KEY", "").strip():      # GitHub Actions secret
        return os.environ["BUFFER_API_KEY"].strip()
    if ENV.exists():
        for line in ENV.read_text(encoding="utf-8").splitlines():
            if line.strip().startswith("BUFFER_API_KEY="):
                key = line.split("=", 1)[1].strip().strip('"').strip("'")
                if key:
                    return key
    sys.exit(f"No Buffer key. Put BUFFER_API_KEY=... in {ENV} (from publish.buffer.com/settings/api).")


def gql(query, variables=None, _retry=True):
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(API, data=body, method="POST", headers={
        "Content-Type": "application/json", "Authorization": f"Bearer {api_key()}"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        if e.code == 429 and _retry:
            wait = int(e.headers.get("Retry-After", "60"))
            print(f"  Buffer says slow down; waiting {wait}s")
            time.sleep(wait)
            return gql(query, variables, _retry=False)
        detail = e.read().decode(errors="replace")[:500]
        sys.exit(f"Buffer API error {e.code}: {detail}")
    if data.get("errors"):
        msgs = "; ".join(err.get("message", str(err)) for err in data["errors"])
        raise RuntimeError(f"Buffer said: {msgs}")
    return data["data"]


def setup():
    orgs = gql("query { account { organizations { id name } } }")["account"]["organizations"]
    found = {}
    for org in orgs:
        chans = gql("query($input: ChannelsInput!) { channels(input: $input) "
                    "{ id name service descriptor isDisconnected isLocked } }",
                    {"input": {"organizationId": org["id"]}})["channels"]
        for c in chans:
            service = str(c["service"]).lower()
            flag = " (DISCONNECTED: reconnect it in Buffer)" if c.get("isDisconnected") else ""
            flag += " (LOCKED: over your plan's channel limit)" if c.get("isLocked") else ""
            print(f"  {service:10} {c['name']}  [{c.get('descriptor') or ''}]{flag}")
            if service in SERVICES and not c.get("isDisconnected") and service not in found:
                found[service] = {"id": c["id"], "name": c["name"]}
    CHANNELS_FILE.write_text(json.dumps(found, indent=2), encoding="utf-8")
    missing = [s for s in SERVICES if s not in found]
    print(f"Saved {', '.join(found) or 'nothing'} to {CHANNELS_FILE.name}.")
    if missing:
        print(f"Not connected in Buffer: {', '.join(missing)}. "
              "(Facebook must be a Page, Instagram a Professional account.)")


def schema():
    """Print the input fields Buffer expects for createPost, two levels deep."""
    q = """query($n: String!) { __type(name: $n) { name kind
      inputFields { name type { kind name ofType { kind name ofType { kind name ofType { kind name } } } } }
      enumValues { name } } }"""
    seen, todo = set(), ["CreatePostInput"]
    while todo:
        name = todo.pop(0)
        if name in seen:
            continue
        seen.add(name)
        t = gql(q, {"n": name})["__type"]
        if not t:
            continue
        if t["kind"] == "ENUM":
            print(f"{name}: {', '.join(v['name'] for v in t['enumValues'])}")
            continue
        print(f"{name}:")
        for f in t.get("inputFields") or []:
            ty, label = f["type"], ""
            while ty:
                label += "!" if ty["kind"] == "NON_NULL" else "[" if ty["kind"] == "LIST" else ""
                if ty.get("name"):
                    label += ty["name"]
                    if ty["kind"] in ("INPUT_OBJECT", "ENUM"):
                        todo.append(ty["name"])
                    break
                ty = ty.get("ofType")
            print(f"    {f['name']}: {label}")


# ---------- images ----------

def git(*args):
    r = subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        sys.exit(f"git {' '.join(args)} failed: {r.stderr.strip()}")
    return r.stdout


def publish_images(week):
    """Commit the week's folder to the public repo, push, and return {relative path: public URL}."""
    if not (REPO / ".git").exists():
        sys.exit(f"{REPO} is not the afterwordpoet-cards git repo.")
    urls = {}
    for size in ("tiktok", "ig"):
        for png in sorted((week / size).glob("*.png")):
            rel = f"weeks/{week.name}/{size}/{png.name}"
            urls[rel] = RAW + rel
    git("add", "--", f"weeks/{week.name}")
    if git("diff", "--cached", "--name-only").strip():
        git("commit", "-q", "-m", f"Add cards for {week.name}")
    git("pull", "--rebase", "-q")
    git("push", "-q")   # always: also sends any commit left over from an earlier failed push
    print(f"  {len(urls)} images are on GitHub")
    # Wait until every link actually serves the image.
    for rel, url in urls.items():
        for attempt in range(12):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=20) as r:
                    if r.status == 200:
                        break
            except urllib.error.URLError:
                pass
            time.sleep(5)
        else:
            sys.exit(f"Image never became available: {url}")
    return urls


# ---------- scheduling ----------

def last_sunday(year, month):
    d = date(year, month, 31)
    while d.weekday() != 6:
        d -= timedelta(days=1)
    return d


def uk_to_utc(day, hour, minute):
    """UK wall-clock time on `day` (hour may be 24 for midnight at the end of the day) -> UTC."""
    local_day = datetime(day.year, day.month, day.day) + timedelta(hours=hour, minutes=minute)
    d = local_day.date()
    bst = last_sunday(d.year, 3) <= d < last_sunday(d.year, 10)
    return local_day.replace(tzinfo=timezone(timedelta(hours=1 if bst else 0))).astimezone(timezone.utc)


def week_start(week):
    try:
        return date.fromisoformat(week.name[:10])
    except ValueError:
        sys.exit(f"Week folder must start with a date like 2026-11-23: {week.name}")


def push(week, test=False):
    if not CHANNELS_FILE.exists():
        sys.exit("Run --setup first so I know your Buffer channel ids.")
    channels = json.loads(CHANNELS_FILE.read_text(encoding="utf-8"))
    only = [a.split("=", 1)[1] for a in sys.argv if a.startswith("--only=")]
    if only:
        channels = {s: c for s, c in channels.items() if s in only}
    record_file = week / ("buffer-test.json" if test else "buffer.json")
    if record_file.exists() and "--force" not in sys.argv:
        sys.exit(f"Already sent ({record_file.name} exists). Add --force to send again.")

    cards = sorted(p.name for p in (week / "tiktok").glob("[0-9][0-9].png"))
    if not cards:
        sys.exit(f"No cards in {week / 'tiktok'}. Run make_week.py first.")
    has_books = (week / "tiktok" / "books.png").exists()
    if not has_books:
        print("  note: no books slide this week (nothing in the promo folder)")
    caption = (week / "caption.txt").read_text(encoding="utf-8").strip()
    sys.path.insert(0, str(HERE))
    from make_week import read_blocks
    quotes = read_blocks(week / "lines.txt")
    books_alt = "Three afterword poet poetry books lying on a sunlit cream bedsheet."
    urls = publish_images(week)

    start = week_start(week)
    now = datetime.now(timezone.utc)
    record = []
    for i, card in enumerate(cards[:1] if test else cards):
        for service, ch in channels.items():
            cfg = SERVICES[service]
            due = uk_to_utc(start + timedelta(days=i), *POST_TIMES[service])
            if not test and due < now + timedelta(minutes=15):
                print(f"  skipped {card} -> {service}: {due:%a %d %b %H:%M} UTC has already passed")
                continue
            alt = quotes[i].replace("\n", " ") if i < len(quotes) else "Quote card by afterwordpoet."
            assets = [{"image": {"url": urls[f"weeks/{week.name}/{cfg['size']}/{card}"],
                                 "metadata": {"altText": alt}}}]
            if has_books:
                assets.append({"image": {"url": urls[f"weeks/{week.name}/{cfg['size']}/books.png"],
                                         "metadata": {"altText": books_alt}}})
            post = {"channelId": ch["id"], "text": caption, "assets": assets,
                    "schedulingType": cfg["scheduling"], "mode": "customScheduled",
                    "dueAt": due.strftime("%Y-%m-%dT%H:%M:%SZ"), "needsApproval": False}
            if cfg["metadata"]:
                post["metadata"] = cfg["metadata"]   # Instagram multi-image posts still use type "post"
            if test:
                post["saveToDraft"] = True
            try:
                res = gql(CREATE_POST, {"input": post})["createPost"]
            except RuntimeError as e:
                res = {"message": str(e)}
            if res.get("post"):
                print(f"  {card} -> {service}: {'draft' if test else 'scheduled'} for "
                      f"{due:%a %d %b %H:%M} UTC")
                record.append({"card": card, "service": service, "postId": res["post"]["id"],
                               "dueAt": post["dueAt"]})
            else:
                print(f"  {card} -> {service}: FAILED: {res.get('message')}")
    record_file.write_text(json.dumps(record, indent=2), encoding="utf-8")
    expected = (1 if test else len(cards)) * len(channels)
    print(f"Done: {len(record)} of {expected} posts {'saved as drafts' if test else 'scheduled'}.")
    if len(record) < expected:
        sys.exit(1)


if __name__ == "__main__":
    args = [a for a in sys.argv[1:] if a != "--force" and not a.startswith("--only=")]
    if args == ["--setup"]:
        setup()
    elif args == ["--schema"]:
        schema()
    elif len(args) == 2 and args[0] == "--test":
        push((HERE / args[1]).resolve(), test=True)
    elif len(args) == 1 and not args[0].startswith("--"):
        push((HERE / args[0]).resolve())
    else:
        sys.exit(__doc__)
