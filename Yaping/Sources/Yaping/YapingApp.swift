import AppKit

@main
enum YapingMain {
    @MainActor
    static func main() {
        let args = CommandLine.arguments
        if let i = args.firstIndex(of: "--selftest"), i + 1 < args.count {
            let url = URL(fileURLWithPath: args[i + 1])
            Task.detached {
                await SelfTest.run(url)
                exit(0)
            }
            dispatchMain()
        }

        let app = NSApplication.shared
        let delegate = AppDelegate()
        app.delegate = delegate
        app.setActivationPolicy(.accessory)
        app.run()
    }
}
