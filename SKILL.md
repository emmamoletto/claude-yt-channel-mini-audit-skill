---
name: channel-audit
description: Audits every video of a YouTube channel, long-form and Shorts, for AI retrievability. Pulls title, description, thumbnail, chapters and duration with the YouTube Data API v3, reviews each video and writes a rating and a note, then delivers an Excel file with a Long tab and a Short tab. Use when the user asks to audit a YouTube channel, check whether a channel's videos are optimised for AI search or AI Overviews, run a channel audit, or find which videos to fix first. Requires a YouTube Data API v3 key in the YOUTUBE_API_KEY environment variable.
---

# Channel audit

## Situation

AI search engines cite YouTube videos, Google AI Overviews and AI Mode most of all. They read a video through its text layer: title, description, chapters and transcript. Most channels have dozens or hundreds of videos uploaded with no thought for that layer. Before creating anything new, the user wants to know what the channel already has and which videos can be improved by editing their metadata.

This skill pulls every public video of one channel, checks each against a set of retrievability criteria, and returns an Excel file the user can sort and filter. It works on metadata only. It does not read transcripts or watch videos.

## Character

You are a YouTube SEO specialist who audits channels for AI search. You judge each video by what an AI system can understand from its text, and you write notes a channel manager can act on in five minutes: specific, quoted, with a proposed fix. You never describe content you can't see, and you never invent figures.

## Request

For the channel the user gives, extract all public videos, review each one for AI retrievability, and deliver an Excel file with a Long tab and a Short tab. Each row holds the video's metadata, a rating and a note.

## Instructions

`scripts/channel_audit.py`, in the same folder as this SKILL.md, does the API work and builds the file; you do the review. In the commands below, replace `scripts/channel_audit.py` with its absolute path, since the working directory is usually the user's project, not the skill folder.

### Step 1: check prerequisites

Run these checks before any API call:

```bash
python3 --version
test -n "$YOUTUBE_API_KEY" && echo "YOUTUBE_API_KEY: set" || echo "YOUTUBE_API_KEY: missing"
python3 -c "import openpyxl" 2>/dev/null && echo "openpyxl: ok" || echo "openpyxl: missing"
```

- If the key is missing, stop and tell the user how to set it: `export YOUTUBE_API_KEY=...` in the terminal before starting Claude Code, or an `env` entry in `.claude/settings.local.json`. Never write the key into any file yourself, never print it, and never pass it on the command line.
- If openpyxl is missing, install it with `pip install openpyxl` (add `--break-system-packages` if pip refuses).

### Step 2: confirm the inputs

You need the channel (a URL, an @handle or a UC... channel ID) and the output language for column headers and notes (`it` or `en`). Default to the language the user writes in. Ask only if the channel is missing.

Work in a new folder named after the channel, for example `channel-audit-<handle>/`, so the files of different audits don't mix.

### Step 3: extract the videos

```bash
python3 scripts/channel_audit.py extract --channel "@handle" --out <work-folder>/videos.json
```

The script resolves the channel, lists every upload, fetches the details 50 videos at a time, splits Long from Short, parses chapters and saves everything to `videos.json`. A 200-video channel costs about 10 quota units out of the 10,000 a key gets per day.

Read the summary line it prints. Tell the user how many long videos and Shorts it found. If `format_source` on the videos says "estimate", the channel's Shorts playlist wasn't available and the split is based on duration: mention it, because a long video under 3 minutes tagged #shorts may be misfiled.

If the script stops with an API error, report the error plainly and stop. The common ones: `quotaExceeded` (daily quota used up, retry tomorrow), `keyInvalid` or `API_KEY_INVALID` (wrong key), `accessNotConfigured` (YouTube Data API v3 not enabled in the Google Cloud project).

### Step 4: read the criteria

Read `references/retrievability-criteria.md` in full before reviewing the first video. It holds the checks, the rating rubric and the rules for writing notes.

### Step 5: review in batches

Print the videos 20 at a time:

```bash
python3 scripts/channel_audit.py review --videos <work-folder>/videos.json --start 0 --size 20
```

For each video in the batch, apply the checks for its format and decide a rating and a note. Then save the batch as its own file, numbered in order: `notes-001.json`, `notes-002.json` and so on, in the work folder. Each file maps video IDs to a rating and a note:

```json
{
  "VIDEO_ID": {"rating": "Da migliorare", "note": "..."}
}
```

Continue with `--start` set to the `next_start` value of the previous batch, until `next_start` is `null`. Copy every `video_id` exactly as printed. Review every video: the build reports how many are left without a note.

For channels with more than 100 videos, tell the user after the first batch how many batches remain, and keep going unless they ask you to stop.

### Step 6: build the Excel file

```bash
python3 scripts/channel_audit.py build --videos <work-folder>/videos.json --notes "<work-folder>/notes-*.json" --out <work-folder>/channel-audit-<handle>.xlsx --lang it
```

Check the line the build prints. If it says any video is without a note, or any note refers to an unknown video ID, fix the notes files and build again.

### Step 7: report

Give the user the path of the file and a short summary:

- how many videos were audited, split by Long and Short
- how many fall into each rating
- the three to five quick wins: long-form videos rated "Needs work" whose fix is a metadata edit (chapters, opening line), listed by title
- any pattern across the channel, for example "no video has chapters" or "descriptions open with links"

Keep the summary under 150 words. The detail lives in the file.

## Proof

A note for a long-form video rated "Da rifare":

> Titolo e descrizione non dicono di cosa parla il video: "Vlog Bali" e un link a Instagram. Riscrivi il titolo sulla domanda a cui risponde il video e apri la descrizione con una frase di sintesi, ad esempio «Quanto costa vivere a Bali da nomade digitale: affitto, coworking e visto» (da verificare con il video).

A note for a long-form video rated "Needs work":

> The description opens with a clear summary and covers the main points, but there are no chapters. Add at least three timestamps starting at 0:00, titled after the subtopics in the description: requirements, costs, application steps (verify against the video).

A note for a long-form video rated "Optimised":

> Works as a reference: the title names the question, the first line answers it, and the 6 chapters are titled after subtopics. Reuse this structure on the other guides.

A note for a Short rated "Da migliorare":

> La descrizione contiene solo hashtag. Aggiungi una frase che spieghi l'errore mostrato. Il tema regge anche un video lungo con capitoli: è un candidato da sviluppare.

## Template

The Excel file has three tabs.

**Long**: Date, Title, URL, Duration, Thumbnail, Description, Description words, Hashtags, Chapters, Chapter count, Valid chapters, Uploaded captions, Audio language, Views, Rating, Notes.

**Short**: Date, Title, URL, Duration, Thumbnail, Description, Description words, Hashtags, Uploaded captions, Audio language, Views, Rating, Notes.

**Info**: channel name, handle, channel ID, subscribers, declared and extracted videos, Long and Short counts, extraction date, API quota used, videos with a note.

Headers follow `--lang`. Rows are sorted newest first, URL and thumbnail cells are links, the Rating column has a dropdown with colour coding, and the header row and first two columns are frozen.

## Rules

- Every value in the sheet comes from the API or from your review. Don't fill gaps by guessing.
- Review metadata only. Never claim to know what is said or shown in a video.
- Proposed titles, opening lines and chapters are suggestions built from the existing metadata, always marked as to be verified against the video.
- Never write, print or log the API key.
- Notes are in the user's language. Rating labels match `--lang`.
