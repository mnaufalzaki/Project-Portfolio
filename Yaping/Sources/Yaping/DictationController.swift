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
    private static let minDuration: TimeInterval = 0.5
    private static let minSpeechDuration: TimeInterval = 0.25
    /// Cut at the first pause after 90 s, or hard at 120 s. Longer pieces conserve Gemini's
    /// 25 req/day free quota while M4A compression keeps uploads compact and fast.
    private static let pieceLength: ClosedRange<TimeInterval> = 90...120

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

    /// Retries transcribing the most recent failed audio chunk preserved by FailedRecordings.
    func retryLastFailed() {
        guard state == .idle, let item = FailedRecordings.shared.latest else { return }
        state = .processing
        overlay.show(.processing)
        stayAwake(true)

        Task {
            defer {
                state = .idle
                stayAwake(false)
            }
            do {
                let result = try await Transcriber.transcribe(item.url, settings: settings)
                let raw = result.text.trimmingCharacters(in: .whitespacesAndNewlines)
                guard !raw.isEmpty else {
                    FailedRecordings.shared.remove(item)
                    overlay.hide()
                    return
                }
                let text = Transcriber.normalize(raw)
                FailedRecordings.shared.remove(item)
                let pasted = TextInserter.insert(text, restoreClipboard: settings.restoreClipboard)
                HistoryStore.shared.add(text: text, raw: raw)
                if !pasted {
                    overlay.flash(error: "Teks disalin — tekan ⌘V.")
                } else {
                    overlay.hide()
                }
            } catch {
                overlay.flash(error: "Gagal coba ulang: \(error.localizedDescription)")
            }
        }
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

        let last = AudioRecorder.Chunk(url: url, duration: recorder.duration,
                                       peak: recorder.peakLevel, speechDuration: recorder.speechDuration)
        let spoken = Date().timeIntervalSince(recordingStarted)

        // Skip brief accidental toggles or takes with no sustained voice before calling cloud APIs
        // (saves Gemini daily quota and avoids Whisper silence hallucinations).
        let hasVoice = last.peak >= ChunkPipeline.silenceLevel && last.speechDuration >= Self.minSpeechDuration
        if pipeline.isEmpty && (last.duration < Self.minDuration || !hasVoice) {
            try? FileManager.default.removeItem(at: url)
            state = .idle
            stayAwake(false)
            Log.write(String(format: "skipped: %.1fs audio, speech %.2fs, peak %.2f",
                             last.duration, last.speechDuration, last.peak))
            // Only warn about microphone issues if the user recorded for a noticeable time with no sound.
            if last.duration >= 1.8 && last.peak < ChunkPipeline.silenceLevel {
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
                overlay.flash(error: "\(result.failedParts) bagian gagal ditranskripsi (disimpan di menu bar untuk dicoba ulang).")
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
