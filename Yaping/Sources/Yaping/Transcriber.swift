import Foundation
import Speech

enum YapingError: LocalizedError {
    case missingKey(String)
    /// The key exists but macOS won't hand it to Yaping yet.
    case keyLocked(String)
    case http(Int, String)
    case badResponse
    case permission(String)
    case unavailable(String)
    /// Every engine in the chain failed; one short reason per engine.
    case allFailed([String])

    var errorDescription: String? {
        switch self {
        case .missingKey(let who): return "API key \(who) belum diisi"
        case .keyLocked(let who): return "Yaping belum diizinkan membaca API key \(who) — buka Pengaturan › Mesin AI"
        case .http(let code, let msg): return "Error \(code): \(msg)"
        case .badResponse: return "Respons server tidak dikenali"
        case .permission(let what): return "Izin \(what) ditolak"
        case .unavailable(let what): return what
        case .allFailed(let reasons): return reasons.joined(separator: " · ")
        }
    }
}

enum HTTP {
    /// `onResponse` sees every HTTP response, including errors (used to read rate-limit headers).
    static func send(_ req: URLRequest, body: Data,
                     onResponse: ((HTTPURLResponse) -> Void)? = nil) async throws -> [String: Any] {
        let (data, resp) = try await URLSession.shared.upload(for: req, from: body)
        if let http = resp as? HTTPURLResponse { onResponse?(http) }
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        guard (200..<300).contains(code) else {
            let message = (json?["error"] as? [String: Any])?["message"] as? String
                ?? String(data: data, encoding: .utf8)?.prefix(200).description
                ?? "?"
            throw YapingError.http(code, message)
        }
        guard let json else { throw YapingError.badResponse }
        return json
    }
}

enum Transcriber {
    struct Transcript {
        let text: String
        let engine: TranscriptionProvider
        /// Engines tried before `engine`, with why they were skipped — empty when the primary worked.
        let skipped: [String]
        /// "Kuota Gemini tinggal ±5 hari ini" when a free tier is running low.
        var quotaWarning: String?
    }

    /// Tries the primary engine, then the backup, then local Whisper (see `AppSettings.transcriptionChain`).
    static func transcribe(_ url: URL, settings s: AppSettings) async throws -> Transcript {
        var skipped: [String] = []
        for engine in s.transcriptionChain {
            // An engine that hit its limit sits out until the provider said it may be retried.
            if let until = Quota.shared.blockedUntil(engine) {
                skipped.append("\(engine.shortName): kuota habis s/d \(until.formatted(date: .omitted, time: .shortened))")
                continue
            }
            do {
                let text = tidy(try await rawTranscript(url, engine: engine, settings: s))
                if !skipped.isEmpty { Log.write("transcribed via \(engine.rawValue) after: \(skipped.joined(separator: "; "))") }
                var transcript = Transcript(text: text, engine: engine, skipped: skipped)
                if engine == .gemini { transcript.quotaWarning = Quota.shared.recordGeminiSuccess() }
                if engine == .groq { transcript.quotaWarning = lastGroqWarning.take() }
                return transcript
            } catch is CancellationError {
                throw CancellationError()
            } catch {
                if case YapingError.http(429, let message) = error {
                    Quota.shared.recordLimitHit(engine, message: message)
                }
                Log.write("transcribe via \(engine.rawValue) failed: \(error.localizedDescription)")
                skipped.append("\(engine.shortName): \(shortReason(error))")
            }
        }
        throw YapingError.allFailed(skipped)
    }

    /// Groq's low-quota warning, read from response headers and picked up once by the transcript.
    private static let lastGroqWarning = Slot<String>()

    private static func shortReason(_ error: Error) -> String {
        switch error {
        case YapingError.http(429, _): return "kuota habis"
        case YapingError.http(401, _), YapingError.http(403, _): return "API key ditolak"
        case YapingError.http(let code, _): return "error \(code)"
        case YapingError.missingKey: return "API key belum diisi"
        case YapingError.keyLocked: return "akses key belum diizinkan"
        case is URLError: return "internet bermasalah"
        default: return String(error.localizedDescription.prefix(80))
        }
    }

