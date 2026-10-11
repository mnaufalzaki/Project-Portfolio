import Foundation
import Security

/// API keys live in the login Keychain, cached in memory once read.
///
/// Builds are ad-hoc signed, so macOS treats every update as a different app. An item created with the
/// default access rules can't be replaced by the next build (`errSecInvalidOwnerEdit`), which made keys
/// look "lost" after updates and restarts. Keys are therefore stored with an access list that lets any
/// build of Yaping read and replace them without a prompt (still encrypted in the login Keychain).
/// They live under a new service name because items saved by older builds can't be modified anymore.
enum KeyStore {
    enum Status {
        case missing
        case saved
        /// Stored, but macOS refused to hand it to Yaping (permission prompt denied or not answered).
        case locked
    }

    private static let service = "com.naufalzaki.yaping.keys"
    private static let lock = NSLock()
    private static var cache: [String: String] = [:]
    /// Accounts whose last read was refused, and when — so we don't re-prompt on every dictation.
    private static var refusedAt: [String: Date] = [:]
    private static let retryAfterRefusal: TimeInterval = 60

    static func get(_ account: String) -> String {
        lock.lock()
        if let cached = cache[account] { lock.unlock(); return cached }
        if let refused = refusedAt[account], Date().timeIntervalSince(refused) < retryAfterRefusal {
            lock.unlock()
            return ""
        }
        lock.unlock()

        // Outside the lock: this call may show a macOS permission dialog and block until it's answered.
        var out: AnyObject?
        let status = SecItemCopyMatching(query(account, returnData: true) as CFDictionary, &out)

        lock.lock()
        defer { lock.unlock() }
        switch status {
        case errSecSuccess:
            let value = (out as? Data).flatMap { String(data: $0, encoding: .utf8) } ?? ""
            cache[account] = value
            refusedAt[account] = nil
            return value
        case errSecItemNotFound:
            cache[account] = ""
            refusedAt[account] = nil
            return ""
        default:
            refusedAt[account] = Date()
            Log.write("keychain: reading \(account) refused (status \(status))")
            return ""
        }
    }

    /// The key, or a clear error saying whether it's missing or just not readable yet.
    static func required(_ account: String, name: String) throws -> String {
        let key = get(account)
        if !key.isEmpty { return key }
        if status(account) == .locked { throw YapingError.keyLocked(name) }
        throw YapingError.missingKey(name)
    }

    /// Whether a key exists, without reading the secret itself (so it never triggers a permission dialog).
    static func status(_ account: String) -> Status {
        lock.lock()
        let cached = cache[account]
        let refused = refusedAt[account] != nil
        lock.unlock()
        if let cached, !cached.isEmpty { return .saved }

        var out: AnyObject?
        let found = SecItemCopyMatching(query(account, returnData: false) as CFDictionary, &out) == errSecSuccess
        guard found else { return .missing }
        return refused ? .locked : .saved
    }

    /// Forgets a refusal and asks macOS again (the "Izinkan" button).
    @discardableResult
    static func retry(_ account: String) -> Bool {
        lock.lock()
        cache[account] = nil
        refusedAt[account] = nil
        lock.unlock()
        return !get(account).isEmpty
    }

    /// Saves (or, with an empty value, removes) a key. Returns false if the Keychain refused.
    @discardableResult
    static func set(_ value: String, for account: String) -> Bool {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        let base: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        var status: OSStatus
        if trimmed.isEmpty {
            status = SecItemDelete(base as CFDictionary)
            if status == errSecItemNotFound { status = errSecSuccess }
        } else {
            let data = Data(trimmed.utf8)
            status = SecItemUpdate(base as CFDictionary, [kSecValueData as String: data] as CFDictionary)
            if status == errSecItemNotFound {
                var add = base
                add[kSecValueData as String] = data
                add[kSecAttrLabel as String] = "Yaping API key (\(account))"
                if let access = sharedAccess() { add[kSecAttrAccess as String] = access }
                status = SecItemAdd(add as CFDictionary, nil)
            }
        }
        guard status == errSecSuccess else {
            Log.write("keychain: saving \(account) failed (status \(status))")
            return false
        }
        lock.lock()
        cache[account] = trimmed
        refusedAt[account] = nil
        lock.unlock()
        return true
    }

    /// Access rules with no application list: every build of Yaping may read, update and delete the
    /// item without a prompt. (The Keychain APIs for this are deprecated but remain the only way to set
    /// an item's access list on a non-sandboxed, ad-hoc-signed app.)
    private static func sharedAccess() -> SecAccess? {
        var access: SecAccess?
        guard SecAccessCreate("Yaping API key" as CFString, nil, &access) == errSecSuccess,
              let access else { return nil }
        var list: CFArray?
        guard SecAccessCopyACLList(access, &list) == errSecSuccess else { return nil }
        for acl in (list as? [SecACL]) ?? [] {
            var apps: CFArray?
            var description: CFString?
            var prompt = SecKeychainPromptSelector()
            SecACLCopyContents(acl, &apps, &description, &prompt)
            SecACLSetContents(acl, nil, description ?? ("Yaping" as CFString), [])
        }
        return access
    }

    private static func query(_ account: String, returnData: Bool) -> [String: Any] {
        var q: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        if returnData {
            q[kSecReturnData as String] = true
        } else {
            q[kSecReturnAttributes as String] = true
        }
        return q
    }
}
