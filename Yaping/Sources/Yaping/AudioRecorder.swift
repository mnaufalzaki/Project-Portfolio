import AVFoundation
import CoreAudio
import CoreMedia

enum RecorderError: LocalizedError {
    case noInput, converter

    var errorDescription: String? {
        switch self {
        case .noInput: return "Mikrofon tidak ditemukan"
        case .converter: return "Format audio tidak didukung"
        }
    }
}

/// Records audio to 16 kHz mono Int16 WAV using `AVCaptureSession` + `AVCaptureAudioDataOutput`.
///
/// Why `AVCaptureSession` instead of `AVAudioEngine`:
/// - When a Bluetooth headset (e.g. EarFun Air 2 / AirPods) is the system default input,
///   `AVAudioEngine` forces a 1-2.5s Bluetooth A2DP->HFP profile switch on every start and
///   causes sample-rate mismatches (`16 kHz` vs `44.1 kHz`).
/// - `AVCaptureSession` targets a specific `AVCaptureDevice` (preferring the built-in MacBook
///   mic in Auto mode when default input is Bluetooth/Continuity), cutting start latency to
///   ~35-50 ms while keeping Bluetooth playback audio crystal clear.
/// - `AVCaptureAudioDataOutput` delivers 16 kHz mono Int16 PCM directly on our serial `ioQueue`.
final class AudioRecorder: NSObject, AVCaptureAudioDataOutputSampleBufferDelegate, @unchecked Sendable {
    struct Chunk {
        let url: URL
        let duration: TimeInterval
        let peak: Float
        /// Accumulated time with sustained audio above ambient noise (ignoring initial key-click).
        let speechDuration: TimeInterval
    }

    struct MicDevice: Identifiable, Hashable {
        let id: String
        let name: String
    }

    var onLevel: ((Float) -> Void)?
    /// Called on the main queue each time a chunked recording rolls over to a new file.
    var onChunk: ((Chunk) -> Void)?

    private(set) var peakLevel: Float = 0
    private(set) var duration: TimeInterval = 0
    private(set) var speechDuration: TimeInterval = 0

