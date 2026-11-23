import Foundation

/// Stores API keys locally in `~/Library/Application Support/Yaping/keys.json` with `0600`
/// (owner read/write only) permissions.
///
/// Using an owner-only local file avoids repeated macOS login Keychain password prompts on
/// ad-hoc-signed builds and when switching between multiple API key slots.
enum KeyStore {
    enum Status {
        case missing
        case saved
        case locked
    }

    private static let lock = NSLock()
    private static var cache: [String: String]?

    private static let folderURL: URL = {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Yaping", isDirectory: true)
    }()

    private static let fileURL: URL = {
        folderURL.appendingPathComponent("keys.json")
    }()

    static func get(_ account: String) -> String {
        lock.lock()
        defer { lock.unlock() }
        return loadLocked()[account] ?? ""
    }

    static func required(_ account: String, name: String) throws -> String {
        let key = get(account)
        if !key.isEmpty { return key }
        throw YapingError.missingKey(name)
    }

    static func status(_ account: String) -> Status {
        get(account).isEmpty ? .missing : .saved
    }

    @discardableResult
    static func retry(_ account: String) -> Bool {
        !get(account).isEmpty
    }

    /// Saves (or, with an empty value, removes) a key atomically with `0600` permissions.
    @discardableResult
    static func set(_ value: String, for account: String) -> Bool {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        lock.lock()
        defer { lock.unlock() }

        var dict = loadLocked()
        if trimmed.isEmpty {
            dict.removeValue(forKey: account)
        } else {
            dict[account] = trimmed
        }

        do {
            try saveLocked(dict)
            cache = dict
            return true
        } catch {
            Log.write("keystore: saving \(account) failed: \(error.localizedDescription)")
            return false
        }
    }

    // MARK: Persistence (caller holds `lock`)

    private static func loadLocked() -> [String: String] {
        if let cache { return cache }
        guard let data = try? Data(contentsOf: fileURL),
              let decoded = try? JSONDecoder().decode([String: String].self, from: data) else {
            cache = [:]
            return [:]
        }
        cache = decoded
        return decoded
    }

    private static func saveLocked(_ dict: [String: String]) throws {
        let fm = FileManager.default
        if !fm.fileExists(atPath: folderURL.path) {
            try fm.createDirectory(
                at: folderURL,
                withIntermediateDirectories: true,
                attributes: [.posixPermissions: 0o700]
            )
        }
        let data = try JSONEncoder().encode(dict)
        try data.write(to: fileURL, options: .atomic)
        try fm.setAttributes([.posixPermissions: 0o600], ofItemAtPath: fileURL.path)
    }
}
