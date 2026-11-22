import AVFoundation
import Foundation

/// Compresses 16 kHz mono WAV recordings into compact M4A (AAC 32 kbps) before cloud upload.
/// Falls back to the original WAV if AAC encoding fails for any reason.
enum AudioCompressor {
    struct Payload {
        let data: Data
        let mimeType: String
        let filename: String
    }

    static func compressForCloud(_ wavURL: URL) throws -> Payload {
        if let m4aData = encodeAAC(from: wavURL) {
            return Payload(data: m4aData, mimeType: "audio/mp4", filename: "audio.m4a")
        }
        return Payload(data: try Data(contentsOf: wavURL), mimeType: "audio/wav", filename: "audio.wav")
    }

    private static func encodeAAC(from wavURL: URL) -> Data? {
        let tmpURL = FileManager.default.temporaryDirectory
            .appendingPathComponent("yaping-aac-\(UUID().uuidString).m4a")
        defer { try? FileManager.default.removeItem(at: tmpURL) }

        do {
            try writeAAC(from: wavURL, to: tmpURL)
            let data = try Data(contentsOf: tmpURL)
            return data.isEmpty ? nil : data
        } catch {
            Log.write("audio compress fallback to wav: \(error.localizedDescription)")
            return nil
        }
    }

    /// Scoped so `outFile` is closed and deallocated (finalizing the MP4 moov atom) before reading.
    private static func writeAAC(from wavURL: URL, to m4aURL: URL) throws {
        let inFile = try AVAudioFile(forReading: wavURL)
        let format = inFile.processingFormat
        let settings: [String: Any] = [
            AVFormatIDKey: kAudioFormatMPEG4AAC,
            AVSampleRateKey: format.sampleRate,
            AVNumberOfChannelsKey: format.channelCount,
            AVEncoderBitRateKey: 32_000,
        ]
        let outFile = try AVAudioFile(forWriting: m4aURL, settings: settings)
        let chunkFrames: AVAudioFrameCount = 8192
        guard let buffer = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: chunkFrames) else {
            throw RecorderError.converter
        }
        while inFile.framePosition < inFile.length {
            try inFile.read(into: buffer)
            guard buffer.frameLength > 0 else { break }
            try outFile.write(from: buffer)
        }
        if #available(macOS 15.0, *) { outFile.close() }
    }
}
