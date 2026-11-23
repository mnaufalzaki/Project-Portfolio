import Foundation

/// Preserves audio chunks when every transcription engine fails, so speech is never lost.
/// Keeps at most the latest 5 failed files in Application Support/Yaping/failed/.
@MainActor
final class FailedRecordings: ObservableObject {
    static let shared = FailedRecordings()

    struct Item: Identifiable {
        let url: URL
        let date: Date
        var id: URL { url }
    }

    @Published private(set) var items: [Item] = []

    private static let maxStored = 5
    private static let maxAge: TimeInterval = 24 * 3600
    private static let folder: URL = {
        FileManager.default.urls(for: .applicationSupportDirectory, in: .userDomainMask)[0]
            .appendingPathComponent("Yaping/failed", isDirectory: true)
    }()

    private init() {
        reload()
    }

    var count: Int { items.count }
    var latest: Item? { items.first }

    /// Moves a failed temporary WAV into persistent storage and trims older files beyond `maxStored`.
    func save(from tempURL: URL) {
        let fm = FileManager.default
        do {
            try fm.createDirectory(at: Self.folder, withIntermediateDirectories: true)
            let stamp = Int(Date().timeIntervalSince1970 * 1000)
            let dest = Self.folder.appendingPathComponent("yaping-failed-\(stamp)-\(UUID().uuidString.prefix(6)).wav")
            if fm.fileExists(atPath: tempURL.path) {
                try fm.moveItem(at: tempURL, to: dest)
            }
            reload()
            trimExcess()
        } catch {
            Log.write("failed to preserve audio chunk: \(error.localizedDescription)")
            try? fm.removeItem(at: tempURL)
        }
    }

    func remove(_ item: Item) {
        try? FileManager.default.removeItem(at: item.url)
        reload()
    }

    func clearAll() {
        for item in items {
            try? FileManager.default.removeItem(at: item.url)
        }
        reload()
    }

    func reload() {
        let fm = FileManager.default
        guard let urls = try? fm.contentsOfDirectory(
            at: Self.folder,
            includingPropertiesForKeys: [.creationDateKey, .contentModificationDateKey],
            options: [.skipsHiddenFiles]
        ) else {
            items = []
            return
        }
        let cutoff = Date().addingTimeInterval(-Self.maxAge)
        var kept: [Item] = []
        for url in urls where url.pathExtension.lowercased() == "wav" {
            let values = try? url.resourceValues(forKeys: [.creationDateKey, .contentModificationDateKey])
            let date = values?.creationDate ?? values?.contentModificationDate ?? Date.distantPast
            if date < cutoff {
                try? fm.removeItem(at: url)
            } else {
                kept.append(Item(url: url, date: date))
            }
        }
        items = kept.sorted { $0.date > $1.date }
    }

    private func trimExcess() {
        guard items.count > Self.maxStored else { return }
        for old in items.dropFirst(Self.maxStored) {
            try? FileManager.default.removeItem(at: old.url)
        }
        reload()
    }
}
