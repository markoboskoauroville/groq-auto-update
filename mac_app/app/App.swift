// Queen: Queen herself on the Mac. Since v5 (Phase A, 14.11.2026) this app serves 127.0.0.1:8765
// (core/QueenServer.swift) and starts the Python CAPI/skills backend on 8766.
// Marko, 14.11.2026: "now it is time to convert our Grok AI Studio into a Swift app. Please do that and upgrade it with new
// skills for accessibility". Swift only, no web view (MANTRA_MANIFEST swift-apps.md); compiled only by GitHub (build.yml).
// The window: the house top row (ON OFF · name · TOP PERMISSIONS ✕), Queen's status line, the conversation, one input and
// its one word (SEND, STOP while she answers). Chats sit behind the one word CHATS (simple first).
import SwiftUI
import AppKit
import ApplicationServices

let VERSION = 31
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
    static let accent = Color(red: 0.96, green: 0.45, blue: 0.20)
    static let claude = Color(red: 0.55, green: 0.65, blue: 1.0)
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
        Text(text).foregroundStyle(color).unit()
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
                Text("ON").foregroundStyle(Ink.green).unit().padding(.horizontal, 6)
                Word(text: "OFF", id: "off", color: Ink.grey, help: "Quit Queen: her server on 8765 and her backend on 8766 stop") {
                    // the server and backend stop in applicationWillTerminate, only after Marko confirmed the Quit guard
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
enum QueenTab: String, Equatable {
    case capi
    case autoUpdate = "auto-update"
}

struct StatusLine: View {
    @ObservedObject var q = Queen.shared
    @ObservedObject var cp = Capi.shared
    @Binding var selectedTab: QueenTab
    var body: some View {
        // v20: groups divided by dim pipes; a group is one unbreakable unit and wraps whole; the tabs sit at the right end
        FlowLayout(spacing: 8, rowSpacing: 2) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Circle().fill(q.up ? Ink.green : (q.starting ? Ink.amber : Ink.red)).frame(width: 8, height: 8).alignmentGuide(.firstTextBaseline) { d in d.height / 2 + 4.5 }
                // the one version number: the app's own (release tag vN); a click opens the Latest release (version-visible.md)
                Text("v\(VERSION)")
                    .font(.system(size: 12, weight: .bold, design: .monospaced)).foregroundStyle(Ink.accent).unit()
                    .padding(.horizontal, 4).contentShape(Rectangle())
                    .onTapGesture { StatusLine.openLatest() }
                    .accessibilityElement(children: .ignore).accessibilityLabel("version")
                    .accessibilityIdentifier("version").accessibilityValue("v\(VERSION)")
                    .accessibilityAddTraits(.isButton).accessibilityAction(.default) { StatusLine.openLatest() }
                    .pressHover()
                    .help("Version \(VERSION): click to open the newest version on GitHub")
            }.unit()
            ForEach(Array(statusParts.enumerated()), id: \.offset) { _, p in
                Text(p).font(.system(size: 12, design: .monospaced)).foregroundStyle(Ink.dim).textSelection(.enabled)
                    .pipeGroup()
            }
            if (!q.up || !q.backend) && !q.starting {
                Word(text: "START QUEEN", id: "start-queen", color: Ink.amber, help: "Start Queen's Python backend again (~/.queen/queen-backend on 8766)") {
                    q.startServer()
                }.pipeGroup().flowRight()
            }
            HStack(alignment: .firstTextBaseline, spacing: 0) {
                Word(text: "CAPI", id: "capi", color: selectedTab == .capi ? Ink.claude : Ink.text,
                     help: "CAPI coding chats") {
                    selectedTab = .capi
                    if !cp.active { cp.toggle() }
                }
                Word(text: "AUTO UPDATE", id: "auto-update", color: selectedTab == .autoUpdate ? Ink.claude : Ink.text,
                     help: "Chat with Queen's update pipeline") { selectedTab = .autoUpdate }
            }.unit().flowRight()
        }
        .clipped()
        .font(.system(size: 12, weight: .bold, design: .monospaced))
        .padding(.horizontal, 14).padding(.vertical, 6)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    static func openLatest() {
        if let u = URL(string: "https://github.com/markoboskoauroville/groq_ai_studio/releases/latest") { NSWorkspace.shared.open(u) }
    }

    var statusParts: [String] {
        guard q.up else { return ["Queen \(q.line)".replacingOccurrences(of: " ", with: "\u{00A0}")] }
        var parts = ["Queen", "Python skills", "external CAPI"]
        if !q.backend { parts.append("backend 8766 down") }
        if cp.active { parts.append(cp.providerName) }
        return parts.map { $0.replacingOccurrences(of: " ", with: "\u{00A0}") }
    }
}

