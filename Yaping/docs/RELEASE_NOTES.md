## Yaping 1.0.1 🎙️

A reliability update: **your API keys now stay saved** across restarts and app updates.

**What's fixed**
- **API keys no longer "disappear."** Keys saved by an earlier build couldn't be replaced by a newer one, so re-entered keys silently failed to save and looked lost after a restart. Keys are now stored so every Yaping version can read and update them, still encrypted in the macOS Keychain.
- **Clearer key handling in Settings.** Paste a key and press **Simpan** (Save). It's then locked as *Tersimpan* (Saved) until you press **Ubah** (Change) or **Hapus** (Remove). Keys are no longer saved on every keystroke.
- **Honest error messages.** If macOS hasn't allowed Yaping to read a key yet, you see that, not "API key missing."

> Upgrading from 1.0? Paste your Gemini and Groq keys once more in *Pengaturan › Mesin AI*. Keys saved by 1.0 can't be migrated, which is exactly the bug this release fixes. After that, they persist.

**Install**
1. Download `Yaping-1.0.1.zip` below, unzip it, and drag **Yaping.app** into **Applications** (replace the old one).
2. Open it. macOS will say it *"could not verify"* Yaping, because free open-source apps aren't notarized by Apple. Go to **System Settings › Privacy & Security**, scroll down and click **Open Anyway**.
3. Enable Yaping under **Accessibility** (*Device Control and Data Access* on macOS 27) and **Input Monitoring**, and allow the microphone.
4. Menu-bar icon › *Pengaturan* › *Mesin AI*: paste a free API key from [Google AI Studio](https://aistudio.google.com/apikey) or [Groq](https://console.groq.com/keys) and press **Simpan**.

Requires an Apple Silicon Mac (M1 or later) running macOS 14 or later.

📄 [Technical documentation (PDF)](https://github.com/mnaufalzaki/Project-Portfolio/blob/main/Yaping/docs/Dokumentasi%20Teknis%20Yaping.pdf) · 📖 [The story behind Yaping](https://github.com/mnaufalzaki/Project-Portfolio/blob/main/Yaping/docs/JOURNEY.md)
