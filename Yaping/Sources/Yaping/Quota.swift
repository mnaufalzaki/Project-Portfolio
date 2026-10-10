import Foundation

/// Tracks how much of each free tier is left, for the menu bar, Settings and in-app warnings.
///
/// - Gemini doesn't report remaining quota, so successful requests are counted locally against the
///   daily limit (accurate as long as the key is only used by Yaping). The daily window resets at
///   midnight UTC. A 429 tells us the real limit and the exact wait, which overrides the estimate.
/// - Groq reports its daily request quota in every response's `x-ratelimit-*` headers.
final class Quota: ObservableObject {
    static let shared = Quota()

    private struct Gemini: Codable {
        var day = ""
        var used = 0
        var limit = 25
        var blockedUntil: Date?
    }

    private struct Groq: Codable {
        var limit: Int?
        var remaining: Int?
        var resetsAt: Date?
        var blockedUntil: Date?
    }

    private let lock = NSLock()
    private var gemini: Gemini
    private var groq: Groq
    private let defaults = UserDefaults.standard

    /// Warn when this many (or fewer) requests are left.
    private static let geminiWarnAt: Set<Int> = [5, 1]
    private static let groqWarnAt = 20

    private init() {
        gemini = Self.load(Gemini.self, key: "quota.gemini") ?? Gemini()
        groq = Self.load(Groq.self, key: "quota.groq") ?? Groq()
    }

    // MARK: Recording

    /// Call after a successful Gemini transcription. Returns a warning when the quota is running low.
    func recordGeminiSuccess() -> String? {
        let remaining: Int = locked {
            rollGeminiDay()
            gemini.used += 1
            return max(0, gemini.limit - gemini.used)
        }
        save()
        return Self.geminiWarnAt.contains(remaining)
            ? "Kuota Gemini tinggal ±\(remaining) hari ini — setelah habis otomatis pakai cadangan"
            : nil
    }

    /// Reads Groq's quota headers from any response (successful or not).
    func recordGroq(_ response: HTTPURLResponse) -> String? {
        let limit = response.value(forHTTPHeaderField: "x-ratelimit-limit-requests").flatMap { Int($0) }
        let remaining = response.value(forHTTPHeaderField: "x-ratelimit-remaining-requests").flatMap { Int($0) }
        guard limit != nil || remaining != nil else { return nil }
        let reset = response.value(forHTTPHeaderField: "x-ratelimit-reset-requests").flatMap(Self.parseDuration)
        locked {
            groq.limit = limit ?? groq.limit
            groq.remaining = remaining ?? groq.remaining
            if let reset { groq.resetsAt = Date().addingTimeInterval(reset) }
        }
        save()
        if let remaining, remaining <= Self.groqWarnAt {
            return "Kuota Groq tinggal \(remaining) hari ini"
        }
        return nil
    }

