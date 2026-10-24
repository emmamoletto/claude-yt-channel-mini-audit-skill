#!/usr/bin/env python3
"""
channel_audit.py: extract every video of a YouTube channel (long-form and
Shorts) with the YouTube Data API v3, then build an Excel audit.

Three subcommands:

  extract  Pull all videos of a channel and save them to a JSON file.
           Only the Python standard library is needed.

      python channel_audit.py extract --channel @handle --out videos.json

  review   Print a compact batch of videos for review (no API calls).

      python channel_audit.py review --videos videos.json --start 0 --size 20

  build    Turn videos.json, plus an optional notes.json with the review
           of each video, into an .xlsx file with a "Long" and a "Short" tab.
           Needs openpyxl (pip install openpyxl).

      python channel_audit.py build --videos videos.json \
          --notes notes.json --out channel-audit.xlsx --lang it

The API key is read from the YOUTUBE_API_KEY environment variable, or from
--api-key. Quota: about 1 unit per 50 videos, plus 1 unit per channel lookup.
"""

import argparse
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

API = "https://www.googleapis.com/youtube/v3/"
QUOTA_USED = 0


# ---------------------------------------------------------------- API calls

def api_get(endpoint, params, key, retries=3):
    """GET one API endpoint and return the parsed JSON. Raises on errors."""
    global QUOTA_USED
    params = dict(params, key=key)
    url = API + endpoint + "?" + urllib.parse.urlencode(params)
    last_error = None
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=30) as resp:
                QUOTA_USED += 1
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            try:
                reason = json.loads(body)["error"]["errors"][0].get("reason", "")
            except Exception:
                reason = ""
            # A missing playlist is a normal answer for the Shorts playlist.
            if e.code == 404:
                raise LookupError(reason or "notFound")
            if e.code in (500, 503) and attempt < retries - 1:
                time.sleep(2 * (attempt + 1))
                continue
            raise RuntimeError(f"YouTube API error {e.code} on {endpoint}: {reason or body[:300]}")
        except urllib.error.URLError as e:
            last_error = e
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Network error calling {endpoint}: {last_error}")


def parse_channel_ref(ref):
    """Accept a channel URL, @handle or UC... ID. Return ('id'|'handle'|'user', value)."""
    ref = ref.strip()
    m = re.search(r"(UC[0-9A-Za-z_-]{22})", ref)
    if m:
        return "id", m.group(1)
    m = re.search(r"@([0-9A-Za-z_.\-·]+)", ref)
    if m:
        return "handle", "@" + m.group(1)
    m = re.search(r"youtube\.com/(?:user|c)/([^/?#]+)", ref)
    if m:
        return "user", m.group(1)
    return "handle", ref if ref.startswith("@") else "@" + ref


def resolve_channel(ref, key):
    kind, value = parse_channel_ref(ref)
    params = {"part": "snippet,contentDetails,statistics"}
    if kind == "id":
        params["id"] = value
    elif kind == "handle":
        params["forHandle"] = value
    else:
        params["forUsername"] = value
    data = api_get("channels", params, key)
    items = data.get("items") or []
    if not items:
        raise SystemExit(f"Channel not found: {ref}")
    ch = items[0]
    return {
        "channel_id": ch["id"],
        "title": ch["snippet"].get("title", ""),
        "handle": ch["snippet"].get("customUrl", ""),
        "country": ch["snippet"].get("country", ""),
        "default_language": ch["snippet"].get("defaultLanguage", ""),
        "subscribers": ch.get("statistics", {}).get("subscriberCount"),
        "video_count": ch.get("statistics", {}).get("videoCount"),
        "uploads_playlist": ch["contentDetails"]["relatedPlaylists"]["uploads"],
    }


def playlist_video_ids(playlist_id, key):
    """Every video ID in a playlist. Raises LookupError if the playlist does not exist."""
    ids, token = [], None
    while True:
        params = {"part": "contentDetails", "playlistId": playlist_id, "maxResults": 50}
        if token:
            params["pageToken"] = token
        data = api_get("playlistItems", params, key)
        for it in data.get("items", []):
            vid = it.get("contentDetails", {}).get("videoId")
            if vid:
                ids.append(vid)
        token = data.get("nextPageToken")
        if not token:
            return ids


def video_details(ids, key):
    out = []
    for i in range(0, len(ids), 50):
        batch = ids[i:i + 50]
        data = api_get("videos", {
            "part": "snippet,contentDetails,statistics,status",
            "id": ",".join(batch),
            "maxResults": 50,
        }, key)
        out.extend(data.get("items", []))
    return out


