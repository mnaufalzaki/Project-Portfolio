import AppKit
import Combine

enum HotkeyChoice: String, CaseIterable, Identifiable {
    case commandOption, fn, rightOption, rightCommand, rightControl

    var id: String { rawValue }

    var label: String {
        switch self {
        case .commandOption: return "Command + Option (⌘⌥)"
        case .fn: return "Fn / 🌐"
        case .rightOption: return "Option kanan (⌥)"
        case .rightCommand: return "Command kanan (⌘)"
        case .rightControl: return "Control kanan (⌃)"
        }
    }

    /// Short form for the overlay and menu.
    var symbol: String {
        switch self {
        case .commandOption: return "⌘⌥"
        case .fn: return "Fn"
        case .rightOption: return "⌥ kanan"
        case .rightCommand: return "⌘ kanan"
        case .rightControl: return "⌃ kanan"
        }
    }

    private static let modifierKeyCodes: Set<UInt16> = [54, 55, 56, 58, 59, 60, 61, 62]

    /// Whether a flagsChanged event for this key code can affect the hotkey.
    func concerns(keyCode: UInt16) -> Bool {
        switch self {
        case .commandOption: return Self.modifierKeyCodes.contains(keyCode)
        case .fn: return keyCode == 63
        case .rightOption: return keyCode == 61
        case .rightCommand: return keyCode == 54
        case .rightControl: return keyCode == 62
        }
    }

    /// Uses device-dependent masks so the left-hand modifier doesn't count.
    func isPressed(_ flags: NSEvent.ModifierFlags) -> Bool {
        switch self {
        case .commandOption: return flags.intersection(Self.chordMask) == [.command, .option]
        case .fn: return flags.contains(.function)
        case .rightOption: return flags.rawValue & 0x40 != 0
        case .rightCommand: return flags.rawValue & 0x10 != 0
        case .rightControl: return flags.rawValue & 0x2000 != 0
        }
    }

    /// ⌘⌥ plus Shift/Control means the user is reaching for a shortcut, not dictating.
    func hasExtraModifiers(_ flags: NSEvent.ModifierFlags) -> Bool {
        guard self == .commandOption else { return false }
        let held = flags.intersection(Self.chordMask)
        return held.isSuperset(of: [.command, .option]) && held != [.command, .option]
    }

    private static let chordMask: NSEvent.ModifierFlags = [.command, .option, .control, .shift]
}

enum HotkeyMode: String, CaseIterable, Identifiable {
    case toggle, holdOrTap
    var id: String { rawValue }

    var label: String {
        switch self {
        case .toggle: return "Tekan sekali mulai, tekan lagi selesai"
        case .holdOrTap: return "Tahan untuk bicara (ketuk = bebas tangan)"
        }
    }
}

enum TranscriptionProvider: String, CaseIterable, Identifiable {
    case local, groq, gemini, openai, custom, apple

    var id: String { rawValue }

    var label: String {
        switch self {
        case .local: return "Lokal — whisper.cpp (gratis, offline)"
        case .groq: return "Groq — gratis, perlu API key (cloud)"
        case .gemini: return "Google Gemini 3.5 Transcribe — gratis, paling canggih (cloud)"
        case .openai: return "OpenAI"
        case .custom: return "Custom (OpenAI-compatible)"
        case .apple: return "Apple — offline, tanpa API key"
        }
    }

    var defaultBaseURL: String {
        switch self {
        case .local: return ""
        case .groq: return "https://api.groq.com/openai/v1"
        case .gemini: return "https://generativelanguage.googleapis.com/v1beta"
        case .openai: return "https://api.openai.com/v1"
        case .custom: return "http://localhost:8000/v1"
        case .apple: return ""
        }
    }

    var defaultModel: String {
        switch self {
        case .local: return ""
        case .groq: return "whisper-large-v3"
        case .gemini: return "gemini-3.5-transcribe"
        case .openai: return "gpt-4o-transcribe"
        case .custom: return "whisper-1"
        case .apple: return ""
        }
    }

    var defaultChatModel: String {
        switch self {
        case .groq: return "llama-3.3-70b-versatile"
        case .openai: return "gpt-4o-mini"
        case .local, .gemini, .custom, .apple: return ""
        }
    }

