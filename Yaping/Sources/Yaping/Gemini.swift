import Foundation

/// Google's Gemini 3.5 Transcribe via the Interactions API — one request, compressed audio sent inline.
enum GeminiTranscriber {
    static let endpoint = URL(string: "https://generativelanguage.googleapis.com/v1beta/interactions")!

    static func transcribe(_ payload: AudioCompressor.Payload, apiKey: String, model: String, settings s: AppSettings) async throws -> String {
        var config: [String: Any] = [
            "language_codes": languageCodes(s.language),
        ]
        // Smart: drops fillers and follows self-corrections without rewording. Verbatim is the API default.
        if s.geminiSmart { config["mode"] = "smart" }

        let body: [String: Any] = [
            "model": model,
            "input": [[
                "type": "audio",
                "mime_type": payload.mimeType,
                "data": payload.data.base64EncodedString(),
            ]],
            "generation_config": ["transcription_config": config],
            "store": false,
        ]

        var req = URLRequest(url: endpoint, timeoutInterval: 60)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.setValue(apiKey, forHTTPHeaderField: "x-goog-api-key")
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

    /// The transcript lives in the `model_output` step (or `outputs` / `output_text`).
    /// When Gemini receives silence or non-speech audio, it returns a valid 200 response with empty text —
    /// treat that as `""` (silence) rather than `badResponse`.
    private static func outputText(_ json: [String: Any]) -> String? {
        if let steps = json["steps"] as? [[String: Any]] {
            let text = steps
                .filter { ($0["type"] as? String) == "model_output" }
                .flatMap { ($0["content"] as? [[String: Any]]) ?? [] }
                .compactMap { $0["text"] as? String }
                .joined()
            return text
        }
        if let outputs = json["outputs"] as? [[String: Any]] {
            let text = outputs
                .compactMap { $0["text"] as? String }
                .joined()
            return text
        }
        if let direct = json["output_text"] as? String {
            return direct
        }
        // Valid interaction response with no speech output emitted.
        if json["id"] != nil || json["status"] != nil {
            return ""
        }
        return nil
    }
}
