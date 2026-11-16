// Queen: Queen herself on the Mac. Since v5 (Phase A, 14.11.2026) this app serves 127.0.0.1:8765
// (core/QueenServer.swift) and starts the Python server as its internal backend on 8766 for the routes not moved yet.
// Marko, 14.11.2026: "now it is time to convert our Grok AI Studio into a Swift app. Please do that and upgrade it with new
// skills for accessibility". Swift only, no web view (MANTRA_MANIFEST swift-apps.md); compiled only by GitHub (build.yml).
// The window: the house top row (ON OFF · name · TOP PERMISSIONS ✕), Queen's status line, the conversation, one input and
// its one word (SEND, STOP while she answers). Chats sit behind the one word CHATS (simple first).
import SwiftUI
import AppKit
import ApplicationServices

let VERSION = 6
let APP_NAME = "Queen"

enum Ink {
    static let bg = Color(red: 0.07, green: 0.07, blue: 0.08)
    static let panel = Color(red: 0.11, green: 0.11, blue: 0.12)
    static let text = Color(white: 0.92)
    static let dim = Color(white: 0.55)
    static let grey = Color(white: 0.45)
    static let line = Color(white: 0.22)
    static let green = Color(red: 0.30, green: 0.85, blue: 0.45)
    static let amber = Color(red: 1.0, green: 0.70, blue: 0.15)
    static let red = Color(red: 1.0, green: 0.35, blue: 0.30)
    static let accent = Color(red: 0.96, green: 0.45, blue: 0.20)   // Groq orange
}

// every word that acts is an Accessibility button with a label and an identifier (swift-apps.md, 31.10.2026)
extension View {
    func axButton(_ label: String, id: String, value: String? = nil, _ action: @escaping () -> Void) -> some View {
        accessibilityElement(children: .ignore)
            .accessibilityLabel(label)
            .accessibilityIdentifier(id)
            .accessibilityValue(value ?? "")
            .accessibilityAddTraits(.isButton)
            .accessibilityAction(.default, action)
    }
}

// every pressable control highlights on hover (workflow-interface.md, 10.11.2026)
struct PressHover: ViewModifier {
    @Environment(\.isEnabled) private var enabled
    @State private var hot = false
    func body(content: Content) -> some View {
        let on = hot && enabled
        content
            .background(RoundedRectangle(cornerRadius: 5).fill(Color.white.opacity(on ? 0.12 : 0)))
            .overlay(RoundedRectangle(cornerRadius: 5).stroke(Color.white.opacity(on ? 0.55 : 0), lineWidth: 1))
            .animation(.easeOut(duration: 0.12), value: on)
            .onHover { inside in
                hot = inside
                if enabled { if inside { NSCursor.pointingHand.push() } else { NSCursor.pop() } }
            }
    }
}
extension View { func pressHover() -> some View { modifier(PressHover()) } }

/// A word that acts: tap + Accessibility button + hover.
struct Word: View {
    let text: String
    let id: String
    var color: Color = Ink.text
    var help: String = ""
    let action: () -> Void
    var body: some View {
        Text(text).foregroundStyle(color)
            .padding(.horizontal, 6).padding(.vertical, 4)
            .contentShape(Rectangle())
            .onTapGesture { action() }
            .axButton(text.capitalized, id: id) { action() }
            .pressHover()
            .help(help)
    }
}

struct Hairline: View {
    var body: some View { Rectangle().fill(Ink.line).frame(height: 1) }
}

// ---------------------------------------------------------------- permissions
// PERMISSIONS at the top right while Accessibility is missing (swift-apps.md). Queen reads apps through Accessibility
// (axread inside this app); when this app starts Queen, the permission belongs to this app.
final class Permissions: ObservableObject {
    static let shared = Permissions()
    @Published private(set) var missing: [String] = []
    private init() {
        missing = Permissions.check()
        Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in
            let m = Permissions.check()
            if m != self?.missing { self?.missing = m }
        }
    }
    static func check() -> [String] { AXIsProcessTrusted() ? [] : ["Accessibility"] }
    static func openMissing() {
        // the system's own request first, so the app is in the list and only needs switching on
        let opts = [kAXTrustedCheckOptionPrompt.takeUnretainedValue() as String: true] as CFDictionary
        _ = AXIsProcessTrustedWithOptions(opts)
        if let u = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Accessibility") {
            NSWorkspace.shared.open(u)
        }
    }
}