    /// Short name for status messages ("Gemini: kuota habis → Groq").
    var shortName: String {
        switch self {
        case .local: return "Whisper lokal"
        case .groq: return "Groq"
        case .gemini: return "Gemini"
        case .openai: return "OpenAI"
        case .custom: return "Custom"
        case .apple: return "Apple"
        }
    }

    /// Speaks the OpenAI `/audio/transcriptions` + `/chat/completions` dialect.
    var isOpenAICompatible: Bool { self == .groq || self == .openai || self == .custom }

    var keyURL: URL? {
        switch self {
        case .groq: return URL(string: "https://console.groq.com/keys")
        case .openai: return URL(string: "https://platform.openai.com/api-keys")
        case .gemini: return URL(string: "https://aistudio.google.com/apikey")
        case .local, .custom, .apple: return nil
        }
    }
}

enum CleanupProvider: String, CaseIterable, Identifiable {
    case groq, ollama, claude, sameAsTranscription
    var id: String { rawValue }
}

enum CleanupStyle: String, CaseIterable, Identifiable {
    case polish, minimal
    var id: String { rawValue }

    var label: String {
        switch self {
        case .polish: return "Parafrase + cek grammar"
        case .minimal: return "Minimal — hanya buang filler & tanda baca"
        }
    }
}

final class AppSettings: ObservableObject {
    static let shared = AppSettings()
    private let d = UserDefaults.standard

    @Published var hotkey: HotkeyChoice { didSet { d.set(hotkey.rawValue, forKey: "hotkey") } }
    @Published var hotkeyMode: HotkeyMode { didSet { d.set(hotkeyMode.rawValue, forKey: "hotkeyMode") } }
    /// Primary transcription engine.
    @Published var provider: TranscriptionProvider {
        didSet {
            d.set(provider.rawValue, forKey: "provider")
            guard oldValue != provider else { return }
            chatModel = provider.defaultChatModel
            // Picking the backup as primary swaps the two, so the chain never names one engine twice.
            if backupProvider == provider { backupProvider = oldValue }
        }
    }
    /// Tried when the primary fails (quota, network, missing key…). nil = no backup.
    @Published var backupProvider: TranscriptionProvider? {
        didSet { d.set(backupProvider?.rawValue ?? "", forKey: "backupProvider") }
    }
    /// Last resort when every online engine failed: whisper.cpp on this Mac.
    @Published var offlineFallback: Bool { didSet { d.set(offlineFallback, forKey: "offlineFallback") } }
    @Published var customBaseURL: String { didSet { d.set(customBaseURL, forKey: "customBaseURL") } }
    /// Model name per engine, so switching engines never clobbers another engine's choice.
    @Published private var models: [String: String] { didSet { d.set(models, forKey: "transcriptionModels") } }
    @Published var language: String { didSet { d.set(language, forKey: "language") } }
    @Published var geminiSmart: Bool { didSet { d.set(geminiSmart, forKey: "geminiSmart") } }
    @Published var cleanupEnabled: Bool { didSet { d.set(cleanupEnabled, forKey: "cleanupEnabled") } }
    @Published var cleanupProvider: CleanupProvider { didSet { d.set(cleanupProvider.rawValue, forKey: "cleanupProvider") } }
    @Published var cleanupStyle: CleanupStyle { didSet { d.set(cleanupStyle.rawValue, forKey: "cleanupStyle") } }
    @Published var ollamaModel: String { didSet { d.set(ollamaModel, forKey: "ollamaModel") } }
    @Published var groqChatModel: String { didSet { d.set(groqChatModel, forKey: "groqChatModel") } }
    /// Chat models the user's Groq account can use, as reported by the API.
    @Published var groqModels: [String] { didSet { d.set(groqModels, forKey: "groqModels") } }
    @Published var claudeModel: String { didSet { d.set(claudeModel, forKey: "claudeModel") } }
    @Published var chatModel: String { didSet { d.set(chatModel, forKey: "chatModel") } }
    @Published var vocabulary: String { didSet { d.set(vocabulary, forKey: "vocabulary") } }
    @Published var playSounds: Bool { didSet { d.set(playSounds, forKey: "playSounds") } }
    @Published var restoreClipboard: Bool { didSet { d.set(restoreClipboard, forKey: "restoreClipboard") } }
    /// Long recordings paste each ~1-minute piece as soon as it's transcribed.
    @Published var progressiveInsert: Bool { didSet { d.set(progressiveInsert, forKey: "progressiveInsert") } }

