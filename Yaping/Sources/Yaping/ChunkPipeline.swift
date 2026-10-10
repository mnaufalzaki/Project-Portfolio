import Foundation

/// Transcribes the pieces of one recording in order, while the user is still talking.
/// In progressive mode each piece is pasted as soon as it's ready; otherwise everything is joined at the end.
@MainActor
final class ChunkPipeline {
    struct Outcome {
        var text: String
        var raw: String
        var parts: Int
        var failedParts: Int
        var lastError: Error?
        var polishError: Error?
        var pastedAny: Bool
        var pasteBlocked: Bool
        /// e.g. "Gemini: kuota habis → Groq" when a backup engine did (some of) the work.
        var fallbackNote: String?
        var quotaWarning: String?
    }

    let progressive: Bool
    private let settings: AppSettings
    private var tail: Task<Void, Never>?
    private var texts: [String] = []
    private var raws: [String] = []
    private var queued = 0
    private var failedParts = 0
    private var lastError: Error?
    private var polishError: Error?
    private var insertedAny = false
    private var pasteBlocked = false
    private var cancelled = false
    private var fallbackNote: String?
    private var quotaWarning: String?

    private static let minDuration: TimeInterval = 0.4
    static let silenceLevel: Float = 0.12

    init(settings: AppSettings, progressive: Bool) {
        self.settings = settings
        self.progressive = progressive
    }

    var isEmpty: Bool { queued == 0 }

    func add(_ chunk: AudioRecorder.Chunk) {
        queued += 1
        let previous = tail
        tail = Task { [weak self] in
            await previous?.value
            await self?.process(chunk)
        }
    }

    /// Drops whatever hasn't been pasted yet (Esc). Text already pasted stays.
    func cancel() {
        cancelled = true
    }

    func finish() async -> Outcome {
        await tail?.value
        return Outcome(text: texts.joined(separator: " "), raw: raws.joined(separator: " "), parts: queued,
                       failedParts: failedParts, lastError: lastError, polishError: polishError,
                       pastedAny: insertedAny, pasteBlocked: pasteBlocked, fallbackNote: fallbackNote,
                       quotaWarning: quotaWarning)
    }

    private func process(_ chunk: AudioRecorder.Chunk) async {
        defer { try? FileManager.default.removeItem(at: chunk.url) }
        // Silent pieces are skipped: Whisper tends to invent text from silence.
        guard !cancelled, chunk.duration >= Self.minDuration, chunk.peak >= Self.silenceLevel else { return }

        var transcript: String?
        for attempt in 1...2 {
            do {
                let result = try await Transcriber.transcribe(chunk.url, settings: settings)
                transcript = result.text
                if let warning = result.quotaWarning { quotaWarning = warning }
                if !result.skipped.isEmpty {
                    fallbackNote = result.skipped.joined(separator: " · ") + " → \(result.engine.shortName)"
                }
                break
            } catch {
                lastError = error
                Log.write(String(format: "piece %.0fs failed (attempt %d): %@", chunk.duration, attempt, error.localizedDescription))
                if attempt == 1 { try? await Task.sleep(nanoseconds: 1_500_000_000) }
            }
        }
        guard let transcript else { failedParts += 1; return }

        let raw = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cancelled, !raw.isEmpty, !Transcriber.isHallucination(raw) else { return }

        var text = raw
        if settings.cleanupEnabled && raw.split(separator: " ").count >= 3 {
            do {
                text = try await TextCleaner.clean(raw, settings: settings)
            } catch {
                polishError = error
            }
        }
        text = Transcriber.normalize(text)
        guard !cancelled, !text.isEmpty else { return }
        raws.append(raw)
        texts.append(text)

        if progressive {
            // Later pieces always get a space: we know the text before the cursor is our own.
            let pasted = TextInserter.insert(text, restoreClipboard: settings.restoreClipboard,
                                             forceLeadingSpace: insertedAny)
            if pasted { insertedAny = true } else { pasteBlocked = true }
        }
    }
}
