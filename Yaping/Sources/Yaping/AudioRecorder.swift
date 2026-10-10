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
final class AudioRecorder {
    /// A finished piece of a chunked (meeting) recording.
    struct Chunk {
        let url: URL
        let duration: TimeInterval
        let peak: Float
    }

    var onLevel: ((Float) -> Void)?
    /// Called on the main queue each time a chunked recording rolls over to a new file.
    var onChunk: ((Chunk) -> Void)?

    private(set) var peakLevel: Float = 0
    private var engine: AVAudioEngine?
    private var file: AVAudioFile?
    private var converter: AVAudioConverter?
    private var fileURL: URL?
    private var framesWritten: AVAudioFramePosition = 0
    private var chunkRange: ClosedRange<TimeInterval>?
    private let lock = NSLock()
    private let outFormat = AVAudioFormat(commonFormat: .pcmFormatInt16, sampleRate: 16_000, channels: 1, interleaved: true)!

    var duration: TimeInterval { Double(framesWritten) / outFormat.sampleRate }

    /// `chunked` rolls over to a new file at the first pause after `range.lowerBound` seconds
    /// (or hard at `upperBound`), so long recordings can be transcribed piece by piece while they run.
    func start(chunked range: ClosedRange<TimeInterval>? = nil) throws {
        // Fresh engine each time so a switched input device (AirPods etc.) gets the right format.
        let engine = AVAudioEngine()
        let input = engine.inputNode
        let inFormat = input.outputFormat(forBus: 0)
        guard inFormat.sampleRate > 0, inFormat.channelCount > 0 else { throw RecorderError.noInput }
        guard let converter = AVAudioConverter(from: inFormat, to: outFormat) else { throw RecorderError.converter }

        let (url, file) = try makeFile()

        lock.lock()
        self.file = file
        self.converter = converter
        self.fileURL = url
        chunkRange = range
        framesWritten = 0
        peakLevel = 0
        lock.unlock()

        input.installTap(onBus: 0, bufferSize: 2048, format: inFormat) { [weak self] buffer, _ in
            self?.process(buffer)
        }
        engine.prepare()
        do {
            try engine.start()
        } catch {
            input.removeTap(onBus: 0)
            throw error
        }
        self.engine = engine
    }

    /// Stops recording and returns the finished file.
    func stop() -> URL? {
        engine?.inputNode.removeTap(onBus: 0)
        engine?.stop()
        engine = nil
        lock.lock()
        defer { lock.unlock() }
        Self.close(file)
        file = nil
        converter = nil
        return fileURL
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

    /// Called with the lock held. Swaps in a fresh file and hands back the finished one.
    private func rotateIfDue(level: Float) -> Chunk? {
        guard let range = chunkRange, let finishedURL = fileURL else { return nil }
        let seconds = duration
        let pause = level < 0.15
        guard seconds >= range.upperBound || (seconds >= range.lowerBound && pause),
              let (url, newFile) = try? makeFile() else { return nil }
        let chunk = Chunk(url: finishedURL, duration: seconds, peak: peakLevel)
        Self.close(file)   // finalize the WAV header before anyone reads the piece
        file = newFile
        fileURL = url
        framesWritten = 0
        peakLevel = 0
        return chunk
    }

    private func process(_ buffer: AVAudioPCMBuffer) {
        let level = Self.level(of: buffer)

        lock.lock()
        guard let file, let converter else { lock.unlock(); return }
        peakLevel = max(peakLevel, level)

        let ratio = outFormat.sampleRate / buffer.format.sampleRate
        let capacity = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 64
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
                framesWritten += AVAudioFramePosition(out.frameLength)
            }
        }
        let chunk = rotateIfDue(level: level)
        lock.unlock()

        let callback = onLevel
        let chunkCallback = onChunk
        DispatchQueue.main.async {
            callback?(level)
            if let chunk { chunkCallback?(chunk) }
        }
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
