import Cocoa
import WebKit

let args = CommandLine.arguments
let url = URL(string: args.count > 1 ? args[1] : "https://www.youtube.com")!
let app = NSApplication.shared
app.setActivationPolicy(.accessory)
let screen = NSScreen.main!.visibleFrame
let w: CGFloat = 360, h: CGFloat = min(560, screen.height - 140)
let frame = NSRect(x: screen.minX + 16, y: screen.minY + (screen.height - h) / 2, width: w, height: h)
let win = NSPanel(contentRect: frame, styleMask: [.titled, .closable, .resizable, .nonactivatingPanel, .utilityWindow], backing: .buffered, defer: false)
win.title = "Live chat"
win.level = .floating
win.collectionBehavior = [.canJoinAllSpaces, .fullScreenAuxiliary, .stationary]
win.hidesOnDeactivate = false
win.isFloatingPanel = true
win.alphaValue = 0.96
let cfg = WKWebViewConfiguration()
let web = WKWebView(frame: win.contentView!.bounds, configuration: cfg)
web.autoresizingMask = [.width, .height]
web.customUserAgent = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.0 Safari/605.1.15"
web.load(URLRequest(url: url))
win.contentView!.addSubview(web)
win.setFrame(frame, display: true)
win.contentMinSize = NSSize(width: 280, height: 300)
win.orderFrontRegardless()
for t in [0.5, 1.5, 3.0, 6.0] {
    DispatchQueue.main.asyncAfter(deadline: .now() + t) { win.setFrame(frame, display: true) }
}
class D: NSObject, NSWindowDelegate { func windowWillClose(_ n: Notification) { NSApp.terminate(nil) } }
let d = D(); win.delegate = d
app.run()
