# The story behind Yaping

🇬🇧 English · 🇮🇩 [Bahasa Indonesia](JOURNEY.id.md)

Yaping went from an empty folder to a daily-driver dictation app in a single day: **10 October 2026**. It started with one sentence: *"make me an app like Wispr Flow."*

It was built by **Naufal Zaki**, who directed and tested every step, most of it by voice through Yaping itself, without typing code by hand. [Claude Code](https://claude.com/claude-code) acted as the pair-programmer. Every design decision below was driven by real tests on a real MacBook (Apple M3, 16 GB). Each number on this page comes from Yaping's own timing log, which records only durations and word counts, never what was said.

---

## 1. First version: local and free

The goal was "free, and running locally on my Mac." The first build combined:

- **whisper.cpp** with `large-v3-turbo` for speech-to-text, kept warm as a background server
- **Qwen 3.5 9B** running in Ollama for paraphrasing and grammar fixes

| Test (synthetic Indonesian clip, 13 s) | Result |
| --- | --- |
| Local Whisper transcription | **~3.0 s**, every word correct |
| Local Qwen paraphrase | **~2.0 s**. It correctly turned *"jam tiga, eh bukan, maksudnya jam empat"* ("three, no wait, I mean four o'clock") into "16.00" |

**An experiment we rejected.** Shrinking Whisper's audio window made transcription faster (3.0 s → 1.8 s), but at some window sizes the output turned into garbage: random scripts and invented words. Speed isn't worth wrong text, so the trick was dropped.

## 2. Paraphrasing: removed on purpose

Paraphrasing moved to Groq's free API for better quality. Then a real dictation stalled for **46 seconds** while Groq hung. The fix was a 6-second limit with an automatic backup model, which brought the worst case down to about 11 seconds and a typical rewrite to under 1 second.

Then came a product decision: **the raw transcript read better.** Paraphrasing made casual speech overly formal ("gimana" → "bagaimana") and sometimes lost nuance. The AI rewrite was switched off by default.

## 3. Gemini vs Groq: a head-to-head test

Naufal dictated comparable passages with each engine:

| | Groq (Whisper turbo) | **Gemini 3.5 Transcribe** |
| --- | --- | --- |
| Punctuation | None: 64 words in one run-on sentence | Clean sentences and commas throughout |
| Brand names | "Grog" in one place, "Groq" in another | "Gemini 3.5 transcribe" and "Groq" both spelled right |
| Speed | 2.4 s (33 s of audio) | 3.3 s (46 s of audio) |

**Gemini won clearly.** Its *smart* mode removes "uh/um" and resolves self-corrections without rewording you, which is exactly the middle ground between raw text and a paraphrase.

## 4. The 5-minute quality-control test

Could Yaping handle a long monologue, such as a meeting? Naufal spoke for five minutes straight.

It worked, and every word arrived. But the wait was **143 seconds**, and the data showed why: Gemini slows down disproportionately on long audio.

| Audio length | Processing time | Seconds per second of speech |
| --- | --- | --- |
| 24 s | 3.1 s | 0.12 |
| 59 s | 8.2 s | 0.14 |
| 85 s | 14.8 s | 0.17 |
| **306 s (5 min)** | **143.0 s** | **0.47**, nearly 4× worse |

The original estimate had been about 45 seconds. The test proved it wrong, and that is exactly why the test was run.

## 5. Chunking: from 143 s to 2.3 s

The fix: split long recordings at natural pauses into roughly 1-minute pieces and transcribe each one **while the user is still talking**. When you stop, only the last piece is left. The pieces were sized from the table above: about a minute of audio is the sweet spot for speed.

Then the same 5-minute test was run again:

| | Before | **After chunking** |
| --- | --- | --- |
| Length | 5 min 6 s | 4 min 58 s |
| Pieces | 1 | 7 |
| **Wait after stopping** | **143 s** | **2.3 s** (about 60× faster) |
| Failed pieces | n/a | 0 |

Text now also appears progressively, piece by piece, while you keep talking.

## 6. Hitting the free-tier wall, then designing around it

Mid-session, one piece came back empty. The log showed the cause: **Gemini's free tier allows only 25 requests per day**, and that day's tests had used them all up. One minute of speech was lost.

The response was a fallback chain with quota awareness:

```
Gemini (primary) ──▶ Groq (backup) ──▶ local Whisper (offline)
```

Yaping now reads the exact retry time from Google's error (*"retry in 10h59m"*), skips Gemini until then, and shows the remaining quota in the menu bar.

**Proven under fire.** Shortly after shipping, a real 85-second dictation met *two* failures in a row: Gemini's quota was exhausted, **then the Wi-Fi dropped while Groq was transcribing**. Yaping fell through to local Whisper and delivered all 129 words without losing a sentence.

## 7. Small fixes found by using it

Living with the app surfaced issues no spec would have predicted:

- whisper.cpp put every phrase on its own line → segments are now joined into flowing text
- Back-to-back dictations ran together ("bagaimana?Tapi") → smart spacing based on the character before the cursor
- Whisper wrote a breath after a pause as "Hai" → removed mid-text, but kept as a real greeting at the start
- Technical words were misheard ("CPP" → "pipi", "API" → "EPK") → a custom vocabulary, which Gemini enforces
- On macOS 27, Accessibility moved to *Device Control and Data Access* → the docs and permission buttons were updated

## Where it landed

| | |
| --- | --- |
| Short dictation | ~1.5–3 s from stop to text |
| 5-minute dictation | ~2–10 s from stop to text |
| Languages | Indonesian, English and mixed |
| Cost | Free |
| Idle footprint | ~190 MB RAM, ~0.5% CPU |

The lesson that runs through every step: **measure, don't guess.** Each time an estimate met a real test, the test won, and the app got better for it.
