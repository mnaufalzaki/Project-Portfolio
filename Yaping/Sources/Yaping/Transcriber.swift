import Foundation

enum YapingError: LocalizedError {
    case missingKey(String)
    /// The key exists but macOS won't hand it to Yaping yet.
    case keyLocked(String)
    case http(Int, String)
    case badResponse
    case permission(String)
    case unavailable(String)
    /// Every configured Gemini API key failed; one short reason per key.
    case allFailed([String])

    var errorDescription: String? {
        switch self {
        case .missingKey(let who): return "API key \(who) belum diisi — buka Pengaturan › Mesin AI"
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
    static func send(_ req: URLRequest, body: Data) async throws -> [String: Any] {
        let (data, resp) = try await URLSession.shared.upload(for: req, from: body)
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
        /// Which Gemini API key slot (1, 2, or 3) handled the transcription.
        let slot: Int
        /// Earlier key slots that were skipped or failed before `slot` succeeded.
        let skipped: [String]
        var quotaWarning: String?
    }

    /// Tries configured Gemini API keys in order (Key 1 -> Key 2 -> Key 3),
    /// automatically failing over when a key hits its rate limit or fails.
    static func transcribe(_ url: URL, settings s: AppSettings) async throws -> Transcript {
        let configured = s.configuredGeminiSlots
        guard !configured.isEmpty else {
            throw YapingError.missingKey("Gemini")
        }

        let model = s.effectiveGeminiModel
        let payload = try AudioCompressor.compressForCloud(url)
        var skipped: [String] = []

        for slot in configured {
            if let until = Quota.shared.blockedUntil(slot: slot) {
                skipped.append("Key \(slot): kuota habis s/d \(until.formatted(date: .omitted, time: .shortened))")
                continue
            }
            let account = GeminiKeySlot.account(for: slot)
            do {
                let apiKey = try KeyStore.required(account, name: "Gemini Key \(slot)")
                let rawText = try await GeminiTranscriber.transcribe(payload, apiKey: apiKey, model: model, settings: s)
                let text = tidy(rawText)
                if !skipped.isEmpty {
                    Log.write("transcribed via Gemini Key \(slot) after: \(skipped.joined(separator: "; "))")
                }
                let warning = Quota.shared.recordSuccess(slot: slot, activeSlots: configured)
                return Transcript(text: text, slot: slot, skipped: skipped, quotaWarning: warning)
            } catch is CancellationError {
                throw CancellationError()
            } catch {
                if case YapingError.http(429, let message) = error {
                    Quota.shared.recordLimitHit(slot: slot, message: message)
                }
                Log.write("transcribe via Gemini Key \(slot) failed: \(error.localizedDescription)")
                skipped.append("Key \(slot): \(shortReason(error))")
            }
        }
        throw YapingError.allFailed(skipped)
    }

    private static func shortReason(_ error: Error) -> String {
        switch error {
        case YapingError.http(429, _): return "kuota habis"
        case YapingError.http(401, _), YapingError.http(403, _): return "API key ditolak"
        case YapingError.http(let code, _): return "error \(code)"
        case YapingError.missingKey: return "belum diisi"
        case YapingError.keyLocked: return "akses key belum diizinkan"
        case is URLError: return "internet bermasalah"
        default: return String(error.localizedDescription.prefix(80))
        }
    }

    /// Joins multi-line transcript segments into flowing text with clean spacing and capitalization.
    static func tidy(_ text: String) -> String {
        let segments = text.components(separatedBy: .newlines)
            .map { $0.split(whereSeparator: \.isWhitespace).joined(separator: " ") }
            .filter { !$0.isEmpty }
        var out = ""
        for segment in segments {
            guard let last = out.last, let first = segment.first else { out = segment; continue }
            let closesSentence = ".?!…,;:".contains(last)
            out += (!closesSentence && first.isUppercase ? ". " : " ") + segment
        }
        guard let first = out.first else { return out }
        return first.uppercased() + out.dropFirst()
    }

    /// Normalizes typographic hyphens/spaces (e.g. non-breaking hyphen U+2011) that look odd in chat apps.
    static func normalize(_ text: String) -> String {
        var t = text
        for (from, to) in [("\u{2011}", "-"), ("\u{2010}", "-"), ("\u{00A0}", " "), ("\u{202F}", " "), ("\u{200B}", "")] {
            t = t.replacingOccurrences(of: from, with: to)
        }
        return t.trimmingCharacters(in: .whitespacesAndNewlines)
    }
}