// ---------------------------------------------------------------- the conversation
struct Bubble: View {
    let m: Msg
    var body: some View {
        if m.role == "tool" {
            // CAPI: one compact line per tool Claude Code used
            Text("·  " + m.content)
                .font(.system(size: 11, design: .monospaced)).foregroundStyle(Ink.dim)
                .lineLimit(2).truncationMode(.tail)
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(.horizontal, 16).padding(.vertical, 2)
        } else {
            if m.role == "pair" {
                // v26: the end of a MASTER / SLAVE turn: one line with how it ended and the costs
                Text(m.content)
                    .font(.system(size: 12, weight: .bold, design: .monospaced))
                    .foregroundStyle(m.content.hasPrefix("PAIR DONE") ? Ink.green : Ink.amber)
                    .fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 16).padding(.vertical, 8)
                    .accessibilityIdentifier("capi-pair-end")
            } else {
            VStack(alignment: .leading, spacing: 4) {
                Text(m.label.isEmpty ? Bubble.label(m.role) : m.label)
                    .fixedSize(horizontal: false, vertical: true)
                    .font(.system(size: 11, weight: .bold, design: .monospaced))
                    .foregroundStyle(Bubble.color(m.role))
                if m.content.isEmpty {
                    Text("…").font(.system(size: 14)).foregroundStyle(Ink.text)
                } else {
                    MarkdownView(text: m.content).textSelection(.enabled)
                }
                if !Bubble.isMine(m.role) && !m.content.isEmpty {
                    HStack(spacing: 6) {                      // the end of every response: the speaker icon (one component)
                        SpeakerButton(m: m)
                        if m.cost > 0 {
                            Text(String(format: "$%.4f", m.cost)).font(.system(size: 11, design: .monospaced)).foregroundStyle(Ink.dim)
                        }
                        Spacer(minLength: 0)
                    }
                }
            }
            .padding(.horizontal, 16).padding(.vertical, 10)
            .padding(.bottom, Bubble.isMine(m.role) && !m.status.isEmpty ? 12 : 0)
            .frame(maxWidth: .infinity, alignment: .leading)
            .overlay(alignment: .bottomTrailing) {
                if Bubble.isMine(m.role) && !m.status.isEmpty { PromptStatus(m: m).padding(.trailing, 12).padding(.bottom, 4) }
            }
            .background(Bubble.isMine(m.role) ? Ink.panel : Color.clear)
            }
        }
    }

    // CAPI roles are user, assistant, and tool.
    static func isMine(_ r: String) -> Bool { r == "user" || r == "marko" }
    static func label(_ r: String) -> String { isMine(r) ? "YOU" : (r == "claude" ? "CLAUDE" : (r == "master" ? "MASTER" : (r == "slave" ? "SLAVE" : "QUEEN"))) }
    static func color(_ r: String) -> Color {
        isMine(r) ? Ink.dim : (r == "claude" ? Ink.claude : (r == "master" ? Ink.amber : (r == "slave" ? Ink.green : Ink.accent)))
    }

    static func rich(_ s: String) -> AttributedString {
        let opts = AttributedString.MarkdownParsingOptions(interpretedSyntax: .inlineOnlyPreservingWhitespace)
        return (try? AttributedString(markdown: s, options: opts)) ?? AttributedString(s)
    }
}