// ---------------------------------------------------------------- the top row
struct TopRow: View {
    @ObservedObject var perms = Permissions.shared
    @AppStorage("onTop") private var onTop = false
    var body: some View {
        ZStack {
            (Text("Queen").fontWeight(.bold) + Text(""))
                .font(.system(size: 15)).foregroundStyle(Ink.text)
                .lineLimit(1)
            HStack(spacing: 6) {
                Spacer().frame(width: 64)                   // the traffic lights
                Text("ON").foregroundStyle(Ink.green).padding(.horizontal, 6)
                Word(text: "OFF", id: "off", color: Ink.grey, help: "Quit Queen: her server on 8765 and her backend on 8766 stop") {
                    Queen.shared.stopIfOurs()
                    DispatchQueue.main.async { NSApp.terminate(nil) }
                }
                Spacer()
                Word(text: "TOP", id: "top", color: onTop ? Ink.green : Ink.grey,
                     help: "Always on top: green, the window stays above every other window") {
                    onTop.toggle(); TopRow.float(onTop)
                }
                if !perms.missing.isEmpty {
                    Word(text: "PERMISSIONS", id: "permissions", color: Ink.amber,
                         help: "Accessibility is not allowed yet: a click opens its page in System Settings; switch Queen on there") {
                        Permissions.openMissing()
                    }
                }
                Image(systemName: "xmark").font(.system(size: 12, weight: .semibold)).foregroundStyle(Ink.grey)
                    .frame(width: 28, height: 28).contentShape(Rectangle())
                    .onTapGesture { NSApp.keyWindow?.performClose(nil) }
                    .axButton("Close window", id: "close") { (NSApp.keyWindow ?? NSApp.windows.first { $0.isVisible })?.performClose(nil) }
                    .pressHover()
            }
            .font(.system(size: 12, weight: .bold, design: .monospaced))
        }
        .frame(height: 32)
        .onAppear { DispatchQueue.main.async { TopRow.float(onTop) } }
    }

    static func float(_ on: Bool) {
        for w in NSApp.windows where w.title.hasPrefix("Queen") || w.identifier?.rawValue == "main" {
            w.level = on ? .floating : .normal
        }
    }
}

// ---------------------------------------------------------------- the status line
struct StatusLine: View {
    @ObservedObject var q = Queen.shared
    @Binding var showChats: Bool
    var body: some View {
        HStack(spacing: 10) {
            Circle().fill(q.up ? Ink.green : (q.starting ? Ink.amber : Ink.red)).frame(width: 8, height: 8)
            Text(statusText)
                .font(.system(size: 12, design: .monospaced)).foregroundStyle(Ink.dim)
                .fixedSize(horizontal: false, vertical: true)
                .textSelection(.enabled)
            Spacer(minLength: 8)
            if (!q.up || !q.backend) && !q.starting {
                Word(text: "START QUEEN", id: "start-queen", color: Ink.amber, help: "Start Queen's backend again (~/.groq/qwen on 8766)") {
                    q.startServer()
                }
            }
            Word(text: "CHATS", id: "chats", color: showChats ? Ink.accent : Ink.text, help: "Your saved chats with Queen") {
                showChats.toggle()
                if showChats { Task { await q.loadChats() } }
            }
            Word(text: "NEW CHAT", id: "new-chat", help: "A clean chat") { q.newChat() }
        }
        .font(.system(size: 12, weight: .bold, design: .monospaced))
        .padding(.horizontal, 14).padding(.vertical, 6)
    }

    var statusText: String {
        guard q.up else { return "Queen \(q.line)" }
        var parts = ["Queen v\(q.version)"]
        if !q.model.isEmpty { parts.append(q.model) }
        parts.append("keys \(q.keys)" + (q.cooling > 0 ? " (\(q.cooling) cooling)" : ""))
        parts.append(String(format: "spent $%.4f", q.spent))
        if !q.backend { parts.append("backend 8766 down") }
        return parts.joined(separator: "  ·  ")
    }
}

// ---------------------------------------------------------------- chats
struct ChatList: View {
    @ObservedObject var q = Queen.shared
    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 0) {
                ForEach(q.chats) { c in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(c.title).font(.system(size: 13, weight: c.id == q.chatId ? .bold : .regular))
                            .foregroundStyle(c.id == q.chatId ? Ink.accent : Ink.text)
                            .fixedSize(horizontal: false, vertical: true)
                        Text("\(c.count) messages  ·  \(String(c.updated.prefix(16)).replacingOccurrences(of: "T", with: " "))")
                            .font(.system(size: 11, design: .monospaced)).foregroundStyle(Ink.dim)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 12).padding(.vertical, 8)
                    .contentShape(Rectangle())
                    .onTapGesture { Task { await q.open(c.id) } }
                    .axButton("Chat " + c.title, id: "chat-" + c.id) { Task { await q.open(c.id) } }
                    .pressHover()
                    Hairline()
                }
            }
        }
        .background(Ink.panel)
    }
}

