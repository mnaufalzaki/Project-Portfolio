import AVFoundation
import Combine
import ServiceManagement
import SwiftUI

struct SettingsView: View {
    var body: some View {
        TabView {
            GeneralTab().tabItem { Label("Umum", systemImage: "gearshape") }
            EngineTab().tabItem { Label("Mesin AI", systemImage: "sparkles") }
            HistoryTab().tabItem { Label("Riwayat", systemImage: "clock.arrow.circlepath") }
        }
        .frame(width: 580, height: 540)
    }
}

/// Live permission + login-item status (plain ObservableObject: the CLT toolchain lacks SwiftUI's @State macro plugin).
private final class GeneralModel: ObservableObject {
    @Published var launchAtLogin = SMAppService.mainApp.status == .enabled {
        didSet {
            guard launchAtLogin != oldValue else { return }
            if launchAtLogin { try? SMAppService.mainApp.register() } else { try? SMAppService.mainApp.unregister() }
        }
    }
    @Published var accessibility = Permissions.accessibilityTrusted(prompt: false)
    @Published var microphone = Permissions.microphone

    func refresh() {
        let ax = Permissions.accessibilityTrusted(prompt: false)
        if ax != accessibility { accessibility = ax }
        let mic = Permissions.microphone
        if mic != microphone { microphone = mic }
    }
}

private struct GeneralTab: View {
    @ObservedObject private var s = AppSettings.shared
    @StateObject private var m = GeneralModel()

    private let refresh = Timer.publish(every: 1.5, on: .main, in: .common).autoconnect()

    var body: some View {
        Form {
            Section("Tombol dikte") {
                Picker("Tombol", selection: $s.hotkey) {
                    ForEach(HotkeyChoice.allCases) { Text($0.label).tag($0) }
                }
                Picker("Cara pakai", selection: $s.hotkeyMode) {
                    ForEach(HotkeyMode.allCases) { Text($0.label).tag($0) }
                }
                switch s.hotkeyMode {
                case .toggle:
                    Hint("**Tekan \(s.hotkey.symbol)** sekali untuk mulai bicara, **tekan lagi** untuk selesai dan menulis. **Esc** untuk batal.")
                case .holdOrTap:
                    Hint("**Tahan \(s.hotkey.symbol)** untuk bicara, lepas untuk menulis. **Ketuk sekali** untuk mode bebas tangan, ketuk lagi untuk selesai. **Esc** untuk batal.")
                }
                if s.hotkey == .commandOption {
                    Hint("Shortcut seperti ⌘⌥D tetap jalan normal: kalau ada tombol lain yang ikut ditekan, rekaman langsung dibatalkan.")
                }
                if s.hotkey == .fn {
                    Hint("Tip: di System Settings › Keyboard, set “Press 🌐 key to” ke “Do Nothing” supaya Fn tidak membuka emoji/dikte bawaan.")
                }
            }
            Section("Perilaku") {
                Toggle("Bunyi saat mulai & selesai", isOn: $s.playSounds)
                Toggle("Kembalikan isi clipboard setelah menempel", isOn: $s.restoreClipboard)
                Toggle("Tampilkan teks bertahap saat bicara lama", isOn: $s.progressiveInsert)
                Hint("Rekaman panjang dipotong tiap ±1,5–2 menit (hemat kuota) dan diproses selagi kamu bicara. Kalau nyala, teks tiap potongan langsung muncul — jangan pindah kolom/aplikasi selama merekam. Kalau mati, semuanya muncul sekaligus di akhir.")
                Toggle("Buka otomatis saat login", isOn: $m.launchAtLogin)
            }
            Section("Izin") {
                PermissionRow(title: "Mikrofon", granted: m.microphone == .authorized) {
                    if m.microphone == .notDetermined { Permissions.requestMicrophone() } else { Permissions.openMicrophoneSettings() }
                }
                PermissionRow(title: "Accessibility — untuk tombol & menempel teks", granted: m.accessibility) {
                    _ = Permissions.accessibilityTrusted(prompt: true)
                    Permissions.openAccessibilitySettings()
                }
            }
            Section("Tentang") {
                AboutRow()
            }
        }
        .formStyle(.grouped)
        .onReceive(refresh) { _ in m.refresh() }
    }
}