/// CAPI (v13): the lower right corner of each prompt. Marko: "Confirmation received in the lower right corner next to
/// each prompt ... add Braille spinner while the API is processing". sent -> received ✓ + spinner -> received ✓ | failed.
struct PromptStatus: View {
    let m: Msg
    static let frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    var body: some View {
        Group {
            switch m.status {
            case "sent":
                Text("sent").foregroundStyle(Ink.dim)
            case "received":
                HStack(spacing: 6) {
                    TimelineView(.periodic(from: .now, by: 0.08)) { t in
                        Text(PromptStatus.frames[Int(t.date.timeIntervalSinceReferenceDate / 0.08) % PromptStatus.frames.count])
                            .foregroundStyle(Ink.claude)
                    }
                    Text("received ✓").foregroundStyle(Ink.green)
                }
            case "failed":
                Text("failed").foregroundStyle(Ink.red).help(m.reason.isEmpty ? "failed" : m.reason)
            default:
                Text("received ✓").foregroundStyle(Ink.dim)
            }
        }
        .font(.system(size: 11, weight: .bold, design: .monospaced))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Prompt " + (m.status == "done" ? "received, answered" : m.status) + (m.reason.isEmpty ? "" : ": " + m.reason))
        .accessibilityIdentifier("capi-prompt-status")
    }
}

/// The one scrolling message list: the normal chat, TRIPLE and CAPI all use it (one module).
struct MessageList<Extra: View>: View {
    let messages: [Msg]
    let empty: String
    var notice: String = ""
    var trigger: Int = 0
    @ViewBuilder var extra: () -> Extra
    var body: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 0) {
                    if messages.isEmpty {
                        Text(empty)
                            .font(.system(size: 14)).foregroundStyle(Ink.dim)
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(16)
                    }
                    ForEach(messages) { m in
                        Bubble(m: m)
                        if m.role != "tool" { Hairline() }
                    }
                    extra()
                    if !notice.isEmpty {
                        Text(notice).font(.system(size: 12, design: .monospaced)).foregroundStyle(Ink.red)
                            .fixedSize(horizontal: false, vertical: true).textSelection(.enabled)
                            .padding(.horizontal, 16).padding(.vertical, 8)
                    }
                    Color.clear.frame(height: 1).id("end")
                }
            }
            .onChange(of: messages) { _ in proxy.scrollTo("end", anchor: .bottom) }
            .onChange(of: trigger) { _ in proxy.scrollTo("end", anchor: .bottom) }
        }
    }
}

struct Root: View {
    @State private var selectedTab: QueenTab = .capi
    @ObservedObject var cp = Capi.shared
    @StateObject private var autoUpdate = AutoUpdateChat()
    @AppStorage("ui.capiListWidth") private var capiListW: Double = 330     // v18: the divider's width, remembered
    @AppStorage("ui.capiShowList") private var capiShowList = true         // v22: CHATS hides the whole list pane
    var body: some View {
        VStack(spacing: 0) {
            TopRow()
            Hairline()
            StatusLine(selectedTab: $selectedTab)
            Hairline()
            if selectedTab == .capi {
                CapiHeader(showList: $capiShowList)
                Hairline()
                HStack(spacing: 0) {
                    if capiShowList {
                        CapiRoomList().frame(minWidth: 230, idealWidth: capiListW, maxWidth: capiListW)
                        SplitHandle(width: $capiListW, minW: 230, maxW: 520, reset: 330)
                    }
                    CapiPane()
                }
            } else {
                AutoUpdatePane(chat: autoUpdate)
            }
        }
        .background(Ink.bg)
        .ignoresSafeArea(.container, edges: .top)
        .preferredColorScheme(.dark)
        .modifier(StateKeeper(selectedTab: $selectedTab))
    }
}

