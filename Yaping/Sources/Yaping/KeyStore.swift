import Foundation
import Security

/// API keys live in the login Keychain, cached in memory so we hit it once per launch.
enum KeyStore {
    private static let service = "com.naufalzaki.yaping"
    private static var cache: [String: String] = [:]

    static func get(_ account: String) -> String {
        if let cached = cache[account] { return cached }
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var out: AnyObject?
        var value = ""
        if SecItemCopyMatching(query as CFDictionary, &out) == errSecSuccess,
           let data = out as? Data {
            value = String(data: data, encoding: .utf8) ?? ""
        }
        cache[account] = value
        return value
    }

    static func set(_ value: String, for account: String) {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        guard cache[account] != trimmed else { return }
        cache[account] = trimmed
        let base: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: service,
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(base as CFDictionary)
        guard !trimmed.isEmpty else { return }
        var add = base
        add[kSecValueData as String] = Data(trimmed.utf8)
        SecItemAdd(add as CFDictionary, nil)
    }
}
