import AppKit

/// Watches a single modifier key system-wide (needs Accessibility permission).
@MainActor
final class HotkeyMonitor {
    var onPress: (() -> Void)?
    var onRelease: (() -> Void)?
    var onEscape: (() -> Void)?
    /// Another key was pressed while the hotkey was held — it's a shortcut, not dictation.
    var onShortcut: (() -> Void)?

    private var monitors: [Any] = []
    private var isDown = false

    func start() {
        stop()
        let mask: NSEvent.EventTypeMask = [.flagsChanged, .keyDown]
        if let m = NSEvent.addGlobalMonitorForEvents(matching: mask, handler: { [weak self] e in
            self?.handle(e)
        }) {
            monitors.append(m)
        }
        if let m = NSEvent.addLocalMonitorForEvents(matching: mask, handler: { [weak self] e in
            self?.handle(e)
            return e
        }) {
            monitors.append(m)
        }
    }

    func stop() {
        monitors.forEach(NSEvent.removeMonitor)
        monitors.removeAll()
        isDown = false
    }

    private func handle(_ e: NSEvent) {
        if e.type == .keyDown {
            if e.keyCode == 53 {
                onEscape?()
            } else if isDown {
                isDown = false
                onShortcut?()
            }
            return
        }
        let key = AppSettings.shared.hotkey
        guard key.concerns(keyCode: e.keyCode) else { return }
        let down = key.isPressed(e.modifierFlags)
        if down && !isDown {
            isDown = true
            onPress?()
        } else if !down && isDown {
            isDown = false
            if key.hasExtraModifiers(e.modifierFlags) { onShortcut?() } else { onRelease?() }
        }
    }
}
