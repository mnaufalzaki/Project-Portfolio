import AppKit
import SwiftUI

final class OverlayModel: ObservableObject {
    enum Phase: Equatable {
        case hidden
        case recording(locked: Bool)
        case processing
        case error(String)
    }

    static let barCount = 24

    @Published var phase: Phase = .hidden
    @Published var levels: [CGFloat] = Array(repeating: 0, count: barCount)
    @Published var currentLevel: CGFloat = 0

    func push(_ level: Float) {
        let raw = CGFloat(max(0, min(1, level)))
        // Fast attack, gentle decay so the indicator and bars feel fluid instead of jittery.
        let smoothed = raw > currentLevel
            ? currentLevel * 0.42 + raw * 0.58
            : currentLevel * 0.72 + raw * 0.28
        currentLevel = smoothed

        // Insert from the center outward for a symmetric, living voice wave.
        let mid = Self.barCount / 2
        var next = levels
        for i in 0..<(mid - 1) {
            next[i] = levels[i + 1]
        }
        for i in stride(from: Self.barCount - 1, to: mid, by: -1) {
            next[i] = levels[i - 1]
        }
        next[mid - 1] = smoothed
        next[mid] = smoothed
        levels = next
    }

    func resetLevels() {
        currentLevel = 0
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
        let panel = HUDPanel(contentRect: NSRect(x: 0, y: 0, width: 420, height: 64),
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
        panel.setFrameOrigin(NSPoint(x: frame.midX - size.width / 2, y: frame.minY + 18))
    }
}

struct OverlayView: View {
    @ObservedObject var model: OverlayModel

    var body: some View {
        if model.phase == .hidden {
            EmptyView()
        } else {
            HStack(spacing: 11) {
                switch model.phase {
                case .hidden:
                    EmptyView()
                case .recording(let locked):
                    RecordingDot(level: model.currentLevel)
                    Waveform(levels: model.levels)
                    if locked {
                        Text("\(AppSettings.shared.hotkey.symbol) selesai · esc batal")
                            .font(.system(size: 11, weight: .medium))
                            .foregroundStyle(.white.opacity(0.68))
                    }
                case .processing:
                    ProcessingDots()
                    Text("Menulis…")
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(.white.opacity(0.95))
                case .error(let message):
                    Image(systemName: "exclamationmark.triangle.fill")
                        .font(.system(size: 13))
                        .foregroundStyle(.yellow)
                    Text(message)
                        .font(.system(size: 12, weight: .medium))
                        .foregroundStyle(.white)
                        .lineLimit(2)
                }
            }
            .padding(.horizontal, 16)
            .frame(height: 40)
            .background(
                Capsule()
                    .fill(Color(white: 0.08).opacity(0.9))
                    .shadow(color: Color.black.opacity(0.45), radius: 12, x: 0, y: 4)
            )
            .overlay(
                Capsule()
                    .stroke(
                        LinearGradient(
                            colors: [Color.white.opacity(0.24), Color.white.opacity(0.08)],
                            startPoint: .top,
                            endPoint: .bottom
                        ),
                        lineWidth: 1
                    )
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .environment(\.colorScheme, .dark)
            .animation(.spring(response: 0.24, dampingFraction: 0.8), value: model.phase)
        }
    }
}

private struct RecordingDot: View {
    let level: CGFloat

    var body: some View {
        ZStack {
            Circle()
                .fill(Color.red.opacity(0.32 + Double(level) * 0.28))
                .frame(width: 8 + level * 11, height: 8 + level * 11)
            Circle()
                .fill(Color(red: 1.0, green: 0.27, blue: 0.23))
                .frame(width: 8, height: 8)
                .shadow(color: Color.red.opacity(0.6), radius: 3)
        }
        .frame(width: 18, height: 18)
        .animation(.spring(response: 0.16, dampingFraction: 0.65), value: level)
    }
}

private struct Waveform: View {
    let levels: [CGFloat]

    var body: some View {
        HStack(alignment: .center, spacing: 2.5) {
            ForEach(levels.indices, id: \.self) { i in
                let t = Double(i) / Double(max(1, levels.count - 1))
                // Raised-cosine envelope: center bars dance tall while outer edges taper smoothly.
                let envelope = CGFloat(0.22 + 0.78 * sin(.pi * t))
                let boosted = pow(levels[i], 0.82) * envelope
                let height = max(3.5, 3.5 + boosted * 21.5)
                let intensity = min(1, boosted * 1.45)

                Capsule()
                    .fill(
                        LinearGradient(
                            colors: [
                                Color.white.opacity(0.55 + Double(intensity) * 0.45),
                                Color(red: 0.84, green: 0.92, blue: 1.0).opacity(0.45 + Double(intensity) * 0.5),
                            ],
                            startPoint: .top,
                            endPoint: .bottom
                        )
                    )
                    .frame(width: 2.5, height: height)
            }
        }
        .frame(height: 26)
        .animation(.spring(response: 0.14, dampingFraction: 0.68), value: levels)
    }
}

private struct ProcessingDots: View {
    var body: some View {
        TimelineView(.animation) { context in
            let t = context.date.timeIntervalSinceReferenceDate
            HStack(spacing: 4) {
                ForEach(0..<3, id: \.self) { index in
                    let wave = 0.5 + 0.5 * sin(t * 5.2 - Double(index) * 0.9)
                    Circle()
                        .fill(Color.white)
                        .frame(width: 5, height: 5)
                        .scaleEffect(0.55 + 0.5 * wave)
                        .opacity(0.35 + 0.65 * wave)
                }
            }
        }
    }
}
