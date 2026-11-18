// Capi.swift: the CAPI tab (17.11.2026). Marko: "can queen be used as capi ... add capi tab to queen software so i can have
// nicer ui". A chat with Claude Code on the $100 API credit: the server (qwen_app/capi_chat.py, /api/capi/*) runs exactly
// what `capi` runs (headless claude -p, one session per room, working folder, model) and streams the events here.
// One module: the list, bubbles, Markdown and speaker are the shared ones (MessageList, Bubble, MarkdownView, SpeakerButton).
import SwiftUI
import AppKit
import Foundation

struct ProviderItem: Identifiable, Equatable {
    let id: String
    let name: String
}

struct FolderItem: Identifiable, Equatable {
    var id: String { path }
    let name: String
    let path: String
}

/// One stored CAPI conversation as the list shows it (v12: rooms became conversations, each its own background process).
struct ConvMeta: Identifiable, Equatable {
    let id: String
    let title: String
    let count: Int
    let running: Bool
    let busy: Bool
    let error: String
}

final class Capi: ObservableObject {
    static let shared = Capi()

    @Published var active = false
    @Published var convId = ""
    @Published var title = ""
    @Published var messages: [Msg] = []          // role: marko | claude | tool
    @Published var convs: [ConvMeta] = []
    @Published var folders: [FolderItem] = []
    @Published var model = "claude-sonnet-5-5"
    @Published var cwd = ""
    @Published var total = 0.0
    @Published var left: Double? = nil
    @Published var busy = false                  // the conversation on screen is answering
    @Published var running = false              // the conversation on screen has its process
    var preferred = ""                           // the conversation left open last time (restored at start)
    @Published var notice = ""
    @Published var keyNote = ""                  // "API key loaded (…abcd)" after the gear
    @Published var provider = "anthropic"        // v17: the radio at the top (anthropic | oxyy), kept by the server
    @Published var providerName = "Anthropic"
    @Published var providers: [ProviderItem] = [ProviderItem(id: "anthropic", name: "Anthropic"), ProviderItem(id: "oxyy", name: "Oxyy")]
    @Published var creditNote = ""
    private var poller: Task<Void, Never>?
    private var shownSig = ""                    // what is on screen: count + last text, so a poll redraws only on change
    private var busyIds: Set<String> = []

    var creditText: String { left.map { String(format: "\(providerName) ($%.2f left)", $0) } ?? "\(providerName) ($ ?)" }
    var folderName: String { (cwd as NSString).lastPathComponent }

    @MainActor
    func toggle() {
        active.toggle()
        if active {
            Triple.shared.active = false
            Task { await begin() }
        }
    }

    @MainActor
    func begin() async {
        await loadCredit()
        if folders.isEmpty, let j = await Queen.shared.json("/api/capi/folders"), let l = j["folders"] as? [[String: Any]] {
            folders = l.compactMap { f in
                guard let n = f["name"] as? String, let p = f["path"] as? String else { return nil }
                return FolderItem(name: n, path: p)
            }
        }
        startPolling()
        if !convId.isEmpty { return }
        await loadConvs()
        if !preferred.isEmpty, convs.contains(where: { $0.id == preferred }) { let p = preferred; preferred = ""; await open(p); return }
        preferred = ""
        if let first = convs.first { await open(first.id) } else { await newConversation() }
    }

    /// While the tab is open: the list (running / answering) and the conversation on screen follow the server, so
    /// answers of every conversation land in their own files and show when you switch to them.
    @MainActor
    private func startPolling() {
        if poller != nil { return }
        poller = Task { @MainActor in
            while self.active && !Task.isCancelled {
                await self.loadConvs()
                if !self.convId.isEmpty { await self.reload() }
                try? await Task.sleep(nanoseconds: 1_200_000_000)
            }
            self.poller = nil
        }
    }

    @MainActor
    func loadCredit() async {
        if let j = await Queen.shared.json("/api/capi/credit") { applyCredit(j) }
    }

