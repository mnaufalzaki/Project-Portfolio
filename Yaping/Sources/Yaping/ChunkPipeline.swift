import Foundation

/// Transcribes the pieces of one recording concurrently while preserving strict output order.
/// In progressive mode each piece is pasted as soon as it (and all earlier pieces) are ready;
/// otherwise everything is joined at the end.
@MainActor
final class ChunkPipeline {
    struct Outcome {
        var text: String
        var raw: String
        var parts: Int
        var failedParts: Int
        var lastError: Error?
        var pastedAny: Bool
        var pasteBlocked: Bool
        /// e.g. "Key 1: kuota habis → Key 2" when an earlier key failed over.
        var fallbackNote: String?
        var quotaWarning: String?
    }

    private enum PieceResult {
        case skipped
        case failed(Error?)
        case success(
            text: String,
            raw: String,
            fallbackNote: String?,
            quotaWarning: String?
        )
    }

    let progressive: Bool
    private let settings: AppSettings
    private var emitTail: Task<Void, Never>?
    private var workTasks: [Task<PieceResult, Never>] = []
    private var texts: [String] = []
    private var raws: [String] = []
    private var queued = 0
    private var failedParts = 0
    private var lastError: Error?
    private var insertedAny = false
    private var pasteBlocked = false
    private var cancelled = false
    private var fallbackNote: String?
    private var quotaWarning: String?

    private static let minDuration: TimeInterval = 0.4
    private static let minSpeechDuration: TimeInterval = 0.2
    static let silenceLevel: Float = 0.12

    init(settings: AppSettings, progressive: Bool) {
        self.settings = settings
        self.progressive = progressive
    }

    var isEmpty: Bool { queued == 0 }

    /// Starts transcription immediately (in parallel with earlier chunks) and queues ordered emission.
    func add(_ chunk: AudioRecorder.Chunk, deleteOnFail: Bool = false) {
        queued += 1
        let work = Task { [weak self] () -> PieceResult in
            guard let self else {
                try? FileManager.default.removeItem(at: chunk.url)
                return .skipped
            }
            return await self.transcribePiece(chunk, deleteOnFail: deleteOnFail)
        }
        workTasks.append(work)

        let previousEmit = emitTail
        emitTail = Task { [weak self] in
            await previousEmit?.value
            let result = await work.value
            self?.emit(result)
        }
    }

    /// Drops whatever hasn't been pasted yet (Esc). Text already pasted stays.
    func cancel() {
        cancelled = true
        workTasks.forEach { $0.cancel() }
    }

    func finish() async -> Outcome {
        await emitTail?.value
        return Outcome(text: texts.joined(separator: " "), raw: raws.joined(separator: " "), parts: queued,
                       failedParts: failedParts, lastError: lastError,
                       pastedAny: insertedAny, pasteBlocked: pasteBlocked, fallbackNote: fallbackNote,
                       quotaWarning: quotaWarning)
    }

    private func transcribePiece(_ chunk: AudioRecorder.Chunk, deleteOnFail: Bool) async -> PieceResult {
        // Silent or cancelled pieces are skipped immediately and cleaned up.
        guard !cancelled, !Task.isCancelled,
              chunk.duration >= Self.minDuration,
              chunk.peak >= Self.silenceLevel,
              chunk.speechDuration >= Self.minSpeechDuration else {
            try? FileManager.default.removeItem(at: chunk.url)
            return .skipped
        }

        var result: Transcriber.Transcript?
        var chunkError: Error?
        for attempt in 1...2 {
            guard !cancelled, !Task.isCancelled else {
                try? FileManager.default.removeItem(at: chunk.url)
                return .skipped
            }
            do {
                result = try await Transcriber.transcribe(chunk.url, settings: settings)
                break
            } catch is CancellationError {
                try? FileManager.default.removeItem(at: chunk.url)
                return .skipped
            } catch {
                chunkError = error
                Log.write(String(format: "piece %.0fs failed (attempt %d): %@", chunk.duration, attempt, error.localizedDescription))
                if attempt == 1 { try? await Task.sleep(nanoseconds: 1_500_000_000) }
            }
        }

        guard let result else {
            if !cancelled && !deleteOnFail {
                FailedRecordings.shared.save(from: chunk.url)
            } else {
                try? FileManager.default.removeItem(at: chunk.url)
            }
            return .failed(chunkError)
        }

        // Transcription succeeded: temporary file is no longer needed.
        try? FileManager.default.removeItem(at: chunk.url)

        let raw = result.text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !cancelled, !raw.isEmpty else { return .skipped }

        let note = result.skipped.isEmpty
            ? nil
            : result.skipped.joined(separator: " · ") + " → Key \(result.slot)"

        let text = Transcriber.normalize(raw)
        guard !cancelled, !text.isEmpty else { return .skipped }

        return .success(
            text: text,
            raw: raw,
            fallbackNote: note,
            quotaWarning: result.quotaWarning
        )
    }

    private func emit(_ result: PieceResult) {
        switch result {
        case .skipped:
            break
        case .failed(let error):
            failedParts += 1
            if let error { lastError = error }
        case .success(let text, let raw, let note, let warning):
            if let warning { quotaWarning = warning }
            if let note { fallbackNote = note }
            guard !cancelled else { return }
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
}