private struct AboutRow: View {
    private var version: String {
        Bundle.main.object(forInfoDictionaryKey: "CFBundleShortVersionString") as? String ?? "1.0"
    }

    var body: some View {
        HStack(alignment: .center, spacing: 14) {
            Image(nsImage: NSApp.applicationIconImage)
                .resizable()
                .frame(width: 48, height: 48)
            VStack(alignment: .leading, spacing: 3) {
                Text("Yaping \(version)").font(.headline)
                Text("Made by Naufal Zaki").foregroundStyle(.secondary)
                HStack(spacing: 14) {
                    Link(destination: URL(string: "https://naufalzaki.tech")!) {
                        Label("naufalzaki.tech", systemImage: "globe")
                    }
                    Link(destination: URL(string: "https://github.com/mnaufalzaki")!) {
                        Label("github.com/mnaufalzaki", systemImage: "chevron.left.forwardslash.chevron.right")
                    }
                }
                .font(.callout)
            }
        }
        .padding(.vertical, 4)
    }
}

private struct EngineTab: View {
    @ObservedObject private var s = AppSettings.shared
    @ObservedObject private var quota = Quota.shared

    var body: some View {
        Form {
            Section("Google Gemini 3.5 Transcribe") {
                TextField("Model", text: $s.geminiModel)
                Toggle("Mode smart (buang “eh/emm” & ikuti koreksi, tanpa mengubah kata)", isOn: $s.geminiSmart)
                Picker("Bahasa", selection: $s.language) {
                    Text("Otomatis (campur juga bisa)").tag("auto")
                    Text("Bahasa Indonesia").tag("id")
                    Text("English").tag("en")
                }
                if let usage = quota.summary(for: s.configuredGeminiSlots) {
                    QuotaRow(text: usage)
                }
            }

            Section("API Key Gemini (1, 2, 3)") {
                Hint("Isi 1 sampai 3 API key dari Google AI Studio. Jika Key 1 kena batas kuota harian atau error, Yaping otomatis pindah ke Key 2 lalu Key 3.")
                ForEach(GeminiKeySlot.all) { item in
                    VStack(alignment: .leading, spacing: 4) {
                        KeyField(title: item.title, account: item.account)
                        if KeyStore.status(item.account) != .missing {
                            Text("Key \(item.slot): \(quota.slotSummary(slot: item.slot))")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                    .padding(.vertical, 2)
                }
                Link("Dapatkan API key di Google AI Studio ↗", destination: AppSettings.geminiKeyURL)
                    .font(.caption)
            }
        }
        .formStyle(.grouped)
    }
}

private struct QuotaRow: View {
    let text: String

    var body: some View {
        Label(text, systemImage: text.contains("habis") ? "hourglass" : "gauge.with.dots.needle.33percent")
            .font(.callout)
            .foregroundStyle(text.contains("habis") ? .orange : .secondary)
    }
}

/// Tracks which history entry was just copied so the button can show a brief confirmation.
private final class CopyFeedback: ObservableObject {
    @Published var copiedID: UUID?
    private var clearWork: DispatchWorkItem?

    func copy(_ entry: HistoryEntry) {
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(entry.text, forType: .string)
        copiedID = entry.id
        clearWork?.cancel()
        let work = DispatchWorkItem { [weak self] in
            if self?.copiedID == entry.id { self?.copiedID = nil }
        }
        clearWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 1.5, execute: work)
    }
}

private struct HistoryTab: View {
    @ObservedObject private var history = HistoryStore.shared
    @StateObject private var feedback = CopyFeedback()

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("\(history.totalWords) kata didikte · \(history.entries.count) catatan")
                    .font(.callout)
                    .foregroundStyle(.secondary)
                Spacer()
                Button("Hapus Semua", role: .destructive) { history.clear() }
                    .disabled(history.entries.isEmpty)
            }
            .padding(.horizontal, 16)
            .padding(.vertical, 12)
            Divider()
            if history.entries.isEmpty {
                VStack(spacing: 8) {
                    Image(systemName: "waveform")
                        .font(.system(size: 28))
                        .foregroundStyle(.tertiary)
                    Text("Belum ada riwayat dikte")
                        .foregroundStyle(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List(history.entries) { entry in
                    let isCopied = feedback.copiedID == entry.id
                    VStack(alignment: .leading, spacing: 10) {
                        Text(entry.text)
                            .font(.body)
                            .lineSpacing(2)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                        HStack(alignment: .center) {
                            Text("\(entry.date.formatted(date: .abbreviated, time: .shortened)) · \(entry.wordCount) kata")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                            Spacer()
                            Button {
                                feedback.copy(entry)
                            } label: {
                                Label(isCopied ? "Tersalin" : "Salin",
                                      systemImage: isCopied ? "checkmark" : "doc.on.doc")
                                    .font(.callout.weight(.medium))
                                    .foregroundStyle(isCopied ? .green : .primary)
                            }
                            .buttonStyle(.bordered)
                            .controlSize(.regular)
                        }
                    }
                    .padding(.vertical, 8)
                }
            }
        }
    }
}

