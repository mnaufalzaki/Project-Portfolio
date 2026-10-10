import Foundation

/// Runs whisper.cpp's server in the background so the model stays loaded between dictations.
final class LocalWhisper {
    static let shared = LocalWhisper()

    static let port = 8178
    static let modelsDir = FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
        .appendingPathComponent("Yaping/models")

    static var binaryPath: String? {
        ["/opt/homebrew/bin/whisper-server", "/usr/local/bin/whisper-server"]
            .first { FileManager.default.isExecutableFile(atPath: $0) }
    }

    /// Prefers large-v3-turbo; any other ggml-*.bin dropped in the folder also works.
    static var modelPath: String? {
        let files = (try? FileManager.default.contentsOfDirectory(atPath: modelsDir.path)) ?? []
        let models = files.filter { $0.hasPrefix("ggml-") && $0.hasSuffix(".bin") }.sorted()
        guard let pick = models.first(where: { $0.contains("turbo") }) ?? models.first else { return nil }
        return modelsDir.appendingPathComponent(pick).path
    }

    static var isInstalled: Bool { binaryPath != nil && modelPath != nil }

    private var process: Process?
    private let lock = NSLock()

    func start() {
        lock.lock()
        defer { lock.unlock() }
        guard process?.isRunning != true,
              let binary = Self.binaryPath, let model = Self.modelPath else { return }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: binary)
        p.arguments = [
            "-m", model,
            "--host", "127.0.0.1",
            "--port", String(Self.port),
            "-l", "auto",
            "-t", String(max(4, ProcessInfo.processInfo.activeProcessorCount - 2)),
        ]
        p.standardOutput = FileHandle.nullDevice
        p.standardError = FileHandle.nullDevice
        do {
            try p.run()
            process = p
        } catch {
            NSLog("Yaping: failed to start whisper-server: \(error)")
        }
    }

    /// Reuses a server that's already listening (e.g. left over from a crashed run).
    func startIfNeeded() {
        Task {
            if await !isUp() { start() }
        }
    }

    func stop() {
        lock.lock()
        defer { lock.unlock() }
        process?.terminate()
        process = nil
    }

    func transcribe(_ url: URL, language: String, prompt: String) async throws -> String {
        guard Self.isInstalled else {
            throw YapingError.unavailable("whisper.cpp belum terpasang — lihat Pengaturan › Mesin AI")
        }
        try await ensureReady()

        var form = Multipart()
        form.field("response_format", "json")
        form.field("temperature", "0")
        form.field("language", language)
        if !prompt.isEmpty { form.field("prompt", prompt) }
        form.file("file", filename: "audio.wav", type: "audio/wav", data: try Data(contentsOf: url))

        var req = URLRequest(url: URL(string: "http://127.0.0.1:\(Self.port)/inference")!, timeoutInterval: 120)
        req.httpMethod = "POST"
        req.setValue(form.contentType, forHTTPHeaderField: "Content-Type")
        let json = try await HTTP.send(req, body: form.finish())
        guard let text = json["text"] as? String else { throw YapingError.badResponse }
        return text
    }

    /// Starts the server if needed and waits for the model to finish loading.
    private func ensureReady() async throws {
        if await isUp() { return }
        start()
        for _ in 0..<120 {
            try await Task.sleep(nanoseconds: 250_000_000)
            if await isUp() { return }
        }
        throw YapingError.unavailable("Server whisper.cpp tidak merespons")
    }

    private func isUp() async -> Bool {
        var req = URLRequest(url: URL(string: "http://127.0.0.1:\(Self.port)/")!, timeoutInterval: 1)
        req.httpMethod = "GET"
        return (try? await URLSession.shared.data(for: req)) != nil
    }
}

/// Talks to a local Ollama install (http://localhost:11434).
enum Ollama {
    static let base = URL(string: "http://127.0.0.1:11434")!
    private static let keepAlive = "30m"

    static func installedModels() async -> [String] {
        guard let (data, _) = try? await URLSession.shared.data(from: base.appendingPathComponent("api/tags")),
              let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let models = json["models"] as? [[String: Any]] else { return [] }
        return models.compactMap { $0["name"] as? String }
    }

    /// The chosen model, or the first installed one when none was picked yet.
    static func resolveModel(_ preferred: String) async throws -> String {
        if !preferred.isEmpty { return preferred }
        guard let first = await installedModels().first else {
            throw YapingError.unavailable("Ollama tidak jalan atau belum ada model — jalankan: ollama pull gemma3:4b")
        }
        return first
    }

    /// Loads the model into memory ahead of time so the first dictation isn't slow.
    static func warmUp(_ preferred: String) {
        Task.detached {
            guard let model = try? await resolveModel(preferred) else { return }
            var req = URLRequest(url: base.appendingPathComponent("api/generate"), timeoutInterval: 120)
            req.httpMethod = "POST"
            let body: [String: Any] = ["model": model, "keep_alive": keepAlive]
            _ = try? await HTTP.send(req, body: try JSONSerialization.data(withJSONObject: body))
        }
    }

    static func chat(system: String, user: String, model preferred: String) async throws -> String {
        let model = try await resolveModel(preferred)
        do {
            return try await chat(system: system, user: user, model: model, disableThinking: true)
        } catch YapingError.http(_, let message) where message.contains("think") {
            // Older non-reasoning models reject the `think` flag.
            return try await chat(system: system, user: user, model: model, disableThinking: false)
        }
    }

    private static func chat(system: String, user: String, model: String, disableThinking: Bool) async throws -> String {
        var req = URLRequest(url: base.appendingPathComponent("api/chat"), timeoutInterval: 90)
        req.httpMethod = "POST"
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        var body: [String: Any] = [
            "model": model,
            "stream": false,
            "keep_alive": keepAlive,
            "options": ["temperature": 0.2],
            "messages": [
                ["role": "system", "content": system],
                ["role": "user", "content": user],
            ],
        ]
        if disableThinking { body["think"] = false }
        let json = try await HTTP.send(req, body: try JSONSerialization.data(withJSONObject: body))
        guard let message = json["message"] as? [String: Any],
              let content = message["content"] as? String else { throw YapingError.badResponse }
        return content
    }
}
