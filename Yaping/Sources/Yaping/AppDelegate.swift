import AppKit
import Combine
import SwiftUI

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate, NSMenuDelegate {
    private var statusItem: NSStatusItem!
    private let controller = DictationController()
    private let hotkeys = HotkeyMonitor()
    private var settingsWindow: NSWindow?
    private var cancellables = Set<AnyCancellable>()
    private var accessibilityTimer: Timer?

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Two copies would both react to the hotkey and paste twice.
        let others = NSRunningApplication.runningApplications(withBundleIdentifier: Bundle.main.bundleIdentifier ?? "")
            .filter { $0 != NSRunningApplication.current }
        if !others.isEmpty {
            NSApp.terminate(nil)
            return
        }

        installMainMenu()

        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)
        let menu = NSMenu()
        menu.delegate = self
        statusItem.menu = menu
        updateIcon(.idle)

        controller.$state
            .sink { [weak self] in self?.updateIcon($0) }
            .store(in: &cancellables)

        hotkeys.onPress = { [weak self] in self?.controller.hotkeyDown() }
        hotkeys.onRelease = { [weak self] in self?.controller.hotkeyUp() }
        hotkeys.onEscape = { [weak self] in self?.controller.cancel() }
        hotkeys.onShortcut = { [weak self] in self?.controller.shortcutPressed() }
        hotkeys.start()

        let keysCount = AppSettings.shared.configuredGeminiSlots.count
        Log.write("launch: accessibility=\(Permissions.accessibilityTrusted(prompt: false)) mic=\(Permissions.microphone.rawValue) model=\(AppSettings.shared.effectiveGeminiModel) keys=\(keysCount)")
        if Permissions.microphone == .notDetermined { Permissions.requestMicrophone() }
        if !Permissions.accessibilityTrusted(prompt: true) { waitForAccessibility() }
        if AppSettings.shared.needsSetup { openSettings() }
    }

    /// Installs a standard hidden Edit & Window menu so ⌘V, ⌘C, ⌘X, ⌘A, ⌘Z, and ⌘W work
    /// inside Settings fields even though Yaping runs as a menu bar app (LSUIElement).
    private func installMainMenu() {
        let main = NSMenu()

        let appItem = NSMenuItem()
        let appMenu = NSMenu()
        appMenu.addItem(withTitle: "Keluar Yaping", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        appItem.submenu = appMenu
        main.addItem(appItem)

        let editItem = NSMenuItem()
        let editMenu = NSMenu(title: "Edit")
        editMenu.addItem(withTitle: "Undo", action: Selector(("undo:")), keyEquivalent: "z")
        let redo = NSMenuItem(title: "Redo", action: Selector(("redo:")), keyEquivalent: "z")
        redo.keyEquivalentModifierMask = [.command, .shift]
        editMenu.addItem(redo)
        editMenu.addItem(.separator())
        editMenu.addItem(withTitle: "Cut", action: #selector(NSText.cut(_:)), keyEquivalent: "x")
        editMenu.addItem(withTitle: "Copy", action: #selector(NSText.copy(_:)), keyEquivalent: "c")
        editMenu.addItem(withTitle: "Paste", action: #selector(NSText.paste(_:)), keyEquivalent: "v")
        editMenu.addItem(withTitle: "Select All", action: #selector(NSText.selectAll(_:)), keyEquivalent: "a")
        editItem.submenu = editMenu
        main.addItem(editItem)

        let windowItem = NSMenuItem()
        let windowMenu = NSMenu(title: "Window")
        windowMenu.addItem(withTitle: "Close", action: #selector(NSWindow.performClose(_:)), keyEquivalent: "w")
        windowItem.submenu = windowMenu
        main.addItem(windowItem)

        NSApp.mainMenu = main
    }

    /// Global key monitors only start receiving events once Accessibility is granted.
    private func waitForAccessibility() {
        accessibilityTimer = Timer.scheduledTimer(withTimeInterval: 1.5, repeats: true) { [weak self] _ in
            Task { @MainActor in
                guard let self, Permissions.accessibilityTrusted(prompt: false) else { return }
                self.accessibilityTimer?.invalidate()
                self.accessibilityTimer = nil
                self.hotkeys.start()
            }
        }
    }

    private func updateIcon(_ state: DictationController.State) {
        let symbol: String
        switch state {
        case .idle: symbol = "waveform"
        case .recording: symbol = "waveform.circle.fill"
        case .processing: symbol = "ellipsis.circle"
        }
        let image = NSImage(systemSymbolName: symbol, accessibilityDescription: "Yaping")
        image?.isTemplate = true
        statusItem.button?.image = image
    }

    func menuNeedsUpdate(_ menu: NSMenu) {
        menu.removeAllItems()
        let s = AppSettings.shared

        let status: String
        switch controller.state {
        case .idle: status = s.hotkeyMode == .toggle
            ? "Tekan \(s.hotkey.symbol) untuk mulai bicara"
            : "Tahan \(s.hotkey.symbol) untuk bicara"
        case .recording: status = "Merekam…"
        case .processing: status = "Menulis…"
        }
        menu.addItem(withTitle: status, action: nil, keyEquivalent: "").isEnabled = false

        if !Permissions.accessibilityTrusted(prompt: false) {
            menu.addItem(item("⚠️ Beri izin Accessibility…", #selector(openAccessibility)))
        }

        if let quotaLine = Quota.shared.summary(for: s.configuredGeminiSlots) {
            menu.addItem(.separator())
            menu.addItem(withTitle: "Kuota hari ini", action: nil, keyEquivalent: "").isEnabled = false
            menu.addItem(withTitle: "   " + quotaLine, action: nil, keyEquivalent: "").isEnabled = false
        }
        menu.addItem(.separator())

        let isRecording: Bool
        if case .recording = controller.state { isRecording = true } else { isRecording = false }
        menu.addItem(item(isRecording ? "Selesai Dikte" : "Mulai Dikte (bebas tangan)", #selector(toggleDictation)))
        menu.addItem(item("Tempel Ulang Teks Terakhir", #selector(pasteLast)))
        let failedCount = FailedRecordings.shared.count
        if failedCount > 0 {
            menu.addItem(item("⚠️ Coba Ulang Rekaman Gagal (\(failedCount))", #selector(retryFailed)))
        }

        let historyItem = NSMenuItem(title: "Riwayat", action: nil, keyEquivalent: "")
        let historyMenu = NSMenu()
        let entries = HistoryStore.shared.entries.prefix(10)
        if entries.isEmpty {
            historyMenu.addItem(withTitle: "Belum ada", action: nil, keyEquivalent: "").isEnabled = false
        }
        for entry in entries {
            let title = entry.text.count > 60 ? String(entry.text.prefix(60)) + "…" : entry.text
            let mi = item(title.replacingOccurrences(of: "\n", with: " "), #selector(copyHistory(_:)))
            mi.representedObject = entry.text
            mi.toolTip = "Klik untuk menyalin"
            historyMenu.addItem(mi)
        }
        historyItem.submenu = historyMenu
        menu.addItem(historyItem)

        menu.addItem(.separator())
        menu.addItem(item("Pengaturan…", #selector(openSettings), key: ","))
        menu.addItem(item("Keluar Yaping", #selector(quit), key: "q"))
    }

    private func item(_ title: String, _ action: Selector, key: String = "") -> NSMenuItem {
        let mi = NSMenuItem(title: title, action: action, keyEquivalent: key)
        mi.target = self
        return mi
    }

    @objc private func toggleDictation() { controller.toggle() }
    @objc private func pasteLast() { controller.pasteLast() }
    @objc private func retryFailed() { controller.retryLastFailed() }
    @objc private func openAccessibility() {
        _ = Permissions.accessibilityTrusted(prompt: true)
        Permissions.openAccessibilitySettings()
    }
    @objc private func quit() { NSApp.terminate(nil) }

    @objc private func copyHistory(_ sender: NSMenuItem) {
        guard let text = sender.representedObject as? String else { return }
        NSPasteboard.general.clearContents()
        NSPasteboard.general.setString(text, forType: .string)
    }

    @objc func openSettings() {
        if settingsWindow == nil {
            let window = NSWindow(contentRect: .zero, styleMask: [.titled, .closable],
                                  backing: .buffered, defer: false)
            window.title = "Yaping"
            window.isReleasedWhenClosed = false
            window.contentView = NSHostingView(rootView: SettingsView())
            window.center()
            settingsWindow = window
        }
        NSApp.activate(ignoringOtherApps: true)
        settingsWindow?.makeKeyAndOrderFront(nil)
    }
}
