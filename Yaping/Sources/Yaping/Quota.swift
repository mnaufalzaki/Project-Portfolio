import Foundation

/// Tracks estimated daily quota and cooldown windows across Gemini API key slots (1, 2, 3).
///
/// Gemini doesn't report remaining quota in response headers, so successful requests are counted
/// locally per key against the daily limit (default 25). The daily window resets at midnight
/// Pacific Time (America/Los_Angeles). A 429 response overrides the estimate with the exact wait.
final class Quota: ObservableObject {
    static let shared = Quota()

    private struct SlotQuota: Codable {
        var day = ""
        var used = 0
        var limit = 25
        var blockedUntil: Date?
    }

    private let lock = NSLock()
    private var slots: [Int: SlotQuota]
    private let defaults = UserDefaults.standard

    /// Warn when total remaining requests across all configured keys reaches these numbers.
    private static let warnAt: Set<Int> = [5, 1]
    private static let storageKey = "quota.gemini.slots"
    private static let pacificTimeZone = TimeZone(identifier: "America/Los_Angeles")!

    private init() {
        if let saved = Self.load([Int: SlotQuota].self, key: Self.storageKey) {
            slots = saved
        } else if let legacy = Self.load(SlotQuota.self, key: "quota.gemini") {
            slots = [1: legacy]
        } else {
            slots = [:]
        }
    }

    // MARK: Recording

    /// Call after a successful Gemini transcription on `slot`. Returns a warning when total quota is low.
    func recordSuccess(slot: Int, activeSlots: [Int]) -> String? {
        let totalRemaining: Int = locked {
            rollDayIfNeeded(slot: slot)
            var state = slots[slot] ?? SlotQuota(day: Self.pacificDay(Date()))
            state.used += 1
            slots[slot] = state

            let tracked = activeSlots.isEmpty ? [slot] : activeSlots
            return tracked.reduce(0) { sum, s in
                rollDayIfNeeded(slot: s)
                let st = slots[s] ?? SlotQuota(day: Self.pacificDay(Date()))
                if let until = st.blockedUntil, until > Date() { return sum }
                return sum + max(0, st.limit - st.used)
            }
        }
        save()
        return Self.warnAt.contains(totalRemaining)
            ? "Total kuota Gemini tinggal ±\(totalRemaining) hari ini"
            : nil
    }

    /// Call on HTTP 429 for `slot`. Learns the real limit/wait from the error message.
    @discardableResult
    func recordLimitHit(slot: Int, message: String) -> Date {
        let wait = Self.retryDelay(in: message) ?? 10 * 60
        let until = Date().addingTimeInterval(wait)
        locked {
            rollDayIfNeeded(slot: slot)
            var state = slots[slot] ?? SlotQuota(day: Self.pacificDay(Date()))
            if let limit = Self.firstInt(in: message, pattern: #"limit:\s*(\d+)"#) {
                state.limit = limit
            }
            state.used = max(state.used, state.limit)
            state.blockedUntil = until
            slots[slot] = state
        }
        save()
        return until
    }

    /// Triggers UI refresh when keys are added or removed in Settings.
    func notifyChanged() {
        DispatchQueue.main.async { self.objectWillChange.send() }
    }

    // MARK: Reading

    /// When `slot` may be tried again after hitting its limit, or nil if it's available.
    func blockedUntil(slot: Int) -> Date? {
        locked {
            guard let until = slots[slot]?.blockedUntil, until > Date() else { return nil }
            return until
        }
    }

    /// Combined one-line summary across all configured keys (for menu bar & Settings).
    func summary(for configuredSlots: [Int]) -> String? {
        guard !configuredSlots.isEmpty else { return nil }
        let now = Date()
        let result: (remaining: Int, totalLimit: Int, earliestUnlock: Date?) = locked {
            var remaining = 0
            var totalLimit = 0
            var earliest: Date?
            for s in configuredSlots {
                rollDayIfNeeded(slot: s)
                let st = slots[s] ?? SlotQuota(day: Self.pacificDay(now))
                totalLimit += st.limit
                if let until = st.blockedUntil, until > now {
                    if earliest == nil || until < earliest! { earliest = until }
                } else {
                    remaining += max(0, st.limit - st.used)
                }
            }
            return (remaining, totalLimit, earliest)
        }

        let label = configuredSlots.count > 1 ? "Gemini (\(configuredSlots.count) key)" : "Gemini"
        if result.remaining == 0, let unlock = result.earliestUnlock {
            return "\(label): semua habis · tersedia lagi \(Self.clock(unlock))"
        }
        return "\(label): ±\(result.remaining) / \(result.totalLimit) tersisa · reset \(Self.clock(Self.nextPacificMidnight()))"
    }

    /// Compact per-key status shown under each API key row in Settings.
    func slotSummary(slot: Int) -> String {
        if let until = blockedUntil(slot: slot) {
            return "Habis · tersedia lagi \(Self.clock(until))"
        }
        let (used, limit) = locked { () -> (Int, Int) in
            rollDayIfNeeded(slot: slot)
            let st = slots[slot] ?? SlotQuota(day: Self.pacificDay(Date()))
            return (st.used, st.limit)
        }
        return "±\(max(0, limit - used)) / \(limit) tersisa"
    }

    // MARK: Helpers

    private func rollDayIfNeeded(slot: Int) {
        let today = Self.pacificDay(Date())
        var state = slots[slot] ?? SlotQuota(day: today)
        if state.day != today {
            state.day = today
            state.used = 0
            if let until = state.blockedUntil, until <= Date() {
                state.blockedUntil = nil
            }
            slots[slot] = state
        }
    }

    private func locked<T>(_ body: () -> T) -> T {
        lock.lock()
        defer { lock.unlock() }
        return body()
    }

    private func save() {
        let snapshot = locked { slots }
        if let data = try? JSONEncoder().encode(snapshot) {
            defaults.set(data, forKey: Self.storageKey)
        }
        DispatchQueue.main.async { self.objectWillChange.send() }
    }

    private static func load<T: Decodable>(_ type: T.Type, key: String) -> T? {
        UserDefaults.standard.data(forKey: key).flatMap { try? JSONDecoder().decode(type, from: $0) }
    }

    private static func pacificDay(_ date: Date) -> String {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = pacificTimeZone
        let c = calendar.dateComponents([.year, .month, .day], from: date)
        return "\(c.year ?? 0)-\(c.month ?? 0)-\(c.day ?? 0)"
    }

    private static func nextPacificMidnight() -> Date {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = pacificTimeZone
        let start = calendar.startOfDay(for: Date())
        return calendar.date(byAdding: .day, value: 1, to: start) ?? Date()
    }

    /// "15.00" today, "besok 15.00" tomorrow, otherwise with the date.
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