    private init() {
        d.register(defaults: [
            "cleanupEnabled": true,
            "playSounds": true,
            "restoreClipboard": true,
            "geminiSmart": true,
            "progressiveInsert": true,
            "offlineFallback": true,
        ])
        let provider = TranscriptionProvider(rawValue: d.string(forKey: "provider") ?? "") ?? .local
        self.provider = provider
        hotkey = HotkeyChoice(rawValue: d.string(forKey: "hotkey") ?? "") ?? .commandOption
        hotkeyMode = HotkeyMode(rawValue: d.string(forKey: "hotkeyMode") ?? "") ?? .toggle
        if let saved = d.string(forKey: "backupProvider") {
            backupProvider = TranscriptionProvider(rawValue: saved)
        } else {
            backupProvider = provider == .groq ? .local : .groq
        }
        offlineFallback = d.bool(forKey: "offlineFallback")
        customBaseURL = d.string(forKey: "customBaseURL") ?? TranscriptionProvider.custom.defaultBaseURL
        var models = d.dictionary(forKey: "transcriptionModels") as? [String: String] ?? [:]
        // Carry over the single model setting from earlier versions.
        if models[provider.rawValue] == nil, let old = d.string(forKey: "transcriptionModel"), !old.isEmpty {
            models[provider.rawValue] = old
        }
        self.models = models
        language = d.string(forKey: "language") ?? "auto"
        geminiSmart = d.bool(forKey: "geminiSmart")
        cleanupEnabled = d.bool(forKey: "cleanupEnabled")
        cleanupProvider = CleanupProvider(rawValue: d.string(forKey: "cleanupProvider") ?? "") ?? .groq
        cleanupStyle = CleanupStyle(rawValue: d.string(forKey: "cleanupStyle") ?? "") ?? .polish
        ollamaModel = d.string(forKey: "ollamaModel") ?? ""
        groqChatModel = d.string(forKey: "groqChatModel") ?? "llama-3.3-70b-versatile"
        groqModels = d.stringArray(forKey: "groqModels") ?? []
        claudeModel = d.string(forKey: "claudeModel") ?? "claude-opus-5-5"
        chatModel = d.string(forKey: "chatModel") ?? provider.defaultChatModel
        vocabulary = d.string(forKey: "vocabulary") ?? ""
        playSounds = d.bool(forKey: "playSounds")
        restoreClipboard = d.bool(forKey: "restoreClipboard")
        progressiveInsert = d.bool(forKey: "progressiveInsert")
    }

    func model(for engine: TranscriptionProvider) -> String {
        let saved = models[engine.rawValue]?.trimmingCharacters(in: .whitespaces) ?? ""
        return saved.isEmpty ? engine.defaultModel : saved
    }

    func setModel(_ model: String, for engine: TranscriptionProvider) {
        models[engine.rawValue] = model
    }

    func baseURL(for engine: TranscriptionProvider) -> String {
        engine == .custom ? customBaseURL : engine.defaultBaseURL
    }

    func key(for engine: TranscriptionProvider) -> String {
        KeyStore.get(engine.rawValue)
    }

    /// Primary engine's endpoint/key (used by the optional "same as transcription" rewrite).
    var baseURL: String { baseURL(for: provider) }
    var transcriptionKey: String { key(for: provider) }

    /// Engines to try, in order: primary, backup, then local Whisper if enabled. Never repeats one.
    var transcriptionChain: [TranscriptionProvider] {
        var chain = [provider]
        if let backup = backupProvider, !chain.contains(backup) { chain.append(backup) }
        if offlineFallback, !chain.contains(.local), LocalWhisper.isInstalled { chain.append(.local) }
        return chain
    }

    var vocabularyTerms: [String] {
        vocabulary
            .components(separatedBy: CharacterSet(charactersIn: ",\n"))
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
    }

    private var needsCleanupKey: Bool {
        cleanupEnabled && cleanupProvider == .groq && KeyStore.get("groq").isEmpty
    }

    /// True when the app can't transcribe yet and the user should see Settings.
    var needsSetup: Bool {
        switch provider {
        case .local: return !LocalWhisper.isInstalled || needsCleanupKey
        case .groq, .gemini, .openai: return transcriptionKey.isEmpty
        case .custom, .apple: return false
        }
    }
}