    @MainActor
    private func applyCredit(_ j: [String: Any]) {
        left = j["left"] as? Double
        provider = (j["provider"] as? String) ?? provider
        providerName = (j["name"] as? String) ?? providerName
        creditNote = (j["note"] as? String) ?? ""
        if let l = j["providers"] as? [[String: Any]] {
            let p = l.compactMap { x -> ProviderItem? in
                guard let i = x["id"] as? String, let n = x["name"] as? String else { return nil }
                return ProviderItem(id: i, name: n)
            }
            if !p.isEmpty { providers = p }
        }
    }

    /// The radio: the server remembers it; new prompts go to that provider (a running chat restarts on it by itself).
    @MainActor
    func setProvider(_ id: String) {
        guard id != provider else { return }
        provider = id
        keyNote = ""
        Task { @MainActor in
            if let j = await Queen.shared.json("/api/capi/provider", body: ["provider": id]) { self.applyCredit(j) }
        }
    }

    /// Oxyy has no balance endpoint: the credit starts from the amount Marko types, then counts down.
    @MainActor
    func askStartBalance() {
        let a = NSAlert()
        a.messageText = "\(providerName): your balance in dollars"
        a.informativeText = creditNote
        let f = NSTextField(frame: NSRect(x: 0, y: 0, width: 160, height: 24))
        f.placeholderString = "5.00"
        a.accessoryView = f
        a.addButton(withTitle: "Set")
        a.addButton(withTitle: "Cancel")
        guard a.runModal() == .alertFirstButtonReturn else { return }
        let v = f.stringValue.replacingOccurrences(of: ",", with: ".").trimmingCharacters(in: .whitespaces)
        guard let usd = Double(v) else { return }
        Task { @MainActor in
            if let j = await Queen.shared.json("/api/capi/oxyy_balance", body: ["usd": usd]) { self.applyCredit(j) }
        }
    }

    @MainActor
    func loadConvs() async {
        guard let j = await Queen.shared.json("/api/capi/list"), let list = j["rooms"] as? [[String: Any]] else { return }
        let l: [ConvMeta] = list.compactMap { r in
            guard let id = r["id"] as? String else { return nil }
            return ConvMeta(id: id, title: (r["title"] as? String) ?? "CAPI chat", count: (r["count"] as? Int) ?? 0,
                            running: (r["running"] as? Bool) ?? false, busy: (r["busy"] as? Bool) ?? false,
                            error: (r["error"] as? String) ?? "")
        }
        let nowBusy = Set(l.filter { $0.busy }.map { $0.id })
        if !busyIds.subtracting(nowBusy).isEmpty { await loadCredit() }     // an answer finished somewhere: the credit moved
        busyIds = nowBusy
        if l != convs { convs = l }
    }

    @MainActor
    private func apply(_ j: [String: Any], force: Bool = false) {
        guard let room = j["room"] as? [String: Any] else { return }
        let ms = (room["messages"] as? [[String: Any]]) ?? []
        let id = (room["id"] as? String) ?? convId
        let sig = id + "|\(ms.count)|" + (((ms.last?["text"] as? String) ?? "").count.description)
            + "|" + (((ms.last?["cost"] as? Double) ?? 0).description)
            + "|" + ms.compactMap { $0["status"] as? String }.joined(separator: ",")
        convId = id
        title = (room["title"] as? String) ?? "CAPI chat"
        model = (room["model"] as? String) ?? model
        cwd = (room["cwd"] as? String) ?? cwd
        total = (room["total"] as? Double) ?? 0
        busy = (j["busy"] as? Bool) ?? false
        running = (j["running"] as? Bool) ?? false
        let e = (j["error"] as? String) ?? ""
        notice = e.isEmpty ? "" : (e == "stopped" ? "Stopped." : "ERROR: " + e)
        if force || sig != shownSig {
            shownSig = sig
            messages = ms.compactMap { m in
                guard let r = m["role"] as? String else { return nil }
                return Msg(role: r, content: (m["text"] as? String) ?? "", cost: (m["cost"] as? Double) ?? 0,
                           status: (m["status"] as? String) ?? "", reason: (m["reason"] as? String) ?? "")
            }
        }
    }

    /// Switch the view to another conversation: never waits for, stops or blocks the one that is answering.
    @MainActor
    func open(_ id: String) async {
        guard let j = await Queen.shared.json("/api/capi/get?id=" + id) else { return }
        apply(j, force: true)
    }

