import AppKit
import SwiftUI

final class OverlayModel: ObservableObject {
    enum Phase: Equatable {
        case hidden
        case recording(locked: Bool)
        case processing
        case error(String)
    }

    static let barCount = 26

    @Published var phase: Phase = .hidden
    @Published var levels: [CGFloat] = Array(repeating: 0, count: barCount)

    func push(_ level: Float) {
        levels.removeFirst()
        levels.append(CGFloat(level))
    }

    func resetLevels() {
        levels = Array(repeating: 0, count: Self.barCount)
    }
}

/// Non-activating HUD panel that stays above full-screen apps (Safari, YouTube, etc.)
/// without ever stealing focus or triggering a macOS Space switch.
private final class HUDPanel: NSPanel {
    override var canBecomeKey: Bool { false }
    override var canBecomeMain: Bool { false }
}

/// The little floating pill at the bottom of the screen.
/// Stays registered with macOS WindowServer (hidden via `alphaValue = 0` instead of `orderOut`)
/// so it remains attached to every Space, including foreign Full-Screen Spaces like Safari.
@MainActor
final class OverlayController {
    let model = OverlayModel()
    private var hideWork: DispatchWorkItem?
    private var spaceObserver: NSObjectProtocol?

    private static let hudBehavior: NSWindow.CollectionBehavior = [
        .canJoinAllSpaces,
        .fullScreenAuxiliary,
        .ignoresCycle,
    ]

    private lazy var panel: HUDPanel = {
        let panel = HUDPanel(contentRect: NSRect(x: 0, y: 0, width: 380, height: 56),
                             styleMask: [.nonactivatingPanel, .borderless],
                             backing: .buffered, defer: false)
        panel.isFloatingPanel = true
        panel.worksWhenModal = true
        panel.isOpaque = false
        panel.backgroundColor = .clear
        panel.hasShadow = false
        panel.hidesOnDeactivate = false
        panel.canBecomeVisibleWithoutLogin = true
        panel.level = NSWindow.Level(rawValue: Int(CGWindowLevelForKey(.assistiveTechHighWindow)))
        panel.ignoresMouseEvents = true
        panel.isReleasedWhenClosed = false
        panel.collectionBehavior = Self.hudBehavior
        panel.alphaValue = 0
        panel.contentView = NSHostingView(rootView: OverlayView(model: model))
        return panel
    }()

    init() {
        // Pre-warm the panel on launch so WindowServer attaches it to all Spaces from the start.
        DispatchQueue.main.async { [weak self] in
            self?.warmUp()
        }
        spaceObserver = NSWorkspace.shared.notificationCenter.addObserver(
            forName: NSWorkspace.activeSpaceDidChangeNotification,
            object: nil,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor [weak self] in
                guard let self else { return }
                self.panel.collectionBehavior = Self.hudBehavior
                if self.model.phase != .hidden {
                    self.position()
                }
                self.panel.orderFrontRegardless()
            }
        }
    }

    deinit {
        if let spaceObserver {
            NSWorkspace.shared.notificationCenter.removeObserver(spaceObserver)
        }
    }

    private func warmUp() {
        position()
        panel.alphaValue = 0
        panel.orderFrontRegardless()
    }

    func show(_ phase: OverlayModel.Phase) {
        hideWork?.cancel()
        if case .recording = phase, !isRecording { model.resetLevels() }
        model.phase = phase
        position()
        panel.collectionBehavior = Self.hudBehavior
        panel.alphaValue = 1
        panel.orderFrontRegardless()
    }

    func hide() {
        hideWork?.cancel()
        model.phase = .hidden
        // Hide via alphaValue instead of orderOut so WindowServer never detaches the panel
        // from active Full-Screen Spaces.
        panel.alphaValue = 0
    }

    func flash(error message: String) {
        show(.error(message))
        let work = DispatchWorkItem { [weak self] in self?.hide() }
        hideWork = work
        DispatchQueue.main.asyncAfter(deadline: .now() + 3, execute: work)
    }

    private var isRecording: Bool {
        if case .recording = model.phase, panel.alphaValue > 0 { return true }
        return false
    }

    private func position() {
        let mouse = NSEvent.mouseLocation
        let screen = NSScreen.screens.first { NSMouseInRect(mouse, $0.frame, false) } ?? NSScreen.main
        guard let frame = screen?.visibleFrame else { return }
        let size = panel.frame.size
        panel.setFrameOrigin(NSPoint(x: frame.midX - size.width / 2, y: frame.minY + 20))
    }
}

struct OverlayView: View {
    @ObservedObject var model: OverlayModel

    var body: some View {
        Group {
            if model.phase == .hidden {
                Color.clear
            } else {
                HStack(spacing: 10) {
                    switch model.phase {
                    case .hidden:
                        EmptyView()
                    case .recording(let locked):
                        Circle().fill(Color.red).frame(width: 8, height: 8)
                        Waveform(levels: model.levels)
                        if locked {
                            Text("\(AppSettings.shared.hotkey.symbol) selesai · esc batal")
                                .font(.system(size: 11, weight: .medium))
                                .foregroundStyle(.white.opacity(0.65))
                        }
                    case .processing:
                        ProgressView().controlSize(.small)
                        Text("Menulis…")
                            .font(.system(size: 12, weight: .medium))
                            .foregroundStyle(.white)
                    case .error(let message):
                        Image(systemName: "exclamationmark.triangle.fill").foregroundStyle(.yellow)
                        Text(message)
                            .font(.system(size: 12))
                            .foregroundStyle(.white)
                            .lineLimit(2)
                    }
                }
                .padding(.horizontal, 14)
                .frame(height: 36)
                .background(Capsule().fill(Color.black.opacity(0.86)))
                .overlay(Capsule().stroke(Color.white.opacity(0.14), lineWidth: 1))
            }
        }
        .frame(width: 380, height: 56)
        .environment(\.colorScheme, .dark)
        .animation(.easeOut(duration: 0.15), value: model.phase)
    }
}

private struct Waveform: View {
    let levels: [CGFloat]

    var body: some View {
        HStack(alignment: .center, spacing: 2) {
            ForEach(levels.indices, id: \.self) { i in
                Capsule()
                    .fill(Color.white)
                    .frame(width: 2.5, height: max(3, levels[i] * 22))
            }
        }
        .frame(height: 24)
        .animation(.linear(duration: 0.08), value: levels)
    }
}
