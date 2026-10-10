import AppKit

/// Toggle mode: press the hotkey to start, press again to transcribe, clean up and paste.
/// Hold mode: hold to record, release to finish; a quick tap locks recording on (hands-free).
/// Long takes are cut into ~1-minute pieces at pauses and transcribed while the user keeps talking,
/// so the wait after stopping stays short however long they spoke.
@MainActor
final class DictationController: ObservableObject {
    enum State: Equatable {
        case idle
        case recording(locked: Bool)
        case processing
    }

    @Published private(set) var state: State = .idle

    private let recorder = AudioRecorder()
    private let overlay = OverlayController()
    private let settings = AppSettings.shared
    private var pressedAt = Date()
    /// The hotkey is still physically down from the press that started this take.
    private var heldSinceStart = false
    private var pipeline: ChunkPipeline?
    private var recordingStarted = Date()
    /// Keeps the Mac awake while recording and transcribing.
    private var awake: NSObjectProtocol?

    private static let tapThreshold: TimeInterval = 0.3
    private static let minDuration: TimeInterval = 0.4
    /// Cut at the first pause after 45 s, or hard at 75 s. Gemini handles ~1-minute pieces far
    /// faster per second of audio than long ones (8 s for 1 min vs 143 s for 5 min in testing).
    private static let pieceLength: ClosedRange<TimeInterval> = 45...75

    init() {
        recorder.onLevel = { [weak self] level in self?.overlay.model.push(level) }
        recorder.onChunk = { [weak self] chunk in self?.pipeline?.add(chunk) }
    }

    func hotkeyDown() {
        switch state {
        case .idle:
            pressedAt = Date()
            heldSinceStart = true
            startRecording(locked: settings.hotkeyMode == .toggle)
        case .recording(locked: true):
            finishRecording()
        default:
            break
        }
    }

    func hotkeyUp() {
        heldSinceStart = false
        guard state == .recording(locked: false) else { return }
        if Date().timeIntervalSince(pressedAt) < Self.tapThreshold {
            state = .recording(locked: true)
            overlay.show(.recording(locked: true))
        } else {
            finishRecording()
        }
    }

    func toggle() {
        switch state {
        case .idle: startRecording(locked: true)
        case .recording: finishRecording()
        case .processing: break
        }
    }

    func cancel(silently: Bool = false) {
        guard case .recording = state else { return }
        recorder.cancel()
        pipeline?.cancel()
        pipeline = nil
        stayAwake(false)
        state = .idle
        overlay.hide()
        if !silently { sound("Funk") }
    }

    /// A key joined the hotkey on the press that started recording (e.g. ⌘⌥D): it was a shortcut, drop the take.
    func shortcutPressed() {
        guard case .recording = state, heldSinceStart else { return }
        heldSinceStart = false
        cancel(silently: true)
    }

    func pasteLast() {
        guard let last = HistoryStore.shared.entries.first else { return }
        TextInserter.insert(last.text, restoreClipboard: settings.restoreClipboard)
    }

    private func startRecording(locked: Bool) {
        switch Permissions.microphone {
        case .notDetermined:
            Permissions.requestMicrophone()
            return
        case .denied, .restricted:
            overlay.flash(error: "Izinkan mikrofon di System Settings")
            Permissions.openMicrophoneSettings()
            return
        default:
            break
        }
        do {
            pipeline = ChunkPipeline(settings: settings, progressive: settings.progressiveInsert)
            try recorder.start(chunked: Self.pieceLength)
            recordingStarted = Date()
            stayAwake(true)
            if settings.cleanupEnabled && settings.cleanupProvider == .groq {
                Task.detached { await Groq.preconnect() }
            }
            state = .recording(locked: locked)
            overlay.show(.recording(locked: locked))
            sound("Tink")
        } catch {
            pipeline = nil
            overlay.flash(error: error.localizedDescription)
        }
    }

    private func finishRecording() {
        guard let url = recorder.stop(), let pipeline else {
            state = .idle
            stayAwake(false)
            overlay.hide()
            return
        }
        self.pipeline = nil
        sound("Pop")

        let last = AudioRecorder.Chunk(url: url, duration: recorder.duration, peak: recorder.peakLevel)
        let spoken = Date().timeIntervalSince(recordingStarted)

        // A short take that's too brief or silent: nothing to transcribe (and Whisper would hallucinate).
        if pipeline.isEmpty && (last.duration < Self.minDuration || last.peak < ChunkPipeline.silenceLevel) {
            try? FileManager.default.removeItem(at: url)
            state = .idle
            stayAwake(false)
            Log.write(String(format: "skipped: %.1fs audio, peak %.2f", last.duration, last.peak))
            if last.duration >= Self.minDuration {
                overlay.flash(error: "Tidak ada suara terdengar — cek mikrofon di System Settings › Sound")
            } else {
                overlay.hide()
            }
            return
        }

        pipeline.add(last)
        state = .processing
        overlay.show(.processing)
        let stopped = Date()
        Task {
            defer {
                state = .idle
                stayAwake(false)
            }
            let result = await pipeline.finish()
            let wait = Date().timeIntervalSince(stopped)

            guard !result.text.isEmpty else {
                Log.write(String(format: "nothing transcribed: %.1fs audio · %d pieces · wait %.2fs", spoken, result.parts, wait))
                if let error = result.lastError {
                    overlay.flash(error: error.localizedDescription)
                } else {
                    overlay.hide()
                }
                return
            }

            var pasted = !result.pasteBlocked
            if pipeline.progressive {
                // Pieces were pasted as they came; if pasting was blocked, hand over the whole text instead.
                if result.pasteBlocked { _ = TextInserter.insert(result.text, restoreClipboard: false) }
            } else {
                pasted = TextInserter.insert(result.text, restoreClipboard: settings.restoreClipboard)
            }
            HistoryStore.shared.add(text: result.text, raw: result.raw)

            Log.write(String(format: "ok: %.1fs audio · %d pieces · wait after stop %.2fs · %d words · pasted=%@%@%@",
                             spoken, result.parts, wait, result.text.split(separator: " ").count,
                             pasted ? "yes" : "no",
                             result.failedParts > 0 ? " · \(result.failedParts) piece(s) failed" : "",
                             result.fallbackNote.map { " · fallback: \($0)" } ?? ""))

            if !pasted {
                overlay.flash(error: "Teks disalin — tekan ⌘V. Izinkan Accessibility agar otomatis.")
            } else if result.failedParts > 0 {
                overlay.flash(error: "\(result.failedParts) bagian (±1 menit) gagal ditranskripsi — sisanya sudah ditempel.")
            } else if let note = result.fallbackNote {
                overlay.flash(error: "Pakai cadangan — \(note)")
            } else if let polishError = result.polishError {
                overlay.flash(error: "Sebagian teks mentah — perapian gagal: \(polishError.localizedDescription)")
            } else if let warning = result.quotaWarning {
                overlay.flash(error: warning)
            } else {
                overlay.hide()
            }
        }
    }

    private func stayAwake(_ on: Bool) {
        if on, awake == nil {
            awake = ProcessInfo.processInfo.beginActivity(options: [.idleSystemSleepDisabled, .userInitiated],
                                                          reason: "Yaping sedang merekam dan mentranskripsi")
        } else if !on, let token = awake {
            ProcessInfo.processInfo.endActivity(token)
            awake = nil
        }
    }

    private func sound(_ name: String) {
        guard settings.playSounds else { return }
        NSSound(named: NSSound.Name(name))?.play()
    }
}