    @MainActor
    private func reload() async {
        let id = convId
        guard let j = await Queen.shared.json("/api/capi/get?id=" + id), id == convId else { return }
        apply(j)
    }

    @MainActor
    func newConversation() async {
        let body: [String: Any] = ["cwd": cwd, "model": model]
        guard let j = await Queen.shared.json("/api/capi/new", body: body) else { return }
        apply(j, force: true)
        notice = ""
        await loadConvs()
    }

    @MainActor
    func setModel(_ m: String) { model = m; saveSettings() }

    @MainActor
    func setFolder(_ p: String) { cwd = p; saveSettings() }

    @MainActor
    private func saveSettings() {
        let body: [String: Any] = ["id": convId, "model": model, "cwd": cwd]
        Task { @MainActor in
            guard let j = await Queen.shared.json("/api/capi/settings", body: body) else { return }
            apply(j, force: true)
            if let n = j["notice"] as? String, !n.isEmpty { notice = n }
        }
    }

    /// Send: the server writes it to the conversation's own process (started if it was not); the answer lands in its file.
    @MainActor
    func send(_ text: String) {
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !busy, !convId.isEmpty, !t.isEmpty else { return }
        messages.append(Msg(role: "marko", content: t, status: "sent"))
        busy = true
        notice = ""
        let id = convId
        Task { @MainActor in
            let j = await Queen.shared.json("/api/capi/send", body: ["id": id, "text": t], timeout: 60)
            if let e = j?["error"] as? String, !e.isEmpty, id == self.convId { self.notice = "ERROR: " + e }
            await self.loadConvs()
            if id == self.convId { await self.reload() }
        }
    }

    /// STOP under the input: stops the conversation on screen (its process; the history stays).
    @MainActor
    func stop() { stopConv(convId) }

    @MainActor
    func startConv(_ id: String) {
        Task { @MainActor in
            _ = await Queen.shared.json("/api/capi/start", body: ["id": id], timeout: 30)
            await self.loadConvs()
            if id == self.convId { await self.reload() }
        }
    }

    @MainActor
    func stopConv(_ id: String) {
        Task { @MainActor in
            _ = await Queen.shared.json("/api/capi/stop", body: ["id": id], timeout: 20)
            await self.loadConvs()
            if id == self.convId { await self.reload() }
        }
    }

    /// The gear: a plain file picker; the server takes the sk-ant- key out of the file by shape (the key never comes here).
    @MainActor
    func pickKeyFile() {
        let p = NSOpenPanel()
        let pid = provider
        p.title = "The file with your \(providerName) API key"
        p.prompt = "Use this file"
        p.canChooseFiles = true
        p.canChooseDirectories = false
        p.allowsMultipleSelection = false
        p.directoryURL = URL(fileURLWithPath: NSHomeDirectory() + "/Downloads/API")
        guard p.runModal() == .OK, let url = p.url else { return }
        Task { @MainActor in
            guard let j = await Queen.shared.json("/api/capi/key", body: ["path": url.path, "provider": pid]) else {
                self.keyNote = "Queen did not answer"
                return
            }
            if (j["ok"] as? Bool) == true, let l = j["last4"] as? String {
                self.keyNote = "API key loaded (…\(l))"
                await self.loadCredit()
            } else {
                self.keyNote = (j["error"] as? String) ?? "No \(self.providerName) API key in that file."
            }
        }
    }

    /// RENAME: the name goes to the server (kept in the chat's file); the list order is by creation, so nothing moves.
    @MainActor
    func rename(_ id: String, to name: String) async {
        let n = name.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !n.isEmpty else { return }
        _ = await Queen.shared.json("/api/capi/rename", body: ["id": id, "title": n])
        if id == convId { title = n }
        await loadConvs()
    }

    /// AUTOMATIC NAME: one Haiku call on the chosen provider; only suggests, Marko saves. -> (title, cost, error)
    @MainActor
    func autoName(_ id: String) async -> (String, Double, String) {
        guard let j = await Queen.shared.json("/api/capi/autoname", body: ["id": id], timeout: 60) else { return ("", 0, "Queen did not answer") }
        await loadCredit()
        return ((j["title"] as? String) ?? "", (j["cost"] as? Double) ?? 0, (j["error"] as? String) ?? "")
    }

