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
| ⚡ | **[ARUS](ARUS/)** | Energy-Aware Compute Intelligence. AI-driven workload placement that predicts runtime and energy per node and recommends the most energy-efficient machine for each job. | Product concept & pitch deck | Python · FastAPI · PostgreSQL · scikit-learn |

### [Yaping](Yaping/)

A lightweight menu-bar app that turns speech into ready-to-send text in any application, designed for mixed Indonesian–English speech.

- Smart cleanup of filler words and self-corrections
- Unlimited-length dictation, transcribed in parallel while you speak
- Automatic engine fallback with free-tier quota tracking
- API keys stored in the macOS Keychain

📖 [Read more](Yaping/README.md) · 🇮🇩 [Bahasa Indonesia](Yaping/README.id.md) · [The story behind it](Yaping/docs/JOURNEY.md)

### [ARUS](ARUS/)

A decision engine that shifts workload placement from "whichever machine is free" to "whichever machine finishes the job with the least energy".

- Predicts runtime and energy (Wh/job) for each candidate node
- Recommends the feasible node with the lowest energy, within performance limits
- Learns from every execution to improve future placements
- Complements existing schedulers (Kubernetes, Slurm) instead of replacing them

📖 [Read more](ARUS/README.md) · 🇮🇩 [Bahasa Indonesia](ARUS/README.id.md) · 📄 [Pitch deck (PDF)](ARUS/docs/ARUS-Pitch-Deck.pdf)

## Repository Structure

```
Project-Portfolio/
├── ARUS/      # Energy-aware workload placement: concept, design & pitch deck
└── Yaping/    # macOS voice dictation app: source code, build scripts & docs
```

Each project is self-contained in its own folder with its own README.

## Contact

**Naufal Zaki** · [naufalzaki.tech](https://naufalzaki.tech) · [@mnaufalzaki](https://github.com/mnaufalzaki)
