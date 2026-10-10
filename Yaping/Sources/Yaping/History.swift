import Foundation

struct HistoryEntry: Codable, Identifiable {
    var id = UUID()
    var date: Date
    var text: String
    var raw: String

    var wordCount: Int { text.split(whereSeparator: \.isWhitespace).count }
}

final class HistoryStore: ObservableObject {
    static let shared = HistoryStore()
    private static let key = "history"
    private static let limit = 100

    @Published private(set) var entries: [HistoryEntry] = []

    private init() {
        if let data = UserDefaults.standard.data(forKey: Self.key),
           let saved = try? JSONDecoder().decode([HistoryEntry].self, from: data) {
            entries = saved
        }
    }

    var totalWords: Int { entries.reduce(0) { $0 + $1.wordCount } }

    func add(text: String, raw: String) {
        entries.insert(HistoryEntry(date: Date(), text: text, raw: raw), at: 0)
        if entries.count > Self.limit { entries.removeLast(entries.count - Self.limit) }
        save()
    }

    func clear() {
        entries.removeAll()
        save()
    }

    private func save() {
        if let data = try? JSONEncoder().encode(entries) {
            UserDefaults.standard.set(data, forKey: Self.key)
        }
    }
}