    private let sessionQueue = DispatchQueue(label: "com.naufalzaki.yaping.capture-session", qos: .userInteractive)
    private let ioQueue = DispatchQueue(label: "com.naufalzaki.yaping.audio-io", qos: .userInitiated)
    private let outFormat = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16_000, channels: 1, interleaved: true)!

    // Owned by `sessionQueue`.
    private var session: AVCaptureSession?
    private var configuredDeviceID: String?
    private var isRecording = false

    // Owned by `ioQueue`.
    private var file: AVAudioFile?
    private var fileURL: URL?
    private var framesWritten: AVAudioFramePosition = 0
    private var currentPeak: Float = 0
    private var currentSpeechDuration: TimeInterval = 0
    private var chunkRange: ClosedRange<TimeInterval>?
    private var silentDuration: TimeInterval = 0

    /// Silence must hold this long before splitting a chunk, avoiding mid-word cuts.
    private static let pauseLevel: Float = 0.15
    private static let pauseHoldDuration: TimeInterval = 0.4
    /// Ignore the very first 150ms of a recording when counting speech so hotkey thuds / Tink sound don't trigger transcription.
    private static let startupIgnoreWindow: TimeInterval = 0.15

    static func availableMicrophones() -> [MicDevice] {
        let discovery = AVCaptureDevice.DiscoverySession(
            deviceTypes: [.microphone],
            mediaType: .audio,
            position: .unspecified
        )
        return discovery.devices
            .filter { $0.transportType != Int32(kAudioDeviceTransportTypeVirtual) }
            .map { MicDevice(id: $0.uniqueID, name: $0.localizedName) }
    }

    /// Pre-configures the `AVCaptureSession` (stopped, mic OFF) so the first dictation starts in ~40 ms.
    func warmUp() {
        guard Permissions.microphone == .authorized else { return }
        let preferredID = AppSettings.shared.microphoneID
        sessionQueue.async { [weak self] in
            guard let self, !self.isRecording else { return }
            _ = try? self.prepareSession(preferredID: preferredID)
        }
    }

    /// Starts recording asynchronously off the Main Thread (~35-50 ms on built-in Mac mic).
    func startAsync(chunked range: ClosedRange<TimeInterval>? = nil) async throws {
        let preferredID = AppSettings.shared.microphoneID
        try await withCheckedThrowingContinuation { (c: CheckedContinuation<Void, Error>) in
            sessionQueue.async { [weak self] in
                guard let self else {
                    c.resume(throwing: RecorderError.noInput)
                    return
                }
                do {
                    try self.startLocked(chunked: range, preferredID: preferredID)
                    c.resume()
                } catch {
                    c.resume(throwing: error)
                }
            }
        }
    }

    /// Stops recording, flushes any queued audio writes, and returns the finished WAV file.
    func stop() -> URL? {
        return sessionQueue.sync {
            guard isRecording else { return nil }
            isRecording = false
            session?.stopRunning()
            return ioQueue.sync {
                Self.close(file)
                file = nil
                let finishedURL = fileURL
                fileURL = nil
                self.duration = Double(framesWritten) / outFormat.sampleRate
                self.peakLevel = currentPeak
                self.speechDuration = currentSpeechDuration
                return finishedURL
            }
        }
    }

    func cancel() {
        if let url = stop() { try? FileManager.default.removeItem(at: url) }
    }

    // MARK: Capture session management (exclusively on `sessionQueue`)

    private func resolveDevice(preferredID: String) -> AVCaptureDevice? {
        let discovery = AVCaptureDevice.DiscoverySession(
            deviceTypes: [.microphone],
            mediaType: .audio,
            position: .unspecified
        )
        let devices = discovery.devices
        guard !devices.isEmpty else { return nil }

        // Explicit user choice if connected.
        if !preferredID.isEmpty, let exact = devices.first(where: { $0.uniqueID == preferredID }) {
            return exact
        }

        // Auto mode: use system default unless it's Bluetooth or Continuity iPhone
        // (which incur 1-2.5s HFP/wireless startup delays); in that case prefer built-in Mac mic.
        let builtIn = devices.first { $0.transportType == Int32(kAudioDeviceTransportTypeBuiltIn) }
        if let sysDefault = AVCaptureDevice.default(for: .audio) {
            let t = UInt32(bitPattern: sysDefault.transportType)
            let isSlowWireless = (t == kAudioDeviceTransportTypeBluetooth)
                || (t == kAudioDeviceTransportTypeBluetoothLE)
                || (t == 0x63707479) // Continuity Camera/Mic ('cpty')
            if isSlowWireless, let builtIn {
                return builtIn
            }
            return sysDefault
        }
        return builtIn ?? devices.first
    }

    private func prepareSession(preferredID: String) throws -> AVCaptureSession {
        guard let device = resolveDevice(preferredID: preferredID) else {
            throw RecorderError.noInput
        }
        if let existing = session, configuredDeviceID == device.uniqueID {
            return existing
        }

        let newSession = AVCaptureSession()
        newSession.beginConfiguration()
        let input = try AVCaptureDeviceInput(device: device)
        guard newSession.canAddInput(input) else {
            newSession.commitConfiguration()
            throw RecorderError.noInput
        }
        newSession.addInput(input)

        let output = AVCaptureAudioDataOutput()
        output.audioSettings = [
            AVFormatIDKey: kAudioFormatLinearPCM,
            AVSampleRateKey: 16_000,
            AVNumberOfChannelsKey: 1,
            AVLinearPCMBitDepthKey: 16,
            AVLinearPCMIsFloatKey: false,
            AVLinearPCMIsBigEndianKey: false,
            AVLinearPCMIsNonInterleaved: false,
        ]
        output.setSampleBufferDelegate(self, queue: ioQueue)
        guard newSession.canAddOutput(output) else {
            newSession.commitConfiguration()
            throw RecorderError.converter
        }
        newSession.addOutput(output)
        newSession.commitConfiguration()

        session = newSession
        configuredDeviceID = device.uniqueID
        Log.write("audio input ready: \(device.localizedName)")
        return newSession
    }

    private func startLocked(chunked range: ClosedRange<TimeInterval>?, preferredID: String) throws {
        let captureSession = try prepareSession(preferredID: preferredID)
        let (url, file) = try makeFile()

        ioQueue.sync {
            self.file = file
            self.fileURL = url
            self.chunkRange = range
            self.framesWritten = 0
            self.currentPeak = 0
            self.currentSpeechDuration = 0
            self.silentDuration = 0
        }
        self.duration = 0
        self.peakLevel = 0
        self.speechDuration = 0

        captureSession.startRunning()
        guard captureSession.isRunning else {
            ioQueue.sync {
                Self.close(self.file)
                self.file = nil
                if let url = self.fileURL { try? FileManager.default.removeItem(at: url) }
                self.fileURL = nil
            }
            // Reset cached session so next attempt rebuilds cleanly.
            session = nil
            configuredDeviceID = nil
            throw RecorderError.noInput
        }
        isRecording = true
    }

    // MARK: Sample buffer delegate (runs exclusively on `ioQueue`)

    func captureOutput(_ output: AVCaptureOutput, didOutput sampleBuffer: CMSampleBuffer, from connection: AVCaptureConnection) {
        guard let file,
              let blockBuffer = CMSampleBufferGetDataBuffer(sampleBuffer) else { return }

        let totalBytes = CMBlockBufferGetDataLength(blockBuffer)
        let frameCount = totalBytes / MemoryLayout<Int16>.size
        guard frameCount > 0,
              let pcm = AVAudioPCMBuffer(pcmFormat: outFormat, frameCapacity: AVAudioFrameCount(frameCount)),
              let dst = pcm.int16ChannelData?[0] else { return }

        let status = CMBlockBufferCopyDataBytes(blockBuffer, atOffset: 0, dataLength: totalBytes, destination: dst)
        guard status == kCMBlockBufferNoErr else { return }
        pcm.frameLength = AVAudioFrameCount(frameCount)

        let level = Self.level(of: dst, count: frameCount)
        currentPeak = max(currentPeak, level)

        try? file.write(from: pcm)
        framesWritten += AVAudioFramePosition(frameCount)

        let bufferSeconds = Double(frameCount) / outFormat.sampleRate
        let elapsedSeconds = Double(framesWritten) / outFormat.sampleRate
        if level < Self.pauseLevel {
            silentDuration += bufferSeconds
        } else {
            silentDuration = 0
            if elapsedSeconds > Self.startupIgnoreWindow {
                currentSpeechDuration += bufferSeconds
            }
        }

        let levelCallback = onLevel
        let chunk = rotateIfDue()
        let chunkCallback = onChunk
        DispatchQueue.main.async {
            levelCallback?(level)
            if let chunk { chunkCallback?(chunk) }
        }
    }

    // MARK: File I/O (exclusively on `ioQueue`)

    private static func close(_ file: AVAudioFile?) {
        if #available(macOS 15.0, *) { file?.close() }
    }

    private func makeFile() throws -> (URL, AVAudioFile) {
        let url = FileManager.default.temporaryDirectory
            .appendingPathComponent("yaping-\(UUID().uuidString).wav")
        let file = try AVAudioFile(forWriting: url, settings: outFormat.settings,
                                   commonFormat: .pcmFormatInt16, interleaved: true)
        return (url, file)
    }

    private func rotateIfDue() -> Chunk? {
        guard let range = chunkRange, let finishedURL = fileURL else { return nil }
        let seconds = Double(framesWritten) / outFormat.sampleRate
        let sustainedPause = silentDuration >= Self.pauseHoldDuration
        guard seconds >= range.upperBound || (seconds >= range.lowerBound && sustainedPause),
              let (url, newFile) = try? makeFile() else { return nil }
        let chunk = Chunk(url: finishedURL, duration: seconds, peak: currentPeak, speechDuration: currentSpeechDuration)
        Self.close(file) // finalize the WAV header before anyone reads the piece
        file = newFile
        fileURL = url
        framesWritten = 0
        currentPeak = 0
        currentSpeechDuration = 0
        silentDuration = 0
        return chunk
    }

    /// RMS of Int16 PCM mapped onto 0…1 over a −50…0 dB range.
    private static func level(of samples: UnsafePointer<Int16>, count: Int) -> Float {
        guard count > 0 else { return 0 }
        var sum: Float = 0
        let scale: Float = 1.0 / 32768.0
        for i in 0..<count {
            let v = Float(samples[i]) * scale
            sum += v * v
        }
        let rms = sqrt(sum / Float(count))
        let db = 20 * log10(max(rms, 1e-7))
        return max(0, min(1, (db + 50) / 50))
    }
}