// ---------------------------------------------------------------- the conversation
struct Bubble: View {
    let m: Msg
    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(m.role == "user" ? "YOU" : "QUEEN")
                .font(.system(size: 11, weight: .bold, design: .monospaced))
                .foregroundStyle(m.role == "user" ? Ink.dim : Ink.accent)
            Text(Bubble.rich(m.content.isEmpty ? "…" : m.content))
                .font(.system(size: 14))
                .foregroundStyle(Ink.text)
                .textSelection(.enabled)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
        .background(m.role == "user" ? Ink.panel : Color.clear)
    }

    static func rich(_ s: String) -> AttributedString {
        let opts = AttributedString.MarkdownParsingOptions(interpretedSyntax: .inlineOnlyPreservingWhitespace)
        return (try? AttributedString(markdown: s, options: opts)) ?? AttributedString(s)
    }
}

struct Conversation: View {
    @ObservedObject var q = Queen.shared
    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 0) {
                    if q.messages.isEmpty {
                        Text("Ask Queen anything. She also reads apps through Accessibility: try \"check my last 5 WhatsApp messages\".")
                            .font(.system(size: 14)).foregroundStyle(Ink.dim)
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(16)
                    }
                    ForEach(q.messages) { m in
                        Bubble(m: m)
                        Hairline()
                    }
                    Color.clear.frame(height: 1).id("end")
                }
            }
            .onChange(of: q.messages) { _ in
                proxy.scrollTo("end", anchor: .bottom)
            }
        }
    }
}

struct InputRow: View {
    @ObservedObject var q = Queen.shared
    @State private var text = ""
    @FocusState private var focused: Bool
    var body: some View {
        HStack(alignment: .bottom, spacing: 10) {
            TextField("Write to Queen", text: $text, axis: .vertical)
                .textFieldStyle(.plain)
                .font(.system(size: 14))
                .foregroundStyle(Ink.text)
                .lineLimit(1...8)
                .focused($focused)
                .onSubmit { go() }
                .padding(10)
                .background(RoundedRectangle(cornerRadius: 6).fill(Ink.panel))
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(Ink.line, lineWidth: 1))
                .accessibilityIdentifier("prompt")
            Word(text: q.busy ? "STOP" : "SEND", id: q.busy ? "stop" : "send",
                 color: q.busy ? Ink.amber : (q.up ? Ink.accent : Ink.grey),
                 help: q.busy ? "Stop her answer" : "Send to Queen (Return)") {
                if q.busy { q.stop() } else { go() }
            }
            .font(.system(size: 13, weight: .bold, design: .monospaced))
        }
        .padding(12)
        .onAppear { focused = true }
    }

    func go() {
        let t = text
        guard !t.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty, !q.busy else { return }
        text = ""
        q.send(t)
    }
}

struct Root: View {
    @State private var showChats = false
    var body: some View {
        VStack(spacing: 0) {
            TopRow()
            Hairline()
            StatusLine(showChats: $showChats)
            Hairline()
            HStack(spacing: 0) {
                if showChats {
                    ChatList().frame(width: 240)
                    Rectangle().fill(Ink.line).frame(width: 1)
                }
                Conversation()
            }
            Hairline()
            InputRow()
        }
        .background(Ink.bg)
        .ignoresSafeArea(.container, edges: .top)
        .preferredColorScheme(.dark)
    }
}

// ---------------------------------------------------------------- the app
final class Delegate: NSObject, NSApplicationDelegate {
    func applicationDidFinishLaunching(_ n: Notification) {
        NSApp.appearance = NSAppearance(named: .darkAqua)
        QueenHost.shared.start(appVersion: VERSION)     // Phase A: Queen's server is this app (8765), Python is its backend (8766)
        Queen.shared.start()
        DispatchQueue.main.async {
            for w in NSApp.windows where w.title.hasPrefix("Queen") { w.setFrameAutosaveName("GroqAIStudioMain") }
        }
        Updater.checkAtStart()
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool { false }
}

@main
struct GroqAIStudioApp: App {
    @NSApplicationDelegateAdaptor(Delegate.self) var delegate
    var body: some Scene {
        Window(APP_NAME, id: "main") {
            Root().frame(minWidth: 560, minHeight: 420)
        }
        .windowStyle(.hiddenTitleBar)
        .defaultSize(width: 920, height: 700)
    }
}
