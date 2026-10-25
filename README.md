<div align="center">

# Project-Portfolio

**A collection of projects by Naufal Zaki, from product concepts to shipped software.**

[![Website](https://img.shields.io/badge/website-naufalzaki.tech-0A66C2)](https://naufalzaki.tech)
[![GitHub](https://img.shields.io/badge/GitHub-@mnaufalzaki-181717?logo=github&logoColor=white)](https://github.com/mnaufalzaki)

</div>

---

## Projects

| | Project | Summary | Type | Stack |
|:---:|---|---|---|---|
| <img src="Yaping/docs/icon.png" width="48" alt="Yaping"> | **[Yaping](Yaping/)** | Free, open-source voice dictation for macOS. Press a shortcut, speak, and clean punctuated text appears wherever your cursor is. Supports Gemini, Groq and fully offline whisper.cpp. | Shipped app · v1.0 | Swift · AppKit |
| <img src="ShowUp-Web/docs/icon.png" width="48" alt="ShowUp"> | **[ShowUp](ShowUp-Web/)** | A daily check-in app for four fixed habits. Hold to check in, see an 18-week consistency heatmap instead of streaks, with a personal 21:00 "devices off" countdown. Installable PWA that syncs between phone and laptop. | Shipped web app · PWA | HTML · CSS · JS · Supabase |
| ⚡ | **[ARUS](ARUS/)** | Energy-Aware Compute Intelligence. AI-driven workload placement that predicts runtime and energy per node and recommends the most energy-efficient machine for each job. | Product concept & pitch deck | Python · FastAPI · PostgreSQL · scikit-learn |
| 📚 | **[HEBAT MCP & Agent Skill](HEBAT-UNAIR/)** | A local MCP server and reusable Agent Skill for understanding HEBAT UNAIR assignments, deadlines, submission history, and course materials. | Local prototype · macOS | Python · MCP · Agent Skills |

### [Yaping](Yaping/)

A lightweight menu-bar app that turns speech into ready-to-send text in any application, designed for mixed Indonesian–English speech.

- Smart cleanup of filler words and self-corrections
- Unlimited-length dictation, transcribed in parallel while you speak
- Automatic engine fallback with free-tier quota tracking
- API keys stored in the macOS Keychain

📖 [Read more](Yaping/README.md) · 🇮🇩 [Bahasa Indonesia](Yaping/README.id.md) · [The story behind it](Yaping/docs/JOURNEY.md)

### [ShowUp](ShowUp-Web/)

A deliberately small personal consistency tracker: four fixed habits, one deliberate gesture, no streak counters.

- Hold-to-check-in with a staged celebration that shows the day's count and the last seven days
- 18-week heatmap per habit, so a missed day is one empty square instead of a reset
- Countdown to a personal 21:00 "devices off" deadline
- Installable PWA with offline queue, synced through Supabase with Row Level Security

🚀 [Open the app](https://mnaufalzaki.github.io/Project-Portfolio/ShowUp-Web/) · 📖 [Read more](ShowUp-Web/README.md) · 🇮🇩 [Bahasa Indonesia](ShowUp-Web/README.id.md)

### [ARUS](ARUS/)

A decision engine that shifts workload placement from "whichever machine is free" to "whichever machine finishes the job with the least energy".

- Predicts runtime and energy (Wh/job) for each candidate node
- Recommends the feasible node with the lowest energy, within performance limits
- Learns from every execution to improve future placements
- Complements existing schedulers (Kubernetes, Slurm) instead of replacing them

📖 [Read more](ARUS/README.md) · 🇮🇩 [Bahasa Indonesia](ARUS/README.id.md) · 📄 [Pitch deck (PDF)](ARUS/docs/ARUS-Pitch-Deck.pdf)

### [HEBAT MCP & Agent Skill](HEBAT-UNAIR/)

Ask an AI agent about your university work and get an explanation grounded in HEBAT UNAIR instructions and course documents, with links to the sources.

- Prioritize upcoming assignment deadlines and inspect submission requirements
- Review submission history, while distinguishing personal and group submission status
- Find and read course PDFs, then reuse the same files for follow-up questions
- Keep credentials and sessions in macOS Keychain, with account-specific caches to reduce repeated reads

The Agent Skill guides the conversation; native MCP tools call the reader that retrieves the data and files. Campus access is read-only. Native Codex reads have been tested; Claude Code integration is connected, with full model conversations still unverified.

📖 [Read more](HEBAT-UNAIR/README.md) · [Installation](HEBAT-UNAIR/docs/INSTALLATION.md) · [How it works](HEBAT-UNAIR/README.md#bagaimana-komponennya-bekerja) · [Testing and limitations](HEBAT-UNAIR/docs/TESTING.md)

## Repository Structure

```
Project-Portfolio/
├── ARUS/         # Energy-aware workload placement: concept, design & pitch deck
├── HEBAT-UNAIR/  # University assistant: MCP runtime, Agent Skill, tests & docs
├── ShowUp-Web/   # Daily check-in PWA: app, Supabase schema & docs
└── Yaping/       # macOS voice dictation app: source code, build scripts & docs
```

Each project is self-contained in its own folder with its own README.

## Contact

**Naufal Zaki** · [naufalzaki.tech](https://naufalzaki.tech) · [@mnaufalzaki](https://github.com/mnaufalzaki)