# ------------------------------------------------------------------ parsing

def iso_duration_seconds(iso):
    """PT1H2M3S -> 3723. Returns 0 for live/upcoming items without a duration."""
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x) if x else 0 for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def fmt_seconds(sec):
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


TS_RE = re.compile(r"(?<![\d:])((?:\d{1,2}:)?\d{1,2}:\d{2})(?![\d:])")


def ts_to_seconds(ts):
    parts = [int(p) for p in ts.split(":")]
    while len(parts) < 3:
        parts.insert(0, 0)
    h, m, s = parts
    return h * 3600 + m * 60 + s


def parse_chapters(description, duration_sec):
    """
    Find chapter lines in a description: one timestamp per line, with a title.
    Returns (chapters, valid, problems). YouTube renders chapters only when the
    first timestamp is 0:00, there are at least 3, they go up, and each lasts
    at least 10 seconds.
    """
    chapters = []
    for line in (description or "").splitlines():
        line = line.strip()
        found = TS_RE.findall(line)
        if len(found) != 1:
            continue
        ts = found[0]
        title = TS_RE.sub("", line, count=1)
        title = re.sub(r"^[\s\-–—:|•·.)\]]+|[\s\-–—:|•·(\[]+$", "", title).strip()
        chapters.append({"start": ts_to_seconds(ts), "timestamp": ts, "title": title})

    problems = []
    if not chapters:
        return [], False, ["no timestamps in the description"]
    if chapters[0]["start"] != 0:
        problems.append("first timestamp is not 0:00")
    if len(chapters) < 3:
        problems.append("fewer than 3 timestamps")
    starts = [c["start"] for c in chapters]
    if any(b <= a for a, b in zip(starts, starts[1:])):
        problems.append("timestamps not in ascending order")
    ends = starts[1:] + ([duration_sec] if duration_sec else [])
    if any(e - s < 10 for s, e in zip(starts, ends)):
        problems.append("a chapter is shorter than 10 seconds")
    if duration_sec and starts[-1] >= duration_sec:
        problems.append("a timestamp is past the end of the video")
    if any(not c["title"] for c in chapters):
        problems.append("chapters without a title")
    return chapters, not problems, problems


def best_thumbnail(thumbs):
    for k in ("maxres", "standard", "high", "medium", "default"):
        if k in (thumbs or {}):
            t = thumbs[k]
            return t.get("url", ""), k, t.get("width"), t.get("height")
    return "", "", None, None


HASHTAG_RE = re.compile(r"(?<!\w)#[\wÀ-ÿ]+", re.UNICODE)
URL_RE = re.compile(r"https?://\S+")


def classify(vid, duration_sec, shorts_ids, longs_ids, title, description):
    """Short or Long. Uses the channel's own Shorts / long-form playlists when
    YouTube exposes them; otherwise falls back to duration and #shorts."""
    if shorts_ids is not None and vid in shorts_ids:
        return "Short", "channel Shorts playlist"
    if longs_ids is not None and vid in longs_ids:
        return "Long", "channel long-form playlist"
    text = f"{title} {description}".lower()
    if duration_sec and duration_sec <= 180 and "#short" in text:
        return "Short", "estimate: up to 3 min and #shorts"
    if duration_sec and duration_sec <= 60:
        return "Short", "estimate: up to 60 s"
    return "Long", "estimate: duration"


# ------------------------------------------------------------------ extract