/// A key is typed, then explicitly saved; once saved it's locked until "Ubah" is pressed.
/// Status comes from the Keychain without reading the secret, so opening Settings never prompts.
private final class KeyModel: ObservableObject {
    let account: String
    @Published private(set) var status: KeyStore.Status
    @Published var editing: Bool
    @Published var draft = ""
    @Published private(set) var error: String?

    init(account: String) {
        self.account = account
        let status = KeyStore.status(account)
        self.status = status
        editing = status == .missing
    }

    var canSave: Bool { !draft.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty }

    func save() {
        guard canSave else { return }
        if KeyStore.set(draft, for: account) {
            draft = ""
            editing = false
            error = nil
            Quota.shared.notifyChanged()
        } else {
            error = "Gagal menyimpan API key — coba lagi"
        }
        status = KeyStore.status(account)
    }

    func startEditing() {
        draft = ""
        error = nil
        editing = true
    }

    func cancel() {
        draft = ""
        error = nil
        editing = status == .missing
    }

    func remove() {
        KeyStore.set("", for: account)
        status = KeyStore.status(account)
        editing = true
        Quota.shared.notifyChanged()
    }

    /// Asks macOS again for a key it refused to hand over.
    func allow() {
        if KeyStore.retry(account) {
            error = nil
        } else {
            error = "Masih ditolak — klik Izinkan lalu pilih “Always Allow”, atau Ubah untuk memasukkan ulang"
        }
        status = KeyStore.status(account)
        Quota.shared.notifyChanged()
    }
}

private struct KeyField: View {
    let title: String
    @StateObject private var model: KeyModel

    init(title: String, account: String) {
        self.title = title
        _model = StateObject(wrappedValue: KeyModel(account: account))
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            if model.editing {
                HStack {
                    SecureField(title, text: $model.draft, prompt: Text("Tempel API key di sini"))
                        .onSubmit { model.save() }
                    Button("Simpan") { model.save() }
                        .keyboardShortcut(.defaultAction)
                        .disabled(!model.canSave)
                    if model.status != .missing {
                        Button("Batal") { model.cancel() }
                    }
                }
            } else {
                HStack {
                    Text(title)
                    Spacer()
                    switch model.status {
                    case .saved:
                        Label("Tersimpan", systemImage: "checkmark.seal.fill")
                            .foregroundStyle(.green)
                        Text("••••••••••").foregroundStyle(.secondary)
                    case .locked:
                        Label("Tersimpan, tapi belum diizinkan dibaca", systemImage: "lock.fill")
                            .foregroundStyle(.orange)
                        Button("Izinkan") { model.allow() }
                    case .missing:
                        EmptyView()
                    }
                    Button("Ubah") { model.startEditing() }
                    Button("Hapus", role: .destructive) { model.remove() }
                }
            }
            if let error = model.error {
                Text(error).font(.caption).foregroundStyle(.red)
            }
        }
    }
}

private struct PermissionRow: View {
    let title: String
    let granted: Bool
    let action: () -> Void

    var body: some View {
        HStack {
            Image(systemName: granted ? "checkmark.circle.fill" : "xmark.circle.fill")
                .foregroundStyle(granted ? .green : .red)
            Text(title)
            Spacer()
            if !granted { Button("Izinkan…", action: action) }
        }
    }
}

private struct Hint: View {
    let text: LocalizedStringKey
    init(_ text: LocalizedStringKey) { self.text = text }

    var body: some View {
        Text(text).font(.caption).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
    }
}
