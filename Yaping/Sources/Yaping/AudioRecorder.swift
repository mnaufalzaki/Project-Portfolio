import AVFoundation

enum RecorderError: LocalizedError {
    case noInput, converter

    var errorDescription: String? {
        switch self {
        case .noInput: return "Mikrofon tidak ditemukan"
        case .converter: return "Format audio tidak didukung"
        }
    }
}

/// Records the default input to a 16 kHz mono WAV — the format Whisper-style APIs like best.
/// Disk I/O, sample-rate conversion, and chunk rotation run on a dedicated serial queue so the
/// real-time audio tap thread never blocks on disk writes or locks.
final class AudioRecorder {
    /// A finished piece of a chunked (meeting) recording.
    struct Chunk {
        let url: URL
        let duration: TimeInterval
        let peak: Float
        /// Accumulated time with sustained audio above ambient noise (ignoring initial key-click).
        let speechDuration: TimeInterval
    }

    var onLevel: ((Float) -> Void)?
    /// Called on the main queue each time a chunked recording rolls over to a new file.
    var onChunk: ((Chunk) -> Void)?

    private(set) var peakLevel: Float = 0
    private(set) var duration: TimeInterval = 0
    private(set) var speechDuration: TimeInterval = 0

    private var engine: AVAudioEngine?
    private let ioQueue = DispatchQueue(label: "com.naufalzaki.yaping.audio-io", qos: .userInitiated)
    private let outFormat = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16_000, channels: 1, interleaved: true)!

    // State exclusively owned by `ioQueue` while recording.
    private var file: AVAudioFile?
    private var converter: AVAudioConverter?
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

    /// `chunked` rolls over to a new file at the first sustained pause after `range.lowerBound` seconds
    /// (or hard at `upperBound`), so long recordings can be transcribed piece by piece while they run.
    func start(chunked range: ClosedRange<TimeInterval>? = nil) throws {
        // Fresh engine each time so a switched input device (AirPods etc.) gets the right format.
        let engine = AVAudioEngine()
        let input = engine.inputNode
        let inFormat = input.outputFormat(forBus: 0)
        guard inFormat.sampleRate > 0, inFormat.channelCount > 0 else { throw RecorderError.noInput }
        guard let converter = AVAudioConverter(from: inFormat, to: outFormat) else { throw RecorderError.converter }

        let (url, file) = try makeFile()

        ioQueue.sync {
            self.file = file
            self.converter = converter
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

        input.installTap(onBus: 0, bufferSize: 2048, format: inFormat) { [weak self] buffer, _ in
            guard let self else { return }
            let level = Self.level(of: buffer)
            let callback = self.onLevel
            DispatchQueue.main.async { callback?(level) }
            guard let copied = Self.copy(buffer) else { return }
            self.ioQueue.async { [weak self] in
                self?.writeBuffer(copied, level: level)
            }
        }
        engine.prepare()
        do {
            try engine.start()
        } catch {
            input.removeTap(onBus: 0)
            ioQueue.sync {
                Self.close(self.file)
                self.file = nil
                self.converter = nil
                if let url = self.fileURL { try? FileManager.default.removeItem(at: url) }
                self.fileURL = nil
            }
            throw error
        }
        self.engine = engine
    }

    /// Stops recording, flushes any queued audio writes, and returns the finished file.
    func stop() -> URL? {
        engine?.inputNode.removeTap(onBus: 0)
        engine?.stop()
        engine = nil
        return ioQueue.sync {
            Self.close(file)
            file = nil
            converter = nil
            let finishedURL = fileURL
            fileURL = nil
            self.duration = Double(framesWritten) / outFormat.sampleRate
            self.peakLevel = currentPeak
            self.speechDuration = currentSpeechDuration
            return finishedURL
        }
    }

    func cancel() {
        if let url = stop() { try? FileManager.default.removeItem(at: url) }
    }

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

    /// Runs exclusively on `ioQueue`. Converts and writes PCM frames, then rotates if due.
    private func writeBuffer(_ buffer: AVAudioPCMBuffer, level: Float) {
        guard let file, let converter else { return }
        currentPeak = max(currentPeak, level)

        let ratio = outFormat.sampleRate / buffer.format.sampleRate
        let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 64
        var writtenFrames: AVAudioFrameCount = 0
        if let out = AVAudioPCMBuffer(pcmFormat: outFormat, frameCapacity: capacity) {
            var consumed = false
            var error: NSError?
            converter.convert(to: out, error: &error) { _, status in
                if consumed {
                    status.pointee = .noDataNow
                    return nil
                }
                consumed = true
                status.pointee = .haveData
                return buffer
            }
            if error == nil, out.frameLength > 0 {
                try? file.write(from: out)
                writtenFrames = out.frameLength
                framesWritten += AVAudioFramePosition(out.frameLength)
            }
        }

        let bufferSeconds = Double(writtenFrames) / outFormat.sampleRate
        let elapsedSeconds = Double(framesWritten) / outFormat.sampleRate
        if level < Self.pauseLevel {
            silentDuration += bufferSeconds
        } else {
            silentDuration = 0
            if elapsedSeconds > Self.startupIgnoreWindow {
                currentSpeechDuration += bufferSeconds
            }
        }

        if let chunk = rotateIfDue() {
            let chunkCallback = onChunk
            DispatchQueue.main.async { chunkCallback?(chunk) }
        }
    }

    /// Called exclusively on `ioQueue`. Swaps in a fresh file and hands back the finished one.
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

    private static func copy(_ src: AVAudioPCMBuffer) -> AVAudioPCMBuffer? {
        guard let dst = AVAudioPCMBuffer(pcmFormat: src.format, frameCapacity: src.frameLength) else { return nil }
        dst.frameLength = src.frameLength
        let srcList = UnsafeMutableAudioBufferListPointer(UnsafeMutablePointer(mutating: src.audioBufferList))
        let dstList = UnsafeMutableAudioBufferListPointer(dst.mutableAudioBufferList)
        for i in 0..<min(srcList.count, dstList.count) {
            if let srcPtr = srcList[i].mData, let dstPtr = dstList[i].mData {
                let bytes = min(Int(srcList[i].mDataByteSize), Int(dstList[i].mDataByteSize))
                memcpy(dstPtr, srcPtr, bytes)
                dstList[i].mDataByteSize = UInt32(bytes)
            }
        }
        return dst
    }

    /// RMS mapped onto 0…1 over a −50…0 dB range.
    private static func level(of buffer: AVAudioPCMBuffer) -> Float {
        guard let data = buffer.floatChannelData?[0], buffer.frameLength > 0 else { return 0 }
        let n = Int(buffer.frameLength)
        var sum: Float = 0
        for i in 0..<n { sum += data[i] * data[i] }
        let rms = sqrt(sum / Float(n))
        let db = 20 * log10(max(rms, 1e-7))
        return max(0, min(1, (db + 50) / 50))
    }
}