    /// whisper.cpp returns one line per segment (" Coba aku ngomong\n Tapi coba") with stray spaces.
    /// Joins segments into flowing text, ending a segment with a period when the next one starts a new sentence.
    static func tidy(_ text: String) -> String {
        let segments = text.components(separatedBy: .newlines)
            .map { $0.split(whereSeparator: \.isWhitespace).joined(separator: " ") }
            .filter { !$0.isEmpty }
        var out = ""
        for var segment in segments {
            if !out.isEmpty { segment = dropFillerHai(segment) }
            guard !segment.isEmpty else { continue }
            guard let last = out.last, let first = segment.first else { out = segment; continue }
            let closesSentence = ".?!…,;:".contains(last)
            out += (!closesSentence && first.isUppercase ? ". " : " ") + segment
        }
        guard let first = out.first else { return out }
        return first.uppercased() + out.dropFirst()
    }

    /// Phrases Whisper invents from near-silence (it was trained on video subtitles).
    private static let hallucinations: Set<String> = [
        "terima kasih telah menonton", "terima kasih sudah menonton", "terima kasih telah menyaksikan",
        "sampai jumpa di video berikutnya", "jangan lupa subscribe", "thank you for watching",
        "thanks for watching", "please subscribe", "subtitles by the amara org community",
    ]

    static func isHallucination(_ text: String) -> Bool {
        let key = text.lowercased()
            .components(separatedBy: CharacterSet.letters.union(.whitespaces).inverted).joined()
            .split(separator: " ").joined(separator: " ")
        return hallucinations.contains(key)
    }

    /// LLMs sometimes emit typographic hyphens/spaces (e.g. "di‑improve" with U+2011) that look odd in chat apps.
    static func normalize(_ text: String) -> String {
        var t = text
        for (from, to) in [("\u{2011}", "-"), ("\u{2010}", "-"), ("\u{00A0}", " "), ("\u{202F}", " "), ("\u{200B}", "")] {
            t = t.replacingOccurrences(of: from, with: to)
        }
        return t.trimmingCharacters(in: .whitespacesAndNewlines)
    }

    /// Whisper often writes a breath or "eh" after a pause as "Hai". Mid-dictation it's never a greeting.
    private static func dropFillerHai(_ segment: String) -> String {
        guard let match = segment.range(of: #"^[Hh]ai\b[,.!]?\s*"#, options: .regularExpression) else { return segment }
        let rest = segment[match.upperBound...]
        guard let first = rest.first else { return "" }
        return first.uppercased() + rest.dropFirst()
    }

    private static func rawTranscript(_ url: URL, engine: TranscriptionProvider, settings s: AppSettings) async throws -> String {
        switch engine {
        case .local:
            return try await LocalWhisper.shared.transcribe(url, language: s.language,
                                                            prompt: s.vocabularyTerms.joined(separator: ", "))
        case .apple:
            return try await AppleTranscriber.transcribe(url, language: s.language, vocabulary: s.vocabularyTerms)
        case .gemini:
            return try await GeminiTranscriber.transcribe(url, model: s.model(for: .gemini), settings: s)
        case .groq, .openai, .custom:
            return try await whisper(url, engine: engine, settings: s)
        }
    }

    /// OpenAI-compatible `/audio/transcriptions` (Groq, OpenAI, local servers).
    private static func whisper(_ url: URL, engine: TranscriptionProvider, settings s: AppSettings) async throws -> String {
        // Custom endpoints (e.g. a local server) may not need a key at all.
        let key = engine == .custom ? s.key(for: engine) : try KeyStore.required(engine.rawValue, name: engine.shortName)
        guard let endpoint = URL(string: s.baseURL(for: engine))?.appendingPathComponent("audio/transcriptions") else {
            throw YapingError.unavailable("Base URL tidak valid")
        }

        var form = Multipart()
        form.field("model", s.model(for: engine))
        form.field("response_format", "json")
        form.field("temperature", "0")
        if s.language != "auto" { form.field("language", s.language) }
        let terms = s.vocabularyTerms
        if !terms.isEmpty { form.field("prompt", terms.joined(separator: ", ")) }
        form.file("file", filename: "audio.wav", type: "audio/wav", data: try Data(contentsOf: url))

        var req = URLRequest(url: endpoint, timeoutInterval: 60)
        req.httpMethod = "POST"
        req.setValue(form.contentType, forHTTPHeaderField: "Content-Type")
        if !key.isEmpty { req.setValue("Bearer \(key)", forHTTPHeaderField: "Authorization") }
        let body = form.finish()

        let json = try await HTTP.send(req, body: body) { response in
            if engine == .groq, let warning = Quota.shared.recordGroq(response) { lastGroqWarning.put(warning) }
        }
        guard let text = json["text"] as? String else { throw YapingError.badResponse }
        return text
    }
}

/// A tiny thread-safe single value, handed from a network callback to the code that awaits it.
final class Slot<T> {
    private var value: T?
    private let lock = NSLock()