    /// Call on HTTP 429. Learns the real limit/wait from the error message and returns when to try again.
    @discardableResult
    func recordLimitHit(_ engine: TranscriptionProvider, message: String) -> Date {
        let wait = Self.retryDelay(in: message) ?? 10 * 60
        let until = Date().addingTimeInterval(wait)
        locked {
            switch engine {
            case .gemini:
                rollGeminiDay()
                if let limit = Self.firstInt(in: message, pattern: #"limit:\s*(\d+)"#) { gemini.limit = limit }
                gemini.used = max(gemini.used, gemini.limit)
                gemini.blockedUntil = until
            case .groq:
                groq.remaining = 0
                groq.blockedUntil = until
            default:
                break
            }
        }
        save()
        return until
    }

    // MARK: Reading

    /// When an engine may be tried again after hitting its limit, or nil if it's available.
    func blockedUntil(_ engine: TranscriptionProvider) -> Date? {
        locked {
            let until: Date?
            switch engine {
            case .gemini: until = gemini.blockedUntil
            case .groq: until = groq.blockedUntil
            default: until = nil
            }
            guard let until, until > Date() else { return nil }
            return until
        }
    }

    /// One-line summary for the menu bar and Settings, or nil for engines without a quota.
    func summary(for engine: TranscriptionProvider) -> String? {
        switch engine {
        case .gemini:
            if let until = blockedUntil(.gemini) {
                return "Gemini: habis · tersedia lagi \(Self.clock(until))"
            }
            let (used, limit) = locked { () -> (Int, Int) in
                rollGeminiDay()
                return (gemini.used, gemini.limit)
            }
            return "Gemini: ±\(max(0, limit - used)) / \(limit) tersisa · reset \(Self.clock(Self.nextUTCMidnight()))"
        case .groq:
            if let until = blockedUntil(.groq) {
                return "Groq: habis · tersedia lagi \(Self.clock(until))"
            }
            let state = locked { groq }
            guard let remaining = state.remaining, let limit = state.limit else {
                return "Groq: sisa kuota muncul setelah dipakai"
            }
            let reset = state.resetsAt.map { " · reset \(Self.clock($0))" } ?? ""
            return "Groq: \(remaining.formatted()) / \(limit.formatted()) tersisa\(reset)"
        default:
            return nil
        }
    }

    // MARK: Helpers

    private func rollGeminiDay() {
        let today = Self.utcDay(Date())
        if gemini.day != today {
            gemini.day = today
            gemini.used = 0
        }
    }

    private func locked<T>(_ body: () -> T) -> T {
        lock.lock()
        defer { lock.unlock() }
        return body()
    }

    private func save() {
        let (g, q) = locked { (gemini, groq) }
        if let data = try? JSONEncoder().encode(g) { defaults.set(data, forKey: "quota.gemini") }
        if let data = try? JSONEncoder().encode(q) { defaults.set(data, forKey: "quota.groq") }
        DispatchQueue.main.async { self.objectWillChange.send() }
    }

    private static func load<T: Decodable>(_ type: T.Type, key: String) -> T? {
        UserDefaults.standard.data(forKey: key).flatMap { try? JSONDecoder().decode(type, from: $0) }
    }

    private static func utcDay(_ date: Date) -> String {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        let c = calendar.dateComponents([.year, .month, .day], from: date)
        return "\(c.year ?? 0)-\(c.month ?? 0)-\(c.day ?? 0)"
    }

    private static func nextUTCMidnight() -> Date {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(identifier: "UTC")!
        let start = calendar.startOfDay(for: Date())
        return calendar.date(byAdding: .day, value: 1, to: start) ?? Date()
    }

    /// "07.00" today, "besok 07.00" tomorrow, otherwise with the date.
    private static func clock(_ date: Date) -> String {
        let time = date.formatted(date: .omitted, time: .shortened)
        if Calendar.current.isDateInToday(date) { return time }
        if Calendar.current.isDateInTomorrow(date) { return "besok \(time)" }
        return date.formatted(date: .abbreviated, time: .shortened)
    }

    /// Finds "retry in 10h59m30s" / "try again in 7m30.5s" in an error message.
    static func retryDelay(in message: String) -> TimeInterval? {
        guard let range = message.range(of: #"(?:retry|try again) in ([0-9hms.]+)"#,
                                        options: [.regularExpression, .caseInsensitive]) else { return nil }
        let match = message[range].split(separator: " ").last.map(String.init) ?? ""
        return parseDuration(match)
    }

    /// Parses Go-style durations like "10h59m30s", "2m59.56s", "7.66s", "120ms".
    static func parseDuration(_ text: String) -> TimeInterval? {
        guard let regex = try? NSRegularExpression(pattern: #"(\d+(?:\.\d+)?)(ms|h|m|s)"#) else { return nil }
        let ns = text as NSString
        var total: TimeInterval = 0
        var found = false
        for match in regex.matches(in: text, range: NSRange(location: 0, length: ns.length)) {
            guard let value = Double(ns.substring(with: match.range(at: 1))) else { continue }
            found = true
            switch ns.substring(with: match.range(at: 2)) {
            case "h": total += value * 3600
            case "m": total += value * 60
            case "s": total += value
            case "ms": total += value / 1000
            default: break
            }
        }
        return found ? total : nil
    }

    private static func firstInt(in text: String, pattern: String) -> Int? {
        guard let regex = try? NSRegularExpression(pattern: pattern),
              let match = regex.firstMatch(in: text, range: NSRange(text.startIndex..., in: text)),
              let range = Range(match.range(at: 1), in: text) else { return nil }
        return Int(text[range])
    }
}
