import Foundation

/// Google's Gemini 3.5 Transcribe via the Interactions API — one request, audio sent inline.
enum GeminiTranscriber {
    static let endpoint = URL(string: "https://generativelanguage.googleapis.com/v1beta/interactions")!

    static func transcribe(_ url: URL, model: String, settings s: AppSettings) async throws -> String {
        let key = KeyStore.get(TranscriptionProvider.gemini.rawValue)
        guard !key.isEmpty else { throw YapingError.missingKey("Gemini") }

        var config: [String: Any] = [
            "language_codes": languageCodes(s.language),
        ]
        // Smart: drops fillers and follows self-corrections without rewording. Verbatim is the API default.
        if s.geminiSmart { config["mode"] = "smart" }
        let terms = s.vocabularyTerms
        if !terms.isEmpty { config["custom_vocabulary"] = Array(terms.prefix(1000)) }

        let body: [String: Any] = [
            "model": model,
            "input": [[
                "type": "audio",
                "mime_type": "audio/wav",
                "data": try Data(contentsOf: url).base64EncodedString(),
            ]],
            "generation_config": ["transcription_config": config],
            "store": false,
        ]

        var req = URLRequest(url: endpoint, timeoutInterval: 60)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue(key, forHTTPHeaderField: "x-goog-api-key")
        let json = try await HTTP.send(req, body: try JSONSerialization.data(withJSONObject: body))
        guard let text = outputText(json) else { throw YapingError.badResponse }
        return text
    }

    /// "Otomatis" means auto-detect, which the API spells as an empty list.
    private static func languageCodes(_ language: String) -> [String] {
        switch language {
        case "id": return ["id-ID"]
        case "en": return ["en-US"]
        default: return []
        }
    }

    /// The transcript lives in the `model_output` step; `output_text` is accepted too in case the shape shifts.
    private static func outputText(_ json: [String: Any]) -> String? {
        if let steps = json["steps"] as? [[String: Any]] {
            let text = steps
                .filter { ($0["type"] as? String) == "model_output" }
                .flatMap { ($0["content"] as? [[String: Any]]) ?? [] }
                .compactMap { $0["text"] as? String }
                .joined()
            if !text.isEmpty { return text }
        }
        return json["output_text"] as? String
    }
}
