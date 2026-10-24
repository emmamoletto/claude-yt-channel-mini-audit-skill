# claude-youtube-channel-audit-skill

Audit every video on a YouTube channel for AI search. A standalone [Claude skill](https://docs.claude.com/en/docs/agents-and-tools/agent-skills) that pulls all public videos of a channel (long-form and Shorts) with the YouTube Data API v3, has Claude review each one against a set of retrievability criteria, and hands you an Excel file with a rating and an actionable note per video.

Free (the API key costs nothing), and takes about 10 minutes to set up.

**Why:** Google AI Overviews and AI Mode cite YouTube more than almost any other source, and they read a video through its text layer: title, description, chapters and transcript. Most channels have dozens of videos uploaded with no thought for that layer. This skill tells you what a channel already has and which videos you can improve just by editing their metadata, before you make anything new.

**Requirements:** a Claude that runs locally on your machine, meaning [Claude Code](https://claude.com/claude-code) (CLI, desktop app, or IDE extension) or the Claude desktop app, plus Python 3 with `openpyxl`. It won't work on claude.ai in the browser: skills there run in a cloud sandbox that doesn't have your API key.

## What you get

One `.xlsx` file per channel with three tabs:

| Tab | Columns |
|---|---|
| **Long** | Date, Title, URL, Duration, Thumbnail, Description, Description words, Hashtags, Chapters, Chapter count, Valid chapters, Uploaded captions, Audio language, Views, **Rating**, **Notes** |
| **Short** | Date, Title, URL, Duration, Thumbnail, Description, Description words, Hashtags, Uploaded captions, Audio language, Views, **Rating**, **Notes** |
| **Info** | Channel name, handle, ID, subscribers, video counts, extraction date, API quota used |

Each video gets one of three ratings, colour-coded in the sheet:

- **Optimised**: title names the topic, the description opens with a summary, chapters are valid and descriptive. Reuse it as a template.
- **Needs work**: the topic is clear, but the summary opening, description depth or chapters are missing. Fixable by editing metadata.
- **Redo**: title and description together don't say what the video is about. Needs a new title and description.

Example notes:

> The description opens with a clear summary and covers the main points, but there are no chapters. Add at least three timestamps starting at 0:00, titled after the subtopics in the description: requirements, costs, application steps (verify against the video).

> Works as a reference: the title names the question, the first line answers it, and the 6 chapters are titled after subtopics. Reuse this structure on the other guides.

Claude also gives you a short summary in chat: ratings breakdown, the 3 to 5 quick wins, and patterns across the channel (e.g. "no video has chapters").

Column headers, ratings and notes can be in **English or Italian**: Claude picks the language you write in.

## Setup

### 1. Get a YouTube Data API v3 key (one time, ~5 minutes)

1. Create a project at [console.cloud.google.com](https://console.cloud.google.com) (free, no billing needed)
2. **APIs & Services → Library** → search **YouTube Data API v3** → **Enable**
3. **APIs & Services → Credentials → Create credentials → API key**
4. Click the new key → under **API restrictions** pick **Restrict key** → select **YouTube Data API v3** → **Save**. Treat the key like a password.

The free quota is 10,000 units a day. Auditing a 200-video channel uses about 10, so you can audit hundreds of channels a day.

### 2. Download this repo

Click the green **Code** button at the top of this page → **Download ZIP**, and unzip it (or `git clone` if you're comfortable with git).

### 3. Install the skill, the easy way

Open Claude Code (or the Claude desktop app) in the unzipped folder and say:

> Install this skill into my Claude skills folder as "channel-audit" and install its Python dependency. Then tell me how to set my YouTube API key as an environment variable, without writing the key into any file yourself.

Then set the key yourself (step 4), so it never passes through the chat.

<details>
<summary>Manual install (if you'd rather run the commands yourself)</summary>

From inside the unzipped folder:

```bash
# Copy the skill into Claude's skills folder
mkdir -p ~/.claude/skills/channel-audit
cp -r SKILL.md scripts references ~/.claude/skills/channel-audit/

# Python dependency for the Excel file (try pip3 first; plain pip if that fails)
pip3 install openpyxl
```

</details>

### 4. Set your API key

The skill reads the key from the `YOUTUBE_API_KEY` environment variable. On macOS (zsh), add it to your shell profile:

```bash
echo 'export YOUTUBE_API_KEY="paste-your-key-here"' >> ~/.zshrc
```

Then **open a new terminal and restart Claude Code** so it picks up the variable. (On Linux with bash, use `~/.bashrc` instead.)

<details>
<summary>Alternative: set it only for one project</summary>

In the project folder where you run Claude Code, create `.claude/settings.local.json`:

```json
{
  "env": {
    "YOUTUBE_API_KEY": "paste-your-key-here"
  }
}
```

`settings.local.json` is meant to stay out of version control. Double-check it's in your `.gitignore` before committing anything.

</details>

### 5. Run it

In Claude Code, type:

> /channel-audit https://www.youtube.com/@yourchannel

or just ask *"audit this YouTube channel for AI search: @yourchannel"*. The channel can be a URL, an @handle or a `UC...` channel ID, and it doesn't have to be yours: any public channel works, so you can audit competitors too.

Claude creates a `channel-audit-<handle>/` folder in your working directory with the raw data (`videos.json`), its review notes, and the final `.xlsx`.

## How it works

`scripts/channel_audit.py` does the API work; Claude does the review.

1. **extract**: resolves the channel, lists every upload, fetches details 50 videos at a time, separates Long from Shorts (using the channel's own Shorts playlist, or duration as a fallback), and parses chapters against YouTube's rules (first at 0:00, at least 3, ascending, each at least 10 seconds).
2. **review**: prints videos 20 at a time. Claude checks each against [`references/retrievability-criteria.md`](references/retrievability-criteria.md) and writes a rating and a note.
3. **build**: merges data and notes into the Excel file, with clickable links, a rating dropdown, colour coding and frozen headers.

The script also runs on its own (`python3 scripts/channel_audit.py --help`) if you just want the raw export.

## What it does and doesn't do

- It reviews **metadata only**: title, description, chapters, duration, hashtags, tags, caption flag and audio language. It doesn't read transcripts or watch videos, so suggested titles, first lines and chapters are always marked *verify against the video*.
- "Uploaded captions: No" means no captions uploaded by the creator. The API flag doesn't count YouTube's auto-generated captions, so it doesn't mean "no transcript".
- The rating rubric is an editorial framework, not a rule published by Google or any AI platform.

## Security notes

- Your API key only grants read access to **public** YouTube data, but it's tied to your Google Cloud quota. Keep it out of repos and chats, and restrict it to the YouTube Data API v3 (step 1.4).
- The skill tells Claude never to write, print or log the key.

## License

MIT
