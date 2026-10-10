import AVFoundation
import Combine
import ServiceManagement
import SwiftUI

struct SettingsView: View {
    var body: some View {
        TabView {
            GeneralTab().tabItem { Label("Umum", systemImage: "gearshape") }
            EngineTab().tabItem { Label("Mesin AI", systemImage: "sparkles") }
            VocabularyTab().tabItem { Label("Kosakata", systemImage: "character.book.closed") }
            HistoryTab().tabItem { Label("Riwayat", systemImage: "clock.arrow.circlepath") }
        }
        .frame(width: 580, height: 560)
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
                Hint("Rekaman panjang dipotong tiap ±1 menit dan diproses selagi kamu bicara. Kalau nyala, teks tiap potongan langsung muncul — jangan pindah kolom/aplikasi selama merekam. Kalau mati, semuanya muncul sekaligus di akhir.")
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

/// Status of the local engines, refreshed while the tab is open.
private final class LocalStatus: ObservableObject {
    @Published var whisperInstalled = LocalWhisper.isInstalled
    @Published var ollamaModels: [String] = []
    @Published var ollamaReachable = false

    func refresh() {
        let installed = LocalWhisper.isInstalled
        if installed != whisperInstalled { whisperInstalled = installed }
        Task { @MainActor in
            let models = await Ollama.installedModels()
            if models != ollamaModels { ollamaModels = models }
            let reachable = !models.isEmpty
            if reachable != ollamaReachable { ollamaReachable = reachable }
        }
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
    @StateObject private var local = LocalStatus()
    private let refresh = Timer.publish(every: 3, on: .main, in: .common).autoconnect()

    var body: some View {
        Form {
            Section("Transkripsi (suara → teks)") {
                Picker("Penyedia utama", selection: $s.provider) {
                    ForEach(TranscriptionProvider.allCases) { Text($0.label).tag($0) }
                }
                switch s.provider {
                case .local:
                    StatusRow(ok: local.whisperInstalled,
                              okText: "whisper.cpp siap — model: \(LocalWhisper.modelPath.map { URL(fileURLWithPath: $0).lastPathComponent } ?? "-")",
                              badText: "whisper.cpp atau modelnya belum terpasang")
                    if !local.whisperInstalled {
                        Hint("Jalankan di Terminal: `./scripts/setup-local.sh` (dari folder Yaping). Butuh ±600 MB ruang disk.")
                    }
                    Button("Buka Folder Model") {
                        try? FileManager.default.createDirectory(at: LocalWhisper.modelsDir, withIntermediateDirectories: true)
                        NSWorkspace.shared.open(LocalWhisper.modelsDir)
                    }
                case .apple:
                    Hint("Memakai pengenal suara Apple langsung di Mac. Gratis dan offline, tapi akurasinya di bawah Whisper.")
                case .gemini:
                    Hint("Gratis: buka aistudio.google.com/apikey → Create API key, lalu tempel di bawah. Di tier gratis, Google boleh memakai audio untuk meningkatkan produknya.")
                    KeyField(title: "API key", account: s.provider.rawValue)
                        .id(s.provider)
                    TextField("Model", text: modelBinding(s.provider))
                    Toggle("Mode smart — buang “eh/emm” & ikuti koreksi, tanpa mengubah kata", isOn: $s.geminiSmart)
                    Hint("Kosakata pribadi dikirim sebagai daftar istilah yang benar-benar dipakai model (sampai 1.000 istilah).")
                    Link("Dapatkan API key ↗", destination: s.provider.keyURL!).font(.caption)
                case .groq, .openai, .custom:
                    if s.provider == .custom {
                        TextField("Base URL", text: $s.customBaseURL)
                    }
                    if s.provider == .groq {
                        Hint("Gratis tanpa kartu kredit: daftar di console.groq.com → API Keys → Create API Key, lalu tempel di bawah.")
                    }
                    KeyField(title: "API key", account: s.provider.rawValue)
                        .id(s.provider)
                    TextField("Model", text: modelBinding(s.provider))
                    if let url = s.provider.keyURL {
                        Link("Dapatkan API key ↗", destination: url).font(.caption)
                    }
                }
                if let usage = quota.summary(for: s.provider) {
                    QuotaRow(text: usage)
                }
                Picker("Bahasa", selection: $s.language) {
                    Text("Otomatis (campur juga bisa)").tag("auto")
                    Text("Bahasa Indonesia").tag("id")
                    Text("English").tag("en")
                }
            }

            Section("Cadangan otomatis") {
                Picker("Penyedia cadangan", selection: $s.backupProvider) {
                    Text("Tidak ada").tag(TranscriptionProvider?.none)
                    ForEach(TranscriptionProvider.allCases.filter { $0 != s.provider }) {
                        Text($0.label).tag(Optional($0))
                    }
                }
                if let backup = s.backupProvider {
                    switch backup {
                    case .groq, .gemini, .openai, .custom:
                        if backup == .custom {
                            TextField("Base URL cadangan", text: $s.customBaseURL)
                        }
                        KeyField(title: "API key \(backup.shortName)", account: backup.rawValue)
                            .id("backup-\(backup.rawValue)")
                        TextField("Model cadangan", text: modelBinding(backup))
                        if let usage = quota.summary(for: backup) {
                            QuotaRow(text: usage)
                        }
                    case .local:
                        StatusRow(ok: local.whisperInstalled,
                                  okText: "Whisper lokal siap",
                                  badText: "Whisper lokal belum terpasang — jalankan ./scripts/setup-local.sh")
                    case .apple:
                        Hint("Pengenal suara Apple, tanpa API key. Akurasinya paling rendah.")
                    }
                }
                Toggle("Pakai Whisper lokal kalau semua gagal (offline)", isOn: $s.offlineFallback)
                    .disabled(!local.whisperInstalled)
                Hint("Urutan saat ini: \(s.transcriptionChain.map(\.shortName).joined(separator: " → ")). Kalau satu penyedia gagal (kuota habis, internet, key salah), yang berikutnya langsung dipakai. Penyedia yang kuotanya habis diistirahatkan 10 menit.")
            }

            Section("Perapian AI") {
                Toggle("Rapikan hasil dikte", isOn: $s.cleanupEnabled)
                if s.cleanupEnabled {
                    Picker("Gaya", selection: $s.cleanupStyle) {
                        ForEach(CleanupStyle.allCases) { Text($0.label).tag($0) }
                    }
                    Picker("Penyedia", selection: $s.cleanupProvider) {
                        Text("Groq — gratis, kualitas terbaik (cloud)").tag(CleanupProvider.groq)
                        Text("Lokal — Ollama (gratis, offline)").tag(CleanupProvider.ollama)
                        Text("Claude (Anthropic, berbayar)").tag(CleanupProvider.claude)
                        Text("Sama dengan transkripsi (mis. Groq gratis)").tag(CleanupProvider.sameAsTranscription)
                    }
                    switch s.cleanupProvider {
                    case .groq:
                        Hint("Gratis tanpa kartu kredit: daftar di console.groq.com → API Keys → Create API Key, lalu tempel di bawah. Hanya teks hasil transkripsi yang dikirim, bukan suaramu.")
                        KeyField(title: "Groq API key", account: "groq")
                        Picker("Model", selection: $s.groqChatModel) {
                            ForEach(groqModelOptions, id: \.self) { Text(Groq.label(for: $0)).tag($0) }
                        }
                        Hint(s.groqModels.isEmpty
                             ? "Daftar model akan dimuat dari akun Groq-mu setelah API key diisi."
                             : "\(s.groqModels.count) model tersedia di akun Groq-mu. Kalau model yang dipilih tidak tersedia, Yaping pindah otomatis.")
                        Link("Dapatkan API key ↗", destination: URL(string: "https://console.groq.com/keys")!)
                            .font(.caption)
                    case .ollama:
                        StatusRow(ok: local.ollamaReachable,
                                  okText: "Ollama jalan — \(local.ollamaModels.count) model terpasang",
                                  badText: "Ollama tidak jalan atau belum ada model")
                        Picker("Model", selection: $s.ollamaModel) {
                            Text("Otomatis (model pertama)").tag("")
                            ForEach(local.ollamaModels, id: \.self) { Text($0).tag($0) }
                        }
                        Hint("Model 4–9B seperti Qwen 3.5 atau Gemma 3 sudah cukup bagus untuk Bahasa Indonesia. Model yang lebih kecil = lebih cepat.")
                    case .claude:
                        KeyField(title: "Anthropic API key", account: "anthropic")
                        Picker("Model", selection: $s.claudeModel) {
                            Text("Claude Opus 5.5 — paling pintar").tag("claude-opus-5-5")
                            Text("Claude Sonnet 5.5").tag("claude-sonnet-5-5")
                            Text("Claude Haiku 5.5 — paling cepat & murah").tag("claude-haiku-5-5")
                        }
                        Link("Dapatkan API key ↗", destination: URL(string: "https://console.anthropic.com/settings/keys")!)
                            .font(.caption)
                    case .sameAsTranscription:
                        if !s.provider.isOpenAICompatible {
                            Hint("Penyedia transkripsi ini tidak punya model teks — pilih Ollama atau Claude.")
                                .foregroundStyle(.orange)
                        } else {
                            TextField("Model chat", text: $s.chatModel)
                        }
                    }
                }
            }
        }
        .formStyle(.grouped)
        .onAppear {
            local.refresh()
            Groq.refreshModels()
        }
        .onReceive(refresh) { _ in local.refresh() }
    }
}

private extension EngineTab {
    /// Each engine keeps its own model name (see `AppSettings.model(for:)`).
    func modelBinding(_ engine: TranscriptionProvider) -> Binding<String> {
        Binding(get: { s.model(for: engine) }, set: { s.setModel($0, for: engine) })
    }

    /// The account's models (or the known defaults before we've asked), always including the current pick.
    var groqModelOptions: [String] {
        var options = s.groqModels.isEmpty ? Array(Groq.preferred) : s.groqModels
        if !options.contains(s.groqChatModel) { options.insert(s.groqChatModel, at: 0) }
        return options
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

private struct StatusRow: View {
    let ok: Bool
    let okText: String
    let badText: String

    var body: some View {
        Label(ok ? okText : badText, systemImage: ok ? "checkmark.circle.fill" : "exclamationmark.circle.fill")
            .foregroundStyle(ok ? .green : .orange)
            .font(.callout)
    }
}

private struct VocabularyTab: View {
    @ObservedObject private var s = AppSettings.shared

    var body: some View {
        Form {
            Section {
                TextEditor(text: $s.vocabulary)
                    .font(.body.monospaced())
                    .frame(minHeight: 260)
            } header: {
                Text("Kosakata pribadi")
            } footer: {
                Hint("Satu kata per baris (atau pisahkan dengan koma): nama orang, merek, istilah teknis. Yaping akan mengejanya persis seperti ini.\nContoh: Naufal, Supabase, Kubernetes, ITS Surabaya")
            }
        }
        .formStyle(.grouped)
    }
}

private struct HistoryTab: View {
    @ObservedObject private var history = HistoryStore.shared

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("\(history.totalWords) kata didikte · \(history.entries.count) catatan")
                    .foregroundStyle(.secondary)
                Spacer()
                Button("Hapus Semua", role: .destructive) { history.clear() }
                    .disabled(history.entries.isEmpty)
            }
            .padding()
            List(history.entries) { entry in
                VStack(alignment: .leading, spacing: 4) {
                    Text(entry.text).textSelection(.enabled)
                    HStack {
                        Spacer()
                        Button("Salin") {
                            NSPasteboard.general.clearContents()
                            NSPasteboard.general.setString(entry.text, forType: .string)
                        }
                        .buttonStyle(.link)
                        .font(.caption)
                    }
                }
                .padding(.vertical, 4)
            }
        }
    }
}

private final class KeyModel: ObservableObject {
    let account: String
    @Published var value: String {
        didSet {
            KeyStore.set(value, for: account)
            if account == "groq" { Groq.scheduleRefresh() }
        }
    }

    init(account: String) {
        self.account = account
        value = KeyStore.get(account)
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
        SecureField(title, text: $model.value, prompt: Text("Tempel di sini"))
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