/// Persists the screen state (split out of Root: the type checker gives up on one long chain).
struct StateKeeper: ViewModifier {
    @Binding var selectedTab: QueenTab
    @ObservedObject var cp = Capi.shared
    func body(content: Content) -> some View {
        content
            .onAppear { UIState.restore(selectedTab: $selectedTab) }
            .onChange(of: selectedTab) { mode in UIState.saveMode(mode) }
            .onChange(of: cp.convId) { (v: String) in UIState.d.set(v, forKey: "ui.capiConv") }
    }
}

/// The screen as it was left (Marko, 17.11.2026): tab, open conversation / room / chat, side lists. Model and folder are
/// kept per conversation by the server; the window frame by the frame autosave. A conversation that no longer exists
/// (CLOSEd) falls back quietly to the first one.
enum UIState {
    static let d = UserDefaults.standard
    static var restoring = true
    static func saveMode(_ mode: QueenTab) {
        if restoring { return }
        d.set(mode.rawValue, forKey: "ui.mode")
    }
    static func restore(selectedTab: Binding<QueenTab>) {
        guard restoring else { return }
        let mode = d.string(forKey: "ui.mode") ?? QueenTab.capi.rawValue
        selectedTab.wrappedValue = mode == QueenTab.autoUpdate.rawValue ? .autoUpdate : .capi
        Task { @MainActor in
            if selectedTab.wrappedValue == .capi, !Capi.shared.active {
                Capi.shared.preferred = d.string(forKey: "ui.capiConv") ?? ""
                Capi.shared.toggle()
            }
            restoring = false
        }
    }
}

// ---------------------------------------------------------------- the app
final class Delegate: NSObject, NSApplicationDelegate {
    /// Quit guard (Marko, 19.11.2026): every quit (Cmd-Q, Dock, menu, OFF) asks first. Code that quits Queen on purpose and
    /// unattended (the updater's swap, which waits for this process to end) sets this before NSApp.terminate, so nothing hangs.
    static var quitWithoutAsking = false

    func applicationShouldTerminate(_ sender: NSApplication) -> NSApplication.TerminateReply {
        if Delegate.quitWithoutAsking { return .terminateNow }
        // Log out, restart and shut down arrive with a quit-reason attribute ('why?'): never block the system.
        if NSAppleEventManager.shared().currentAppleEvent?.attributeDescriptor(forKeyword: 0x7768793F) != nil { return .terminateNow }
        NSApp.activate(ignoringOtherApps: true)
        let a = NSAlert()
        a.messageText = "Are you sure you want to quit?"
        a.informativeText = "Queen's server (8765) and her backend (8766) stop with her."
        a.addButton(withTitle: "Quit")
        a.addButton(withTitle: "Cancel")
        return a.runModal() == .alertFirstButtonReturn ? .terminateNow : .terminateCancel
    }

    /// Runs only once the quit is confirmed (never when Cancel was pressed): her server and the backend this app started stop.
    func applicationWillTerminate(_ n: Notification) { Queen.shared.stopIfOurs() }

    func applicationDidFinishLaunching(_ n: Notification) {
        NSApp.appearance = NSAppearance(named: .darkAqua)
        QueenHost.shared.start(appVersion: VERSION)     // Phase A: Queen's server is this app (8765), Python is its backend (8766)
        Queen.shared.start()
        DispatchQueue.main.async {
            for w in NSApp.windows where w.title.hasPrefix("Queen") { w.setFrameAutosaveName("QueenMain") }
        }
        Updater.checkAtStart()
    }
    func applicationShouldTerminateAfterLastWindowClosed(_ s: NSApplication) -> Bool { false }
}

@main
struct QueenApp: App {
    @NSApplicationDelegateAdaptor(Delegate.self) var delegate
    var body: some Scene {
        Window(APP_NAME, id: "main") {
            Root().frame(minWidth: 560, minHeight: 420)
        }
        .windowStyle(.hiddenTitleBar)
        .defaultSize(width: 920, height: 700)
    }
}