    /// CLOSE deletes the conversation and its history: one confirmation first.
    @MainActor
    func closeConv(_ c: ConvMeta) {
        let a = NSAlert()
        a.messageText = "Close \"\(c.title)\"?"
        a.informativeText = "Its process stops and its whole history is deleted. This cannot be undone."
        a.addButton(withTitle: "Close")
        a.addButton(withTitle: "Cancel")
        a.alertStyle = .warning
        guard a.runModal() == .alertFirstButtonReturn else { return }
        Task { @MainActor in
            _ = await Queen.shared.json("/api/capi/close", body: ["id": c.id], timeout: 20)
            await self.loadConvs()
            if c.id == self.convId {
                self.convId = ""
                if let next = self.convs.first { await self.open(next.id) } else { await self.newConversation() }
            }
        }
    }
}

// ---------------------------------------------------------------- the window parts
/// Top of the tab: the provider radios, the ONE credit number, the working folder, the chats.
struct CapiHeader: View {
    @ObservedObject var c = Capi.shared
    var body: some View {
        // v20: groups divided by dim pipes, each group one unbreakable unit; whole groups wrap when narrow; NEW CHAT at the right end.
        FlowLayout(spacing: 8, rowSpacing: 0) {
            HStack(spacing: 4) {
                Text("PROVIDER").foregroundStyle(Ink.dim).unit().padding(.horizontal, 6)
                ForEach(c.providers) { p in
                    Word(text: (c.provider == p.id ? "◉ " : "○ ") + p.name.uppercased(), id: "capi-provider-" + p.id,
                         color: c.provider == p.id ? Ink.accent : Ink.text,
                         help: "Use \(p.name) for the next prompts") { c.setProvider(p.id) }
                }
            }.unit().padding(.vertical, 2)
            HStack(spacing: 4) {
                Text(c.creditText.replacingOccurrences(of: " ", with: "\u{00A0}")).foregroundStyle(Ink.red).unit()
                    .padding(.leading, 6)
                    .accessibilityIdentifier("capi-credit")
                    .onTapGesture { if c.provider == "oxyy" { c.askStartBalance() } }
                    .help(c.creditNote.isEmpty ? "Credit left for the chosen provider" : c.creditNote)
                Image(systemName: "gearshape")                 // v13: the API key file (file picker, key read by shape)
                    .font(.system(size: 13, weight: .regular)).foregroundStyle(Ink.text)
                    .padding(.horizontal, 4).padding(.vertical, 4)
                    .contentShape(Rectangle())
                    .onTapGesture { c.pickKeyFile() }
                    .axButton("API key file", id: "capi-key-gear") { c.pickKeyFile() }
                    .pressHover()
                    .help("Choose the file with the API key of the chosen provider; other text around it is fine")
            }.pipeGroup().padding(.vertical, 2)
            HStack(spacing: 6) {
                Text(String(format: "this chat $%.4f", c.total).replacingOccurrences(of: " ", with: "\u{00A0}"))
                    .foregroundStyle(Ink.dim).unit()
                if !c.keyNote.isEmpty {
                    Text(c.keyNote.replacingOccurrences(of: " ", with: "\u{00A0}"))
                        .foregroundStyle(c.keyNote.hasPrefix("API key loaded") ? Ink.green : Ink.red).unit()
                        .accessibilityIdentifier("capi-key-note")
                }
            }.pipeGroup().padding(.vertical, 2)
            HStack(spacing: 4) {
                Text("FOLDER").foregroundStyle(Ink.dim).unit().padding(.leading, 6)
                Menu {
                    ForEach(c.folders) { f in Button(f.name) { c.setFolder(f.path) } }
                } label: {
                    Text(c.folderName.isEmpty ? "…" : c.folderName).foregroundStyle(Ink.accent).unit()
                }
                .menuStyle(.borderlessButton).fixedSize()
                .padding(.horizontal, 6).padding(.vertical, 4)
                .pressHover()
                .accessibilityIdentifier("capi-folder")
                .help("The folder Claude Code works in")
            }.pipeGroup()
            Word(text: "NEW CHAT", id: "capi-new-conversation",
                 help: "A clean chat: its own Claude Code process") { Task { await c.newConversation() } }
                .pipeGroup().flowRight()
        }
        .font(.system(size: 12, weight: .bold, design: .monospaced))
        .padding(.horizontal, 8).padding(.vertical, 2)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

struct CapiConversation: View {
    @ObservedObject var c = Capi.shared
    var body: some View {
        MessageList(messages: c.messages,
                    empty: "Claude Code on your API credit. Ask for anything; it works in the folder above, remembers the chat across days, and shows one line per tool it uses. Several chats can work at the same time: the list on the left.",
                    notice: c.notice) { EmptyView() }
    }
}

struct CapiInput: View {
    @ObservedObject var c = Capi.shared
    @State private var text = ""
    @FocusState private var focused: Bool
    var body: some View {
        VStack(spacing: 6) {
            TextField("Write to Claude Code (API credit)", text: $text, axis: .vertical)
                .textFieldStyle(.plain)
                .font(.system(size: 14))
                .foregroundStyle(Ink.text)
                .lineLimit(1...8)
                .focused($focused)
                .onSubmit { go() }
                .padding(10)
                .background(RoundedRectangle(cornerRadius: 6).fill(Ink.panel))
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(Ink.line, lineWidth: 1))
                .accessibilityIdentifier("capi-prompt")
            FlowLayout(spacing: 4, rowSpacing: 0) {
                Text("MODEL").foregroundStyle(Ink.dim).unit().padding(.horizontal, 6)
                ForEach(Triple.models, id: \.self) { m in
                    Word(text: Triple.short(m), id: "capi-model-" + m, color: c.model == m ? Ink.claude : Ink.grey, help: m) { c.setModel(m) }
                }
                if c.busy {
                    Word(text: "STOP", id: "capi-stop", color: Ink.amber, help: "Stop this chat's process (the history stays)") { c.stop() }
                } else {
                    let has = !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    Word(text: "SEND", id: "capi-send", color: has ? Ink.accent : Ink.grey, help: "Send to Claude Code (Return)") { go() }
                }
            }
            .font(.system(size: 13, weight: .bold, design: .monospaced))
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(12)
        .onAppear { focused = true }
    }

    func go() {
        let s = text
        guard !c.busy, !s.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
        text = ""
        c.send(s)
    }
}

/// CHATS: every stored conversation. Click the title to switch to it; a green line on the left edge while its
/// process runs; START (resume from the stored history), STOP (history kept), CLOSE (delete, asks first).
struct CapiRoomList: View {
    @ObservedObject var c = Capi.shared
    @State private var renaming: ConvMeta? = nil
    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 0) {
                ForEach(c.convs) { r in
                    HStack(alignment: .top, spacing: 0) {
                        Rectangle().fill(r.running ? Ink.green : Color.clear).frame(width: 4)
                            .accessibilityHidden(true)
                        VStack(alignment: .leading, spacing: 4) {
                            VStack(alignment: .leading, spacing: 2) {      // the title on its own line (wraps between words only)
                                Text(r.title).font(.system(size: 13, weight: r.id == c.convId ? .bold : .regular))
                                    .foregroundStyle(r.id == c.convId ? Ink.claude : Ink.text)
                                    .fixedSize(horizontal: false, vertical: true)
                                Text(CapiRoomList.status(r)).font(.system(size: 11, design: .monospaced))
                                    .foregroundStyle(r.busy ? Ink.green : (r.error.isEmpty || r.error == "stopped" ? Ink.dim : Ink.red))
                                    .unit()
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .contentShape(Rectangle())
                            .onTapGesture { Task { await c.open(r.id) } }
                            .axButton("Chat " + r.title, id: "capi-conv-" + r.id,
                                      value: r.running ? (r.busy ? "answering" : "running") : "stopped") { Task { await c.open(r.id) } }
                            .pressHover()
                            // v20: ONE line RENAME START STOP CLOSE; only a narrow pane wraps, whole buttons, never letters
                            FlowLayout(spacing: 0, rowSpacing: 0) {
                                act("RENAME", "Rename", r, on: true, color: Ink.accent) { renaming = r }
                                act("START", "Start", r, on: !r.running, color: Ink.green) { c.startConv(r.id) }
                                act("STOP", "Stop", r, on: r.running, color: Ink.amber) { c.stopConv(r.id) }
                                act("CLOSE", "Close", r, on: true, color: Ink.red) { c.closeConv(r) }
                            }
                            .font(.system(size: 11, weight: .bold, design: .monospaced))
                        }
                        .padding(.leading, 8).padding(.vertical, 8).padding(.trailing, 6)
                    }
                    .background(r.id == c.convId ? Ink.bg.opacity(0.6) : Color.clear)
                    Hairline()
                }
            }
        }
        .background(Ink.panel)
        .sheet(item: $renaming) { r in CapiRenameSheet(conv: r) { renaming = nil } }
    }