def cmd_extract(args):
    key = args.api_key or os.environ.get("YOUTUBE_API_KEY")
    if not key:
        raise SystemExit("Missing API key: set YOUTUBE_API_KEY or pass --api-key.")

    channel = resolve_channel(args.channel, key)
    uploads = channel["uploads_playlist"]
    print(f"Channel: {channel['title']} ({channel['channel_id']}), "
          f"{channel['video_count']} public videos declared", file=sys.stderr)

    all_ids = playlist_video_ids(uploads, key)

    # UC... -> UUSH... is the channel's Shorts playlist, UULF... its long-form
    # one. YouTube does not document them, so the script works without them.
    base = channel["channel_id"][2:]
    shorts_ids = longs_ids = None
    try:
        shorts_ids = set(playlist_video_ids("UUSH" + base, key))
    except (LookupError, RuntimeError):
        shorts_ids = None
    try:
        longs_ids = set(playlist_video_ids("UULF" + base, key))
    except (LookupError, RuntimeError):
        longs_ids = None
    if shorts_ids is None and longs_ids is None:
        print("Shorts playlist not available: classifying by duration.", file=sys.stderr)

    items = video_details(all_ids, key)
    videos = []
    for it in items:
        sn, cd = it.get("snippet", {}), it.get("contentDetails", {})
        st = it.get("statistics", {})
        title = sn.get("title", "")
        desc = sn.get("description", "")
        dur = iso_duration_seconds(cd.get("duration"))
        chapters, ch_valid, ch_problems = parse_chapters(desc, dur)
        thumb_url, thumb_size, tw, th = best_thumbnail(sn.get("thumbnails"))
        fmt, fmt_source = classify(it["id"], dur, shorts_ids, longs_ids, title, desc)
        live = sn.get("liveBroadcastContent", "none")
        videos.append({
            "video_id": it["id"],
            "url": (f"https://www.youtube.com/shorts/{it['id']}" if fmt == "Short"
                    else f"https://www.youtube.com/watch?v={it['id']}"),
            "format": fmt,
            "format_source": fmt_source,
            "title": title,
            "title_chars": len(title),
            "description": desc,
            "description_words": len(re.findall(r"\w+", desc, re.UNICODE)),
            "description_first_line": next((l.strip() for l in desc.splitlines() if l.strip()), ""),
            "hashtags": HASHTAG_RE.findall(desc),
            "links_in_description": len(URL_RE.findall(desc)),
            "tags": sn.get("tags", []),
            "published_at": sn.get("publishedAt", ""),
            "duration_seconds": dur,
            "duration": fmt_seconds(dur) if dur else "",
            "is_live_or_upcoming": live != "none",
            "chapters": chapters,
            "chapters_count": len(chapters),
            "chapters_valid": ch_valid,
            "chapters_problems": ch_problems,
            "thumbnail_url": thumb_url,
            "thumbnail_size": thumb_size,
            "thumbnail_resolution": f"{tw}x{th}" if tw else "",
            "captions_uploaded": cd.get("caption") == "true",
            "default_language": sn.get("defaultLanguage", ""),
            "audio_language": sn.get("defaultAudioLanguage", ""),
            "category_id": sn.get("categoryId", ""),
            "views": int(st["viewCount"]) if "viewCount" in st else None,
            "likes": int(st["likeCount"]) if "likeCount" in st else None,
            "comments": int(st["commentCount"]) if "commentCount" in st else None,
            "privacy": it.get("status", {}).get("privacyStatus", ""),
        })

    videos.sort(key=lambda v: v["published_at"], reverse=True)
    result = {
        "extracted_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "channel": channel,
        "counts": {
            "total": len(videos),
            "long": sum(v["format"] == "Long" for v in videos),
            "short": sum(v["format"] == "Short" for v in videos),
            "ids_in_uploads_without_details": len(all_ids) - len(items),
        },
        "quota_units_used": QUOTA_USED,
        "videos": videos,
    }
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    c = result["counts"]
    print(f"Saved {c['total']} videos ({c['long']} long, {c['short']} short) to {args.out}. "
          f"Quota used: {QUOTA_USED} units.", file=sys.stderr)


# -------------------------------------------------------------------- build

# (key, width). Labels come from LABELS, in the language picked with --lang.
LONG_COLUMNS = [
    ("date", 12), ("title", 45), ("url", 22), ("duration", 9),
    ("thumbnail", 22), ("description", 60), ("description_words", 11),
    ("hashtags", 18), ("chapters", 40), ("chapters_count", 9), ("chapters_valid", 10),
    ("captions", 11), ("audio_language", 9), ("views", 10),
    ("rating", 14), ("note", 70),
]
SHORT_COLUMNS = [
    ("date", 12), ("title", 45), ("url", 22), ("duration", 9),
    ("thumbnail", 22), ("description", 60), ("description_words", 11),
    ("hashtags", 18), ("captions", 11), ("audio_language", 9),
    ("views", 10), ("rating", 14), ("note", 70),
]

