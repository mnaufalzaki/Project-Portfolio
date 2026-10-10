import Foundation

/// Asks Groq which chat models this account can actually use, so a retired
/// or restricted model never breaks polishing.
enum Groq {
    static let baseURL = TranscriptionProvider.groq.defaultBaseURL

    /// Best first: strong multilingual rewriting, then faster fallbacks.
    static let preferred = [
        "llama-3.3-70b-versatile",
        "openai/gpt-oss-120b",
        "moonshotai/kimi-k2-instruct",
        "qwen/qwen3-32b",
        "openai/gpt-oss-20b",
        "llama-3.1-8b-instant",
    ]

    private static var pendingRefresh: DispatchWorkItem?

    static func fetchChatModels(key: String) async throws -> [String] {
        var req = URLRequest(url: URL(string: "\(baseURL)/models")!, timeoutInterval: 15)
        req.setValue("Bearer \(key)", forHTTPHeaderField: "Authorization")
        let (data, resp) = try await URLSession.shared.data(for: req)
        let code = (resp as? HTTPURLResponse)?.statusCode ?? 0
        guard (200..<300).contains(code) else {
            let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
            let message = (json?["error"] as? [String: Any])?["message"] as? String ?? "?"
            throw YapingError.http(code, message)
        }
        let json = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        let items = json?["data"] as? [[String: Any]] ?? []
        let skip = ["whisper", "guard", "orpheus", "tts", "playai", "distil"]
        return items
            .filter { ($0["active"] as? Bool) ?? true }
            .compactMap { $0["id"] as? String }
            .filter { id in !skip.contains { id.lowercased().contains($0) } }
            .sorted()
    }

    static func best(of models: [String], excluding bad: String? = nil) -> String? {
        let usable = models.filter { $0 != bad }
        return preferred.first(where: usable.contains) ?? usable.first
    }

    /// Stores the account's model list and moves off a model it can't use.
    @MainActor
    static func apply(_ models: [String]) {
        let s = AppSettings.shared
        if s.groqModels != models { s.groqModels = models }
        if !models.contains(s.groqChatModel), let pick = best(of: models) {
            s.groqChatModel = pick
        }
    }

    /// Opens the HTTPS connection while the user is still talking, so polishing skips the handshake.
    /// Unauthenticated on purpose: the 401 doesn't matter, the warm connection does.
    static func preconnect() async {
        var req = URLRequest(url: URL(string: "\(baseURL)/models")!, timeoutInterval: 5)
        req.httpMethod = "HEAD"
        _ = try? await URLSession.shared.data(for: req)
    }

    static func refreshModels() {
        Task {
            let key = KeyStore.get("groq")
            guard !key.isEmpty,
                  let models = try? await fetchChatModels(key: key), !models.isEmpty else { return }
            await MainActor.run { apply(models) }
        }
    }

    /// Debounced refresh for while the user is pasting a key.
    static func scheduleRefresh() {
        pendingRefresh?.cancel()
        let work = DispatchWorkItem { refreshModels() }
        pendingRefresh = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 1, execute: work)
    }

    static func label(for id: String) -> String {
        switch id {
        case "llama-3.3-70b-versatile": return "Llama 3.3 70B — rekomendasi"
        case "openai/gpt-oss-120b": return "GPT-OSS 120B — pintar, sedikit lebih lambat"
        case "openai/gpt-oss-20b": return "GPT-OSS 20B — cepat"
        case "llama-3.1-8b-instant": return "Llama 3.1 8B — paling cepat"
        case "moonshotai/kimi-k2-instruct": return "Kimi K2"
        default: return id
        }
    }
}
