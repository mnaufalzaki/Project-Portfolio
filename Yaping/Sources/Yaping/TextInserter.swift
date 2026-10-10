import AppKit

/// Types text into the focused app by pasting it, then puts the old clipboard back.
enum TextInserter {
    /// Returns false when macOS blocks synthetic keystrokes; the text is then left on the clipboard.
    @discardableResult
    static func insert(_ text: String, restoreClipboard: Bool, forceLeadingSpace: Bool = false) -> Bool {
        let pb = NSPasteboard.general
        guard AXIsProcessTrusted() else {
            pb.clearContents()
            pb.setString(text, forType: .string)
            return false
        }
        let saved = restoreClipboard ? snapshot(pb) : nil
        let startsWithWord = text.first.map { !$0.isPunctuation && !$0.isWhitespace } ?? false
        let addSpace = forceLeadingSpace ? startsWithWord : needsLeadingSpace(before: text)
        let text = addSpace ? " " + text : text

        pb.clearContents()
        pb.setString(text, forType: .string)
        // Tells clipboard managers to skip this entry.
        pb.setData(Data(), forType: NSPasteboard.PasteboardType("org.nspasteboard.TransientType"))
        let change = pb.changeCount

        pressCommandV()

        guard let saved else { return true }
        DispatchQueue.main.asyncAfter(deadline: .now() + 0.6) {
            guard pb.changeCount == change else { return }
            pb.clearContents()
            if !saved.isEmpty { pb.writeObjects(saved) }
        }
        return true
    }

    /// Asks the focused text field (via Accessibility) for the character before the cursor,
    /// so back-to-back dictations don't run together ("bagaimana?Tapi"). Apps that don't expose it get no space.
    private static func needsLeadingSpace(before text: String) -> Bool {
        guard let first = text.first, !first.isPunctuation, !first.isWhitespace else { return false }
        let system = AXUIElementCreateSystemWide()
        var focusedRef: AnyObject?
        guard AXUIElementCopyAttributeValue(system, kAXFocusedUIElementAttribute as CFString, &focusedRef) == .success,
              let focusedRef, CFGetTypeID(focusedRef) == AXUIElementGetTypeID() else { return false }
        let focused = focusedRef as! AXUIElement

        var rangeRef: AnyObject?
        guard AXUIElementCopyAttributeValue(focused, kAXSelectedTextRangeAttribute as CFString, &rangeRef) == .success,
              let rangeRef, CFGetTypeID(rangeRef) == AXValueGetTypeID() else { return false }
        var selection = CFRange()
        guard AXValueGetValue(rangeRef as! AXValue, .cfRange, &selection), selection.location > 0 else { return false }

        var previous = CFRange(location: selection.location - 1, length: 1)
        guard let previousValue = AXValueCreate(.cfRange, &previous) else { return false }
        var charRef: AnyObject?
        guard AXUIElementCopyParameterizedAttributeValue(focused, kAXStringForRangeParameterizedAttribute as CFString,
                                                         previousValue, &charRef) == .success,
              let char = (charRef as? String)?.last else { return false }
        return !char.isWhitespace
    }

    private static func snapshot(_ pb: NSPasteboard) -> [NSPasteboardItem] {
        (pb.pasteboardItems ?? []).map { item in
            let copy = NSPasteboardItem()
            for type in item.types {
                if let data = item.data(forType: type) { copy.setData(data, forType: type) }
            }
            return copy
        }
    }

    private static func pressCommandV() {
        let source = CGEventSource(stateID: .combinedSessionState)
        let vKey: CGKeyCode = 9
        let down = CGEvent(keyboardEventSource: source, virtualKey: vKey, keyDown: true)
        let up = CGEvent(keyboardEventSource: source, virtualKey: vKey, keyDown: false)
        down?.flags = .maskCommand
        up?.flags = .maskCommand
        down?.post(tap: .cghidEventTap)
        up?.post(tap: .cghidEventTap)
    }
}