    static func status(_ r: ConvMeta) -> String {
        let state = r.busy ? "answering" : (r.running ? "running" : "stopped")
        return "\(r.count) lines  ·  \(state)"
    }

    /// One action word after the title: tap + Accessibility button named with the conversation ("Start <title>").
    @ViewBuilder
    func act(_ word: String, _ verb: String, _ r: ConvMeta, on: Bool, color: Color, _ action: @escaping () -> Void) -> some View {
        Text(word).foregroundStyle(on ? color : Ink.grey.opacity(0.5)).unit()
            .padding(.horizontal, 4).padding(.vertical, 3)
            .contentShape(Rectangle())
            .onTapGesture { if on { action() } }
            .axButton(verb + " " + r.title, id: "capi-" + word.lowercased() + "-" + r.id) { if on { action() } }
            .pressHover()
            .help(verb == "Start" ? "Start its own process: it reads the whole history and you continue"
                  : verb == "Stop" ? "Stop its process; the history stays"
                  : verb == "Rename" ? "Give this chat a name of your own, or let Haiku name it" : "Delete this chat and its history")
    }
}


/// RENAME: a small field with the current name; Return / OK saves, Esc cancels; AUTOMATIC NAME asks Haiku (one cheap call
/// on the chosen provider) and fills the field, you can still edit before saving.
struct CapiRenameSheet: View {
    let conv: ConvMeta
    let done: () -> Void
    @ObservedObject var c = Capi.shared
    @State private var name = ""
    @State private var working = false
    @State private var info = ""
    @FocusState private var focused: Bool
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Rename chat").font(.system(size: 14, weight: .bold)).foregroundStyle(Ink.text)
            TextField("Name", text: $name)
                .textFieldStyle(.roundedBorder)
                .focused($focused)
                .onSubmit { save() }
                .accessibilityIdentifier("capi-rename-field")
            if !info.isEmpty {
                Text(info).font(.system(size: 11, design: .monospaced)).foregroundStyle(info.hasPrefix("ERROR") ? Ink.red : Ink.dim)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack(spacing: 4) {
                Word(text: working ? "NAMING…" : "AUTOMATIC NAME", id: "capi-autoname", color: working ? Ink.grey : Ink.claude,
                     help: "One Haiku call reads the whole chat and suggests a name") { auto() }
                Spacer(minLength: 4)
                Word(text: "CANCEL", id: "capi-rename-cancel", color: Ink.grey) { done() }
                    .keyboardShortcut(.cancelAction)
                Word(text: "OK", id: "capi-rename-ok", color: Ink.accent) { save() }
            }
            .font(.system(size: 13, weight: .bold, design: .monospaced))
        }
        .padding(16).frame(width: 380)
        .onAppear { name = conv.title; focused = true }
    }

    func save() {
        let n = name
        Task { @MainActor in await c.rename(conv.id, to: n); done() }
    }

    func auto() {
        guard !working else { return }
        working = true
        info = ""
        Task { @MainActor in
            let (t, cost, err) = await c.autoName(conv.id)
            working = false
            if !t.isEmpty { name = t }
            let price = cost > 0 ? String(format: "Haiku via %@ $%.4f", c.providerName, cost) : ""
            info = err.isEmpty ? price : "ERROR: " + err + (price.isEmpty ? "" : "  " + price)
        }
    }
}
