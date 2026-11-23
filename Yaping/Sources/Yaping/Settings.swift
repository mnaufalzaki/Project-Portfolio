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

/// Identifies each of the 3 Gemini API key slots stored in macOS Keychain.
/// Slot 1 keeps the original `"gemini"` account name so existing saved keys continue working seamlessly.
struct GeminiKeySlot: Identifiable {
    let slot: Int
    let account: String
    let title: String
    var id: Int { slot }

    static let all: [GeminiKeySlot] = [
        GeminiKeySlot(slot: 1, account: "gemini", title: "API Key 1 (Utama)"),
        GeminiKeySlot(slot: 2, account: "gemini-2", title: "API Key 2"),
        GeminiKeySlot(slot: 3, account: "gemini-3", title: "API Key 3"),
    ]

    static func account(for slot: Int) -> String {
        all.first { $0.slot == slot }?.account ?? "gemini"
    }
}

final class AppSettings: ObservableObject {
    static let shared = AppSettings()
    static let defaultGeminiModel = "gemini-3.5-transcribe"
    static let geminiKeyURL = URL(string: "https://aistudio.google.com/apikey")!

    private let d = UserDefaults.standard

    @Published var hotkey: HotkeyChoice { didSet { d.set(hotkey.rawValue, forKey: "hotkey") } }
    @Published var hotkeyMode: HotkeyMode { didSet { d.set(hotkeyMode.rawValue, forKey: "hotkeyMode") } }
    @Published var geminiModel: String { didSet { d.set(geminiModel, forKey: "geminiModel") } }
    @Published var geminiSmart: Bool { didSet { d.set(geminiSmart, forKey: "geminiSmart") } }
    @Published var language: String { didSet { d.set(language, forKey: "language") } }
    /// Empty string = Auto (prefers built-in Mac mic when default is Bluetooth/Continuity to avoid 1-2.5s startup lag).
    @Published var microphoneID: String { didSet { d.set(microphoneID, forKey: "microphoneID") } }
    @Published var playSounds: Bool { didSet { d.set(playSounds, forKey: "playSounds") } }
    @Published var restoreClipboard: Bool { didSet { d.set(restoreClipboard, forKey: "restoreClipboard") } }
    /// Long recordings paste each piece as soon as it's transcribed.
    @Published var progressiveInsert: Bool { didSet { d.set(progressiveInsert, forKey: "progressiveInsert") } }

    private init() {
        d.register(defaults: [
            "playSounds": true,
            "restoreClipboard": true,
            "geminiSmart": true,
            "progressiveInsert": true,
        ])
        hotkey = HotkeyChoice(rawValue: d.string(forKey: "hotkey") ?? "") ?? .commandOption
        hotkeyMode = HotkeyMode(rawValue: d.string(forKey: "hotkeyMode") ?? "") ?? .toggle
        // Carry over saved Gemini model from earlier multi-provider versions if present.
        let legacyModel = (d.dictionary(forKey: "transcriptionModels") as? [String: String])?["gemini"]
        let savedModel = d.string(forKey: "geminiModel") ?? legacyModel ?? ""
        geminiModel = savedModel.trimmingCharacters(in: .whitespaces).isEmpty
            ? Self.defaultGeminiModel
            : savedModel
        geminiSmart = d.bool(forKey: "geminiSmart")
        language = d.string(forKey: "language") ?? "auto"
        microphoneID = d.string(forKey: "microphoneID") ?? ""
        playSounds = d.bool(forKey: "playSounds")
        restoreClipboard = d.bool(forKey: "restoreClipboard")
        progressiveInsert = d.bool(forKey: "progressiveInsert")
    }

    var effectiveGeminiModel: String {
        let trimmed = geminiModel.trimmingCharacters(in: .whitespaces)
        return trimmed.isEmpty ? Self.defaultGeminiModel : trimmed
    }

    /// Slots that currently have a saved API key in Keychain (checked without reading secrets).
    var configuredGeminiSlots: [Int] {
        GeminiKeySlot.all.filter { KeyStore.status($0.account) != .missing }.map(\.slot)
    }

    /// True when no Gemini API key has been configured yet.
    var needsSetup: Bool {
        configuredGeminiSlots.isEmpty
    }
}
