import Foundation

/// `Yaping --selftest file.wav`: runs Gemini transcription on a file and prints timings.
/// Uses the saved settings and keys; never pastes anything.
enum SelfTest {
    static func run(_ url: URL) async {
        let s = AppSettings.shared
        let slots = s.configuredGeminiSlots
        print("model=\(s.effectiveGeminiModel) smart=\(s.geminiSmart) keys=\(slots)")
        do {
            let t0 = Date()
            let result = try await Transcriber.transcribe(url, settings: s)
            let t1 = Date()
            print(String(format: "transcribe: %.2fs via Gemini Key %d", t1.timeIntervalSince(t0), result.slot))
            if !result.skipped.isEmpty { print("skipped: \(result.skipped.joined(separator: " · "))") }
            print("text: \(result.text.trimmingCharacters(in: .whitespacesAndNewlines))")
        } catch {
            print("error: \(error.localizedDescription)")
        }
    }
}
