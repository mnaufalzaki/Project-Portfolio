import Foundation

/// `Yaping --selftest file.wav`: runs transcription + polishing on a file and prints timings.
/// Uses the saved settings and keys; never pastes anything.
enum SelfTest {
    static func run(_ url: URL) async {
        let s = AppSettings.shared
        print("engine=\(s.provider.rawValue) backup=\(s.backupProvider?.rawValue ?? "none") polish=\(s.cleanupEnabled ? s.cleanupProvider.rawValue : "off")")
        do {
            if s.cleanupProvider == .groq { await Groq.preconnect() }
            let t0 = Date()
            let result = try await Transcriber.transcribe(url, settings: s)
            let raw = result.text
            let t1 = Date()
            print("chain: \(s.transcriptionChain.map(\.rawValue).joined(separator: " → "))")
            print(String(format: "transcribe: %.2fs via %@", t1.timeIntervalSince(t0), result.engine.rawValue))
            if !result.skipped.isEmpty { print("skipped: \(result.skipped.joined(separator: " · "))") }
            print("raw:      \(raw.trimmingCharacters(in: .whitespacesAndNewlines))")
            for run in 1...2 {
                let start = Date()
                let polished = try await TextCleaner.clean(raw, settings: s)
                print(String(format: "polish #%d: %.2fs", run, Date().timeIntervalSince(start)))
                if run == 1 { print("polished: \(polished)") }
            }
        } catch {
            print("error: \(error.localizedDescription)")
        }
    }
}