LABELS = {
    "it": {
        "date": "Data", "title": "Titolo", "url": "URL", "duration": "Durata",
        "thumbnail": "Thumbnail", "description": "Descrizione",
        "description_words": "Parole descrizione", "hashtags": "Hashtag",
        "chapters": "Capitoli", "chapters_count": "N. capitoli",
        "chapters_valid": "Capitoli validi", "captions": "Sottotitoli caricati",
        "audio_language": "Lingua audio", "views": "Views",
        "rating": "Valutazione", "note": "Note",
        "yes": "Sì", "no": "No",
        "ratings": ["Ottimizzato", "Da migliorare", "Da rifare"],
        "info": ["Canale", "Handle", "Channel ID", "Iscritti", "Video dichiarati",
                 "Video estratti", "Long", "Short", "Estratto il", "Quota API usata",
                 "Video con nota"],
    },
    "en": {
        "date": "Date", "title": "Title", "url": "URL", "duration": "Duration",
        "thumbnail": "Thumbnail", "description": "Description",
        "description_words": "Description words", "hashtags": "Hashtags",
        "chapters": "Chapters", "chapters_count": "Chapters",
        "chapters_valid": "Valid chapters", "captions": "Uploaded captions",
        "audio_language": "Audio language", "views": "Views",
        "rating": "Rating", "note": "Notes",
        "yes": "Yes", "no": "No",
        "ratings": ["Optimised", "Needs work", "Redo"],
        "info": ["Channel", "Handle", "Channel ID", "Subscribers", "Declared videos",
                 "Extracted videos", "Long", "Short", "Extracted at", "API quota used",
                 "Videos with a note"],
    },
}
LABELS["en"]["chapters_count"] = "Chapter count"

# A note's rating can be written in either language; the sheet shows it in --lang.
RATING_ALIASES = {
    "ottimizzato": 0, "optimised": 0, "optimized": 0,
    "da migliorare": 1, "needs work": 1,
    "da rifare": 2, "redo": 2,
}


def row_for(v, note, columns, L):
    chapters_txt = "\n".join(f"{c['timestamp']} {c['title']}" for c in v["chapters"])
    rating = note.get("rating", "")
    idx = RATING_ALIASES.get(str(rating).strip().lower())
    values = {
        "date": v["published_at"][:10],
        "title": v["title"],
        "url": v["url"],
        "duration": v["duration"],
        "thumbnail": v["thumbnail_url"],
        "description": v["description"],
        "description_words": v["description_words"],
        "hashtags": " ".join(v["hashtags"]),
        "chapters": chapters_txt,
        "chapters_count": v["chapters_count"],
        "chapters_valid": L["yes"] if v["chapters_valid"] else (L["no"] if v["chapters"] else "-"),
        "captions": L["yes"] if v["captions_uploaded"] else L["no"],
        "audio_language": v["audio_language"] or "-",
        "views": v["views"],
        "rating": L["ratings"][idx] if idx is not None else rating,
        "note": note.get("note", ""),
    }
    return [values[k] for k, _ in columns]


def cmd_build(args):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.worksheet.datavalidation import DataValidation
        from openpyxl.formatting.rule import FormulaRule
    except ImportError:
        raise SystemExit("openpyxl is missing: run  pip install openpyxl")

    with open(args.videos, encoding="utf-8") as f:
        data = json.load(f)
    # Notes can come from one file or many batch files (notes-001.json ...).
    import glob
    paths = []
    for pattern in args.notes:
        paths.extend(sorted(glob.glob(pattern)) or ([pattern] if os.path.exists(pattern) else []))
    notes = {}
    for path in paths:
        with open(path, encoding="utf-8") as f:
            raw = json.load(f)
        notes.update(raw if isinstance(raw, dict) else {n["video_id"]: n for n in raw})
    known = {v["video_id"] for v in data["videos"]}
    unknown = [k for k in notes if k not in known]
    if unknown:
        print(f"Warning: {len(unknown)} note(s) refer to unknown video IDs: {unknown[:5]}", file=sys.stderr)

    L = LABELS[args.lang]
    wb = Workbook()
    header_fill = PatternFill("solid", fgColor="1F2937")
    header_font = Font(bold=True, color="FFFFFF")
    wrap = Alignment(wrap_text=True, vertical="top")
    ratings = L["ratings"]
    fills = dict(zip(ratings, ["D1FAE5", "FEF3C7", "FEE2E2"]))

    def sheet(ws, fmt, columns):
        ws.append([L[k] for k, _ in columns])
        for i, (_, width) in enumerate(columns, start=1):
            cell = ws.cell(row=1, column=i)
            cell.fill, cell.font = header_fill, header_font
            cell.alignment = Alignment(wrap_text=True, vertical="center")
            ws.column_dimensions[cell.column_letter].width = width
        rows = [v for v in data["videos"] if v["format"] == fmt]
        keys = [k for k, _ in columns]
        for v in rows:
            ws.append(row_for(v, notes.get(v["video_id"], {}), columns, L))
            r = ws.max_row
            for cell in ws[r]:
                cell.alignment = wrap
            for col in ("url", "thumbnail"):
                c = ws.cell(row=r, column=keys.index(col) + 1)
                if c.value:
                    c.hyperlink = c.value
                    c.font = Font(color="2563EB", underline="single")
            ws.row_dimensions[r].height = 90
        ws.freeze_panes = "C2"
        ws.auto_filter.ref = ws.dimensions
        last = ws.max_row
        rating_col = ws.cell(row=1, column=keys.index("rating") + 1).column_letter
        if last > 1:
            dv = DataValidation(type="list", formula1='"' + ",".join(ratings) + '"', allow_blank=True)
            ws.add_data_validation(dv)
            dv.add(f"{rating_col}2:{rating_col}{last}")
            for label, color in fills.items():
                ws.conditional_formatting.add(
                    f"{rating_col}2:{rating_col}{last}",
                    FormulaRule(formula=[f'${rating_col}2="{label}"'],
                                fill=PatternFill("solid", fgColor=color)))
        return len(rows)

    ws_long = wb.active
    ws_long.title = "Long"
    n_long = sheet(ws_long, "Long", LONG_COLUMNS)
    n_short = sheet(wb.create_sheet("Short"), "Short", SHORT_COLUMNS)

    info = wb.create_sheet("Info")
    ch = data["channel"]
    values = [
        ch["title"], ch["handle"], ch["channel_id"], ch["subscribers"], ch["video_count"],
        data["counts"]["total"], n_long, n_short, data["extracted_at"],
        data["quota_units_used"],
        sum(1 for v in data["videos"] if v["video_id"] in notes),
    ]
    for k, v in zip(L["info"], values):
        info.append([k, v])
    info.column_dimensions["A"].width = 20
    info.column_dimensions["B"].width = 40
    for c in info["A"]:
        c.font = Font(bold=True)

    wb.save(args.out)
    missing = [v["video_id"] for v in data["videos"] if v["video_id"] not in notes]
    print(f"Saved {args.out}: {n_long} long, {n_short} short. "
          f"Videos without a note: {len(missing)}.", file=sys.stderr)