    func put(_ newValue: T) {
        lock.lock(); value = newValue; lock.unlock()
    }

    func take() -> T? {
        lock.lock(); defer { lock.unlock() }
        let current = value
        value = nil
        return current
    }
}

/// On-device fallback using Apple's speech recognizer — no key, lower accuracy.
enum AppleTranscriber {
    private final class Session {
        var recognizer: SFSpeechRecognizer?
        var task: SFSpeechRecognitionTask?
        var finished = false
    }

    static func transcribe(_ url: URL, language: String, vocabulary: [String]) async throws -> String {
        let status = await withCheckedContinuation { c in
            SFSpeechRecognizer.requestAuthorization { c.resume(returning: $0) }
        }
        guard status == .authorized else { throw YapingError.permission("Speech Recognition") }

        let localeID: String
        switch language {
        case "id": localeID = "id-ID"
        case "en": localeID = "en-US"
        default: localeID = Locale.current.identifier
        }
        guard let recognizer = SFSpeechRecognizer(locale: Locale(identifier: localeID)), recognizer.isAvailable else {
            throw YapingError.unavailable("Pengenal suara Apple tidak tersedia untuk \(localeID)")
        }

        let request = SFSpeechURLRecognitionRequest(url: url)
        request.shouldReportPartialResults = false
        request.addsPunctuation = true
        request.contextualStrings = vocabulary
        if recognizer.supportsOnDeviceRecognition { request.requiresOnDeviceRecognition = true }

        let session = Session()
        session.recognizer = recognizer
        return try await withCheckedThrowingContinuation { c in
            session.task = recognizer.recognitionTask(with: request) { result, error in
                guard !session.finished else { return }
                if let error {
                    session.finished = true
                    session.task = nil
                    c.resume(throwing: error)
                } else if let result, result.isFinal {
                    session.finished = true
                    session.task = nil
                    c.resume(returning: result.bestTranscription.formattedString)
                }
            }
        }
    }
}

struct Multipart {
    private let boundary = "Yaping-\(UUID().uuidString)"
    private var body = Data()

    var contentType: String { "multipart/form-data; boundary=\(boundary)" }

    mutating func field(_ name: String, _ value: String) {
        body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"\r\n\r\n\(value)\r\n".utf8))
    }

    mutating func file(_ name: String, filename: String, type: String, data: Data) {
        body.append(Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"\(name)\"; filename=\"\(filename)\"\r\nContent-Type: \(type)\r\n\r\n".utf8))
        body.append(data)
        body.append(Data("\r\n".utf8))
    }

    func finish() -> Data {
        body + Data("--\(boundary)--\r\n".utf8)
    }
}
