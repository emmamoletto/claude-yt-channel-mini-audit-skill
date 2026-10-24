# AI retrievability criteria for YouTube videos

Read this before reviewing the first batch. It explains what to check on each video, why, and how to turn the checks into a rating and a note.

## What the review can and cannot see

The review works on metadata only: title, description, chapters, duration, hashtags, tags, captions flag and audio language. It does not see the transcript or the video itself. So it judges whether an AI system can understand and quote the video from the text around it, not whether the spoken content is good. Never describe what is said in the video unless the title or description states it.

## YouTube's chapter rules

YouTube renders chapters only when the first timestamp is 0:00, there are at least three timestamps in ascending order, and each chapter lasts at least 10 seconds. The script checks these rules and reports any failure in `chapters_problems`.

## Checks for long-form videos

1. **Title.** Does it name the topic, ideally as the question or task a person would search? A title made only of a place name, a mood or an inside joke ("Vlog Bali", "Ci siamo!") gives an AI system nothing to match a query to.
2. **Opening of the description.** Do the first one or two sentences say what the video answers or shows? This is the text most likely to be read as a summary. Links, sponsor lines and social handles in the opening are a missed opportunity.
3. **Description depth.** Does the description cover the main points, entities (places, tools, brands, people) and terms of the video? Use `description_words` as a signal, not a target: a 60-word description rarely carries enough, and a long one full of links and boilerplate does not count as depth.
4. **Chapters.** Are there chapters, do they pass YouTube's rules, and are their titles descriptive? "Intro / Parte 2 / Fine" are valid chapters with no retrieval value. Chapter titles phrased as the subtopics or questions they answer work like headings on a page.
5. **Duration.** Under about 2 minutes, a long-form video may be too thin to work as a reference. This is a weak signal: mention it only when the title promises a full guide.
6. **Hashtags and tags.** A few relevant hashtags help classify the topic. Only flag their absence alongside other gaps.
7. **Captions and language.** `captions_uploaded` is the API's caption flag. It may not count auto-generated captions, so treat "No" as "no captions uploaded by the creator", never as "no transcript". Uploaded captions fix transcription errors on names and technical terms, which matters for retrieval. Flag a missing `audio_language` only as a small fix.
8. **Freshness.** If the title or description promises current information (a year, "latest", rules, prices) and the video is old, suggest an update.

## Checks for Shorts

Shorts are less cited, so judge them lightly:

1. Does the title name the topic?
2. Does the description add at least one sentence of context beyond hashtags?
3. Does the topic deserve a long-form reference video? If the Short answers a real question in a few seconds, say so in the note: that topic is a candidate for a long video with chapters.

Do not penalise Shorts for missing chapters or short duration.

## Ratings

Use exactly one of these per video. When the build uses `--lang it`, write the Italian labels; with `--lang en`, write the English ones. The script accepts either.

| Rating (en) | Rating (it) | When to use it |
| --- | --- | --- |
| Optimised | Ottimizzato | Title names the topic, the description opens with a summary and covers the main points, and (for long-form) chapters are valid and descriptive. At most one small fix left. |
| Needs work | Da migliorare | The topic is clear, but one or more of these is missing: summary opening, depth, valid or descriptive chapters. Fixable by editing metadata. |
| Redo | Da rifare | Title and description together don't say what the video is about, so an AI system has nothing to retrieve. Needs a new title and a rewritten description. |

These thresholds are an editorial rubric, not rules published by any AI platform.

## Writing the note

- One to three sentences, in the user's language.
- Lead with the most valuable fix, then the next one.
- Be specific: quote the weak part and propose the replacement. For example: "The description opens with the Instagram link. Start with one sentence on what the video answers, e.g. «Come ottenere il visto nomade digitale in Spagna: requisiti, costi e tempi nel 2026»."
- When you propose chapter titles or a new first line, build them only from what the title and description say, and add "(verify against the video)" or "(da verificare con il video)" because you have not seen it.
- For an optimised video, say in a few words why it works, so the user can reuse the pattern.
- Never invent statistics, view counts or content.
