## Yaping 1.0 🎙️

Free, open-source voice dictation for macOS. Press ⌘⌥, speak, press again, and clean text appears wherever your cursor is.

**Highlights**
- Gemini 3.5 Transcribe *smart* mode: fillers removed and self-corrections resolved, without rewording you
- Unlimited-length dictation: a 5-minute take waits **2.3 s** instead of 143 s, thanks to live segmenting
- Primary/backup engines (Gemini → Groq → offline Whisper) with quota tracking in the menu bar
- Indonesian, English and mixed speech

**Install**
1. Download `Yaping-1.0.zip` below, unzip it, and drag **Yaping.app** into **Applications**.
2. Open it. macOS will say it *"could not verify"* Yaping, because free open-source apps aren't notarized by Apple. Go to **System Settings › Privacy & Security**, scroll down and click **Open Anyway**.
3. Enable Yaping under **Accessibility** (*Device Control and Data Access* on macOS 27) and **Input Monitoring**, and allow the microphone.
4. Menu-bar icon › *Pengaturan* › *Mesin AI*: paste a free API key from [Google AI Studio](https://aistudio.google.com/apikey) or [Groq](https://console.groq.com/keys).

Requires an Apple Silicon Mac (M1 or later) running macOS 14 or later.

Read how it was built and tested: [The story behind Yaping](https://github.com/mnaufalzaki/Yaping/blob/main/docs/JOURNEY.md).