# ------------------------------------------------------------------- review

def cmd_review(args):
    """Print a compact batch of videos for Claude to review. No API calls."""
    with open(args.videos, encoding="utf-8") as f:
        data = json.load(f)
    videos = data["videos"]
    if args.format:
        videos = [v for v in videos if v["format"].lower() == args.format.lower()]
    batch = videos[args.start:args.start + args.size]
    compact = [{
        "video_id": v["video_id"],
        "format": v["format"],
        "title": v["title"],
        "duration": v["duration"],
        "published": v["published_at"][:10],
        "description": v["description"][:args.max_desc],
        "description_truncated": len(v["description"]) > args.max_desc,
        "description_words": v["description_words"],
        "hashtags": v["hashtags"],
        "links_in_description": v["links_in_description"],
        "chapters": [f"{c['timestamp']} {c['title']}" for c in v["chapters"]],
        "chapters_valid": v["chapters_valid"],
        "chapters_problems": v["chapters_problems"],
        "captions_uploaded": v["captions_uploaded"],
        "audio_language": v["audio_language"],
        "tags": v["tags"][:15],
        "views": v["views"],
    } for v in batch]
    print(json.dumps({
        "total": len(videos), "start": args.start, "returned": len(compact),
        "next_start": args.start + len(compact) if args.start + len(compact) < len(videos) else None,
        "videos": compact,
    }, ensure_ascii=False, indent=1))


# --------------------------------------------------------------------- main

def main():
    p = argparse.ArgumentParser(description="YouTube channel audit for AI retrievability.")
    sub = p.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract", help="pull all videos of a channel into JSON")
    e.add_argument("--channel", required=True, help="channel URL, @handle or UC... ID")
    e.add_argument("--out", default="videos.json")
    e.add_argument("--api-key", help="defaults to the YOUTUBE_API_KEY env var")
    e.set_defaults(func=cmd_extract)
    r = sub.add_parser("review", help="print a compact batch of videos to review")
    r.add_argument("--videos", default="videos.json")
    r.add_argument("--start", type=int, default=0)
    r.add_argument("--size", type=int, default=20)
    r.add_argument("--format", choices=["long", "short"], help="only long or only short")
    r.add_argument("--max-desc", type=int, default=2500, help="max description characters")
    r.set_defaults(func=cmd_review)
    b = sub.add_parser("build", help="build the Excel file from videos.json and notes.json")
    b.add_argument("--videos", default="videos.json")
    b.add_argument("--notes", nargs="+", default=["notes*.json"],
                   help="one or more notes files or glob patterns")
    b.add_argument("--out", default="channel-audit.xlsx")
    b.add_argument("--lang", choices=["it", "en"], default="en", help="column language")
    b.set_defaults(func=cmd_build)
    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
