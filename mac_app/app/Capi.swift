// Capi.swift: the CAPI tab (17.11.2026). Marko: "can queen be used as capi ... add capi tab to queen software so i can have
// nicer ui". A chat with Claude Code on the $100 API credit: the server (qwen_app/capi_chat.py, /api/capi/*) runs exactly
// what `capi` runs (headless claude -p, one session per room, working folder, model) and streams the events here.
// One module: the list, bubbles, Markdown and speaker are the shared ones (MessageList, Bubble, MarkdownView, SpeakerButton).
import SwiftUI
import AppKit
import Foundation
import UniformTypeIdentifiers

struct ProviderItem: Identifiable, Equatable {
    let id: String
    let name: String
}

/// v24: a file waiting in the input box (a chip) until SEND.
struct Attach: Identifiable, Equatable {
    let id = UUID()
    let name: String
    let mime: String
    let data: Data
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
    @Published var providers: [ProviderItem] = [ProviderItem(id: "anthropic", name: "Anthropic"), ProviderItem(id: "oxyy", name: "Oxyy"), ProviderItem(id: "gcloud", name: "Google Cloud")]
    @Published var attachments: [Attach] = []    // v24: files and images chosen / dropped / pasted, sent with the next prompt
    @Published var gmodel = ""                   // v24: the model of the Google Cloud provider (Gemini or claude-...@...)
    @Published var gGemini: [String] = []
    @Published var gClaude: [String] = []
    @Published var gDefault = ""
    @Published var queenOn = false               // v25: this chat's switch; off = Queen bypassed, not trained (the default)
    @Published var creditExpiry = ""             // v25: Google Cloud free credit expiry, e.g. 2.12.2026
    // v26: MASTER / SLAVE pair (server: /api/capi/pair). Marko: "next to each provider ... a switch master or slave".
    @Published var pairMaster = ""
    @Published var pairSlave = ""
    @Published var pairActive = false
    @Published var pairNote = ""
    @Published var pairRounds = 5
    @Published var pairCap = 0.50
    static let maxFile = 20 * 1024 * 1024
    @Published var creditNote = ""
    private var poller: Task<Void, Never>?
    private var shownSig = ""                    // what is on screen: count + last text, so a poll redraws only on change
    private var busyIds: Set<String> = []

    var creditText: String {
        let ex = creditExpiry.isEmpty ? "" : ", to " + creditExpiry
        return left.map { String(format: "\(providerName) ($%.2f left", $0) + ex + ")" } ?? "\(providerName) ($ ?)"
    }
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
        if gGemini.isEmpty, let j = await Queen.shared.json("/api/capi/gcloud_models", timeout: 25) {
            gGemini = (j["gemini"] as? [String]) ?? []
            gClaude = (j["claude"] as? [String]) ?? []
            gDefault = (j["default"] as? String) ?? ""
            if gmodel.isEmpty { gmodel = gDefault }
        }
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
        await loadPair()
    }

    // ---------------- v26: the pair
    @MainActor
    func loadPair() async {
        if let j = await Queen.shared.json("/api/capi/pair") { applyPair(j) }
    }

    @MainActor
    private func applyPair(_ j: [String: Any]) {
        pairMaster = (j["master"] as? String) ?? ""
        pairSlave = (j["slave"] as? String) ?? ""
        pairActive = (j["active"] as? Bool) ?? false
        pairNote = (j["note"] as? String) ?? ""
        pairRounds = (j["max_rounds"] as? Int) ?? pairRounds
        pairCap = (j["cap_usd"] as? Double) ?? pairCap
        // A Google Cloud master needs the Gemini list for its MASTER MODEL menu: if the first load failed, try again now.
        if pairMaster == "gcloud" && gGemini.isEmpty {
            Task { @MainActor in
                if let g = await Queen.shared.json("/api/capi/gcloud_models", timeout: 25) {
                    gGemini = (g["gemini"] as? [String]) ?? []
                    gDefault = (g["default"] as? String) ?? gDefault
                    if gmodel.isEmpty { gmodel = gDefault }
                }
            }
        }
    }

    func role(of id: String) -> String { pairMaster == id ? "MASTER" : (pairSlave == id ? "SLAVE" : "OFF") }

    static func upperName(_ id: String) -> String { id == "gcloud" ? "GOOGLE CLOUD" : id.uppercased() }

    var pairText: String { Capi.upperName(pairMaster) + " → " + Capi.upperName(pairSlave) }

    /// The switch beside a radio: OFF → MASTER → SLAVE → OFF. The server keeps one master and one slave.
    @MainActor
    func cycleRole(_ id: String) {
        let next: [String: Any]
        switch role(of: id) {
        case "OFF": next = ["master": id]
        case "MASTER": next = ["master": "", "slave": id]
        default: next = ["slave": ""]
        }
        Task { @MainActor in
            if let j = await Queen.shared.json("/api/capi/pair", body: next) { self.applyPair(j) }
        }
    }

    @MainActor
    func cycleRounds() {
        let n = pairRounds >= 10 ? 1 : pairRounds + 1
        pairRounds = n
        Task { @MainActor in if let j = await Queen.shared.json("/api/capi/pair", body: ["max_rounds": n]) { self.applyPair(j) } }
    }

    @MainActor
    func askCap() {
        let a = NSAlert()
        a.messageText = "Cost cap of one pair turn, in dollars"
        a.informativeText = "Master and slave together stop when this much is spent on one prompt. Now $" + String(format: "%.2f", pairCap) + "."
        let f = NSTextField(frame: NSRect(x: 0, y: 0, width: 160, height: 24))
        f.stringValue = String(format: "%.2f", pairCap)
        a.accessoryView = f
        a.addButton(withTitle: "Set")
        a.addButton(withTitle: "Cancel")
        guard a.runModal() == .alertFirstButtonReturn else { return }
        guard let v = Double(f.stringValue.replacingOccurrences(of: ",", with: ".").trimmingCharacters(in: .whitespaces)) else { return }
        Task { @MainActor in if let j = await Queen.shared.json("/api/capi/pair", body: ["cap_usd": v]) { self.applyPair(j) } }
    }

    @MainActor
    private func applyCredit(_ j: [String: Any]) {
        left = j["left"] as? Double
        provider = (j["provider"] as? String) ?? provider
        providerName = (j["name"] as? String) ?? providerName
        creditNote = (j["note"] as? String) ?? ""
        creditExpiry = (j["expires"] as? String) ?? ""
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
        queenOn = (room["queen"] as? String) == "on"
        if let g = room["gmodel"] as? String, !g.isEmpty { gmodel = g } else if gmodel.isEmpty { gmodel = gDefault }
        cwd = (room["cwd"] as? String) ?? cwd
        total = (room["total"] as? Double) ?? 0
        busy = (j["busy"] as? Bool) ?? false
        running = (j["running"] as? Bool) ?? false
        let e = (j["error"] as? String) ?? ""
        notice = e.isEmpty ? "" : (e == "stopped" ? "Stopped." : Capi.line(e))
        if force || sig != shownSig {
            shownSig = sig
            messages = ms.compactMap { m in
                guard let r = m["role"] as? String else { return nil }
                let att = (m["files"] as? [String]) ?? []
                return Msg(role: r, content: ((m["text"] as? String) ?? "") + (att.isEmpty ? "" : "\n\n[attached: " + att.joined(separator: ", ") + "]"), cost: (m["cost"] as? Double) ?? 0,
                           status: (m["status"] as? String) ?? "", reason: (m["reason"] as? String) ?? "",
                           label: (m["label"] as? String) ?? "")
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

    /// One plain line for a failure: Google Cloud's own sentences stand alone, other errors keep the ERROR prefix.
    static func line(_ e: String) -> String {
        (e.hasPrefix("Claude on Google Cloud") || e.contains("limit is 20 MB") || e.contains("not supported")) ? e : "ERROR: " + e
    }

    @MainActor
    func setModel(_ m: String) { model = m; saveSettings() }

    @MainActor
    func setQueen(_ on: Bool) {
        queenOn = on
        let id = convId
        Task { @MainActor in _ = await Queen.shared.json("/api/capi/queen", body: ["id": id, "on": on]) }
    }

    @MainActor
    func setGModel(_ m: String) { gmodel = m; saveSettings() }

    // v24: the file picker (paperclip), drag and drop, paste. Max 20 MB each; chips show them until SEND.
    @MainActor
    func addURLs(_ urls: [URL]) {
        for u in urls {
            let size = (try? u.resourceValues(forKeys: [.fileSizeKey]))?.fileSize ?? 0
            if size > Capi.maxFile {
                notice = String(format: "%@ is %.1f MB: the limit is 20 MB per file.", u.lastPathComponent, Double(size) / 1_048_576)
                continue
            }
            guard let d = try? Data(contentsOf: u) else { notice = "\(u.lastPathComponent) could not be read."; continue }
            let mime = UTType(filenameExtension: u.pathExtension.lowercased())?.preferredMIMEType ?? "application/octet-stream"
            attachments.append(Attach(name: u.lastPathComponent, mime: mime, data: d))
        }
    }

    @MainActor
    func addImage(_ png: Data) {
        if png.count > Capi.maxFile { notice = "The pasted image is over 20 MB: the limit is 20 MB per file."; return }
        let f = DateFormatter(); f.dateFormat = "HHmmss"
        attachments.append(Attach(name: "pasted-" + f.string(from: Date()) + ".png", mime: "image/png", data: png))
    }

    @MainActor
    func pickFiles() {
        let p = NSOpenPanel()
        p.title = "Files to send with your message"
        p.allowsMultipleSelection = true
        p.canChooseDirectories = false
        if p.runModal() == .OK { addURLs(p.urls) }
    }

    @MainActor
    func setFolder(_ p: String) { cwd = p; saveSettings() }

    @MainActor
    private func saveSettings() {
        let body: [String: Any] = ["id": convId, "model": model, "cwd": cwd, "gmodel": gmodel]
        Task { @MainActor in
            guard let j = await Queen.shared.json("/api/capi/settings", body: body) else { return }
            apply(j, force: true)
            if let n = j["notice"] as? String, !n.isEmpty { notice = n }
        }
    }

    /// Send: the server writes it to the conversation's own process (started if it was not); the answer lands in its file.
    @MainActor
    func send(_ text: String) {
        var t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !busy, !convId.isEmpty, !(t.isEmpty && attachments.isEmpty) else { return }
        if t.isEmpty { t = "Please look at the attached file(s)." }
        let files: [[String: String]] = attachments.map { ["name": $0.name, "mime": $0.mime, "b64": $0.data.base64EncodedString()] }
        let names = attachments.map { $0.name }
        attachments = []
        messages.append(Msg(role: "marko", content: t + (names.isEmpty ? "" : "\n\n[attached: " + names.joined(separator: ", ") + "]"), status: "sent"))
        busy = true
        notice = ""
        let id = convId
        Task { @MainActor in
            let j = await Queen.shared.json("/api/capi/send", body: ["id": id, "text": t, "files": files], timeout: 180)
            if let e = j?["error"] as? String, !e.isEmpty, id == self.convId { self.notice = Capi.line(e) }
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
    @Binding var showList: Bool
    var body: some View {
        // v20: groups divided by dim pipes, each group one unbreakable unit; whole groups wrap when narrow; NEW CHAT at the right end.
        FlowLayout(spacing: 8, rowSpacing: 0) {
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                Text("PROVIDER").foregroundStyle(Ink.dim).unit().padding(.horizontal, 6)
                ForEach(c.providers) { p in
                    HStack(alignment: .firstTextBaseline, spacing: 0) {   // v26: radio + its MASTER / SLAVE switch, one unit
                        Word(text: (c.provider == p.id ? "◉ " : "○ ") + p.name.uppercased(), id: "capi-provider-" + p.id,
                             color: c.provider == p.id ? Ink.accent : Ink.text,
                             help: "Use \(p.name) for the next prompts") { c.setProvider(p.id) }
                        RoleSwitch(id: p.id, name: p.name)
                    }.unit()
                }
            }.unit().padding(.vertical, 2)
            if c.pairActive {
                // v26: the active pair, e.g. PAIR | ANTHROPIC → GOOGLE CLOUD, then its rounds and its cost cap
                HStack(alignment: .firstTextBaseline, spacing: 6) {
                    Text("PAIR").foregroundStyle(Ink.amber).unit()
                    Text("|").foregroundStyle(Ink.dim).unit()
                    Text(c.pairText.replacingOccurrences(of: " ", with: "\u{00A0}")).foregroundStyle(Ink.amber).unit()
                }
                .padding(.horizontal, 6)
                .accessibilityElement(children: .combine).accessibilityIdentifier("capi-pair")
                .help(c.pairNote)
                .pipeGroup().padding(.vertical, 2)
                HStack(alignment: .firstTextBaseline, spacing: 0) {
                    Word(text: "ROUNDS\u{00A0}\(c.pairRounds)", id: "capi-pair-rounds", color: Ink.text,
                         help: "Most rounds (slave report + master review) in one pair turn; click for one more (1 to 10)") { c.cycleRounds() }
                    Word(text: String(format: "CAP\u{00A0}$%.2f", c.pairCap), id: "capi-pair-cap", color: Ink.text,
                         help: "Cost cap of one pair turn (master and slave together); click to change") { c.askCap() }
                }.pipeGroup().padding(.vertical, 2)
            } else if !c.pairMaster.isEmpty || !c.pairSlave.isEmpty {
                Text("PAIR\u{00A0}|\u{00A0}SINGLE").foregroundStyle(Ink.dim).unit().padding(.horizontal, 6)
                    .help(c.pairNote).accessibilityIdentifier("capi-pair")
                    .pipeGroup().padding(.vertical, 2)
            }
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                Text(c.creditText.replacingOccurrences(of: " ", with: "\u{00A0}")).foregroundStyle(Ink.red).unit()
                    .padding(.leading, 6)
                    .accessibilityIdentifier("capi-credit")
                    .onTapGesture { if c.provider == "oxyy" { c.askStartBalance() } }
                    .help(c.creditNote.isEmpty ? "Credit left for the chosen provider" : c.creditNote)
                Text(Image(systemName: "gearshape"))           // v13: the API key file (file picker, key read by shape); a Text so it sits on the baseline
                    .font(.system(size: 12, weight: .regular)).foregroundStyle(Ink.text)
                    .padding(.horizontal, 4).padding(.vertical, 4)
                    .contentShape(Rectangle())
                    .onTapGesture { c.pickKeyFile() }
                    .axButton("API key file", id: "capi-key-gear") { c.pickKeyFile() }
                    .pressHover()
                    .help("Choose the file with the API key of the chosen provider; other text around it is fine")
            }.pipeGroup().padding(.vertical, 2)
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text(String(format: "this chat $%.4f", c.total).replacingOccurrences(of: " ", with: "\u{00A0}"))
                    .foregroundStyle(Ink.dim).unit()
                Word(text: c.queenOn ? "QUEEN: ON" : "QUEEN: OFF", id: "capi-queen", color: c.queenOn ? Ink.amber : Ink.green,
                     help: c.queenOn ? "Queen may use this chat (her capi skill). Click to bypass her again."
                                     : "Queen is bypassed in this chat: no Queen prompt, no Groq, nothing recorded for her training, her capi skill refused. Click to allow her.") { c.setQueen(!c.queenOn) }
                if !c.keyNote.isEmpty {
                    Text(c.keyNote.replacingOccurrences(of: " ", with: "\u{00A0}"))
                        .foregroundStyle(c.keyNote.hasPrefix("API key loaded") ? Ink.green : Ink.red).unit()
                        .accessibilityIdentifier("capi-key-note")
                }
            }.pipeGroup().padding(.vertical, 2)
            HStack(alignment: .firstTextBaseline, spacing: 4) {
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
            // v22: the CHATS toggle is back (Marko: "You deleted it, and I didn't ask you to"): hides the whole list pane
            Word(text: "CHATS", id: "capi-chats", color: showList ? Ink.accent : Ink.text,
                 help: "Show or hide the list of chats on the left: hidden, the chat fills the whole window") { showList.toggle() }
                .pipeGroup().flowRight()
        }
        .clipped()
        .font(.system(size: 12, weight: .bold, design: .monospaced))
        .padding(.horizontal, 8).padding(.vertical, 2)
        .frame(maxWidth: .infinity, alignment: .leading)
    }
}

/// v26: the small MASTER / SLAVE switch beside a provider radio. Click: OFF → MASTER → SLAVE → OFF.
struct RoleSwitch: View {
    @ObservedObject var c = Capi.shared
    let id: String
    let name: String
    var body: some View {
        let r = c.role(of: id)
        let col = r == "MASTER" ? Ink.amber : (r == "SLAVE" ? Ink.green : Ink.grey)
        Text(r)
            .font(.system(size: 10, weight: .bold, design: .monospaced))
            .foregroundStyle(col).unit()
            .padding(.horizontal, 4).padding(.vertical, 1)
            .overlay(RoundedRectangle(cornerRadius: 3).stroke(col.opacity(0.8), lineWidth: 1))
            .padding(.trailing, 6)
            .contentShape(Rectangle())
            .onTapGesture { c.cycleRole(id) }
            .axButton(name + " pair role", id: "capi-role-" + id, value: r) { c.cycleRole(id) }
            .pressHover()
            .help("\(name) in a pair: \(r). Click: OFF → MASTER → SLAVE → OFF. A master plans and reviews, the slave does the work and reports; with no master or no slave the chosen provider works alone.")
    }
}

struct CapiConversation: View {
    @ObservedObject var c = Capi.shared
    var body: some View {
        VStack(spacing: 0) {
            // v22: TOPIC | the chat's own title once more at the top of the chat
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Text("TOPIC").foregroundStyle(Ink.dim).unit()
                Text("|").foregroundStyle(Ink.dim).unit()
                Text(c.title.isEmpty ? "CAPI chat" : c.title).foregroundStyle(Ink.claude)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 0)
            }
            .font(.system(size: 12, weight: .bold, design: .monospaced))
            .padding(.horizontal, 14).padding(.vertical, 6)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityIdentifier("capi-topic")
            Hairline()
        MessageList(messages: c.messages,
                    empty: "Claude Code on your API credit. Ask for anything; it works in the folder above, remembers the chat across days, and shows one line per tool it uses. Several chats can work at the same time: the list on the left.",
                    notice: c.notice) { EmptyView() }
        }
    }
}

/// v23: the right pane = TOPIC line + chat stream + the input, so the input is exactly as wide as the stream and the chat list
/// (left) runs to the bottom of the window. Marko: "resize it to be at the size of chat stream ... extend chat list to the
/// bottom of the page."
struct CapiPane: View {
    @AppStorage("ui.capiInputH") private var inputH: Double = 110
    var body: some View {
        GeometryReader { g in
            VStack(spacing: 0) {
                CapiConversation()
                Hairline()
                CapiInput(height: $inputH, maxH: max(80, Double(g.size.height) * 0.7))
            }
        }
        .frame(minWidth: 280)
    }
}

/// v24: a text view that takes pasted images and files as chips; pasted text goes in as before.
final class PasteView: NSTextView {
    var onPasteFiles: (([URL]) -> Void)?
    var onPasteImage: ((Data) -> Void)?
    override func paste(_ sender: Any?) {
        let pb = NSPasteboard.general
        if let urls = pb.readObjects(forClasses: [NSURL.self], options: [.urlReadingFileURLsOnly: true]) as? [URL], !urls.isEmpty {
            onPasteFiles?(urls); return
        }
        if pb.string(forType: .string) == nil,
           let tiff = pb.data(forType: .tiff) ?? pb.data(forType: .png),
           let rep = NSBitmapImageRep(data: tiff), let png = rep.representation(using: .png, properties: [:]) {
            onPasteImage?(png); return
        }
        super.paste(sender)
    }
}

/// An unlimited text box: NSTextView in an NSScrollView (no character or line cap), visible scroll bar when the text is longer
/// than the box, Return sends, Shift+Return (or Option+Return) is a new line.
struct PromptEditor: NSViewRepresentable {
    @Binding var text: String
    var onSend: () -> Void
    var focusTick: Int

    func makeCoordinator() -> Coordinator { Coordinator(self) }

    func makeNSView(context: Context) -> NSScrollView {
        let sv = NSScrollView()
        sv.drawsBackground = false
        sv.hasVerticalScroller = true
        sv.autohidesScrollers = true
        sv.scrollerStyle = .legacy            // a visible bar whenever the text overflows the box
        sv.borderType = .noBorder
        let tv = PasteView()
        tv.onPasteFiles = { urls in Task { @MainActor in Capi.shared.addURLs(urls) } }
        tv.onPasteImage = { d in Task { @MainActor in Capi.shared.addImage(d) } }
        tv.delegate = context.coordinator
        tv.isRichText = false
        tv.allowsUndo = true
        tv.font = NSFont.systemFont(ofSize: 14)
        tv.textColor = NSColor(Ink.text)
        tv.insertionPointColor = NSColor(Ink.text)
        tv.drawsBackground = false
        tv.isAutomaticQuoteSubstitutionEnabled = false
        tv.isAutomaticDashSubstitutionEnabled = false
        tv.isAutomaticTextReplacementEnabled = false
        tv.isAutomaticSpellingCorrectionEnabled = false
        tv.textContainerInset = NSSize(width: 4, height: 6)
        tv.isVerticallyResizable = true
        tv.isHorizontallyResizable = false
        tv.autoresizingMask = [.width]
        tv.textContainer?.widthTracksTextView = true
        tv.textContainer?.containerSize = NSSize(width: 0, height: CGFloat.greatestFiniteMagnitude)
        tv.maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        tv.setAccessibilityIdentifier("capi-prompt")
        tv.setAccessibilityLabel("Write to Claude Code")
        sv.documentView = tv
        DispatchQueue.main.async { tv.window?.makeFirstResponder(tv) }
        return sv
    }

    func updateNSView(_ sv: NSScrollView, context: Context) {
        context.coordinator.parent = self
        guard let tv = sv.documentView as? NSTextView else { return }
        if tv.string != text { tv.string = text }
        if context.coordinator.tick != focusTick {
            context.coordinator.tick = focusTick
            DispatchQueue.main.async { tv.window?.makeFirstResponder(tv) }
        }
    }

    final class Coordinator: NSObject, NSTextViewDelegate {
        var parent: PromptEditor
        var tick = 0
        init(_ p: PromptEditor) { parent = p }
        func textDidChange(_ n: Notification) {
            if let tv = n.object as? NSTextView { parent.text = tv.string }
        }
        func textView(_ tv: NSTextView, doCommandBy sel: Selector) -> Bool {
            if sel == #selector(NSResponder.insertNewline(_:)) {
                let f = NSApp.currentEvent?.modifierFlags ?? []
                if f.contains(.shift) || f.contains(.option) { tv.insertNewlineIgnoringFieldEditor(nil); return true }
                parent.onSend()
                return true
            }
            return false
        }
    }
}

struct CapiInput: View {
    @ObservedObject var c = Capi.shared
    @Binding var height: Double
    var maxH: Double
    @State private var text = ""
    @State private var startH: Double? = nil
    @State private var tick = 0
    var body: some View {
        VStack(spacing: 4) {
            // the drag handle on the top edge of the box: drag up to make the box taller (min about 2 lines, max 70% of the pane)
            ZStack {
                Rectangle().fill(Color.clear).frame(height: 10)
                Capsule().fill(Ink.line).frame(width: 36, height: 3)
            }
            .contentShape(Rectangle())
            .onHover { inside in if inside { NSCursor.resizeUpDown.push() } else { NSCursor.pop() } }
            .gesture(DragGesture(minimumDistance: 1, coordinateSpace: .global)
                .onChanged { g in
                    if startH == nil { startH = height }
                    height = min(maxH, max(58, (startH ?? height) - Double(g.translation.height)))
                }
                .onEnded { _ in startH = nil })
            .help("Drag to resize the text box; double-click for the usual height")
            .onTapGesture(count: 2) { height = 110 }
            .accessibilityElement().accessibilityLabel("Text box height").accessibilityValue("\(Int(height)) points")
            .accessibilityAdjustableAction { d in
                switch d {
                case .increment: height = min(maxH, height + 20)
                case .decrement: height = max(58, height - 20)
                @unknown default: break
                }
            }
            ZStack(alignment: .topLeading) {
                PromptEditor(text: $text, onSend: { go() }, focusTick: tick)
                if text.isEmpty {
                    Text(c.pairActive ? "Write to the master (\(Capi.upperName(c.pairMaster).capitalized)); it plans, the slave (\(Capi.upperName(c.pairSlave).capitalized)) works and reports"
                         : (c.provider == "gcloud" ? "Write to Google Cloud (free credit); attach files with the paperclip" : "Write to Claude Code (API credit)")).font(.system(size: 14)).foregroundStyle(Ink.dim)
                        .padding(.horizontal, 8).padding(.vertical, 6).allowsHitTesting(false)
                }
            }
            .frame(height: min(height, maxH))
            .background(RoundedRectangle(cornerRadius: 6).fill(Ink.panel))
            .overlay(RoundedRectangle(cornerRadius: 6).stroke(Ink.line, lineWidth: 1))
            .onDrop(of: [UTType.fileURL], isTargeted: nil) { provs in
                for p in provs {
                    _ = p.loadObject(ofClass: URL.self) { url, _ in
                        if let url = url { Task { @MainActor in Capi.shared.addURLs([url]) } }
                    }
                }
                return true
            }
            if !c.attachments.isEmpty {
                FlowLayout(spacing: 6, rowSpacing: 4) {
                    ForEach(c.attachments) { a in
                        Text("\(a.name) \(a.data.count / 1024) KB  ✕").unit()
                            .foregroundStyle(Ink.text)
                            .padding(.horizontal, 8).padding(.vertical, 3)
                            .background(RoundedRectangle(cornerRadius: 10).fill(Ink.panel))
                            .overlay(RoundedRectangle(cornerRadius: 10).stroke(Ink.line, lineWidth: 1))
                            .contentShape(Rectangle())
                            .onTapGesture { c.attachments.removeAll { $0.id == a.id } }
                            .axButton("Remove " + a.name, id: "capi-chip-" + a.name) { c.attachments.removeAll { $0.id == a.id } }
                            .help("Click to remove this file from the message")
                    }
                }
                .font(.system(size: 12, weight: .bold, design: .monospaced))
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            FlowLayout(spacing: 4, rowSpacing: 0) {
                Text(Image(systemName: "paperclip"))             // v24: the file picker (also drag and drop, and paste)
                    .font(.system(size: 14, weight: .regular)).foregroundStyle(c.attachments.isEmpty ? Ink.text : Ink.accent)
                    .padding(.horizontal, 6).padding(.vertical, 2)
                    .contentShape(Rectangle())
                    .onTapGesture { c.pickFiles() }
                    .axButton("Attach files", id: "capi-attach") { c.pickFiles() }
                    .pressHover()
                    .help("Attach images, PDFs, text or code (up to 20 MB each); you can also drop or paste them here")
                Text(c.pairActive ? "MASTER\u{00A0}MODEL" : "MODEL").foregroundStyle(Ink.dim).unit().padding(.horizontal, 6)
                    .help(c.pairActive ? "The master's model; the master chooses the slave's model itself, round by round" : "")
                if (c.pairActive ? c.pairMaster : c.provider) == "gcloud" {
                    Menu {
                        // The list comes newest first. Models newer than Queen's default are lowered into their own section below
                        // the established ones (the default and everything older), so the new, untried ones are not the first choice.
                        let cut = c.gGemini.firstIndex(of: c.gDefault) ?? 0
                        Section("Gemini") { ForEach(Array(c.gGemini[cut...]), id: \.self) { m in Button(m) { c.setGModel(m) } } }
                        if cut > 0 {
                            Section("Newer than the default") { ForEach(Array(c.gGemini[..<cut]), id: \.self) { m in Button(m) { c.setGModel(m) } } }
                        }
                    } label: {
                        Text(c.gmodel.isEmpty ? "…" : c.gmodel).foregroundStyle(Ink.claude).unit()
                    }
                    .menuStyle(.borderlessButton).fixedSize()
                    .accessibilityIdentifier("capi-gmodel")
                    .help("Gemini models, listed live from Google; paid from the free credit")
                } else {
                    ForEach(Triple.models, id: \.self) { m in
                        Word(text: Triple.short(m), id: "capi-model-" + m, color: c.model == m ? Ink.claude : Ink.grey, help: m) { c.setModel(m) }
                    }
                }
                if c.busy {
                    Word(text: "STOP", id: "capi-stop", color: Ink.amber, help: "Stop this chat's process (the history stays)") { c.stop() }
                } else {
                    let has = !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || !c.attachments.isEmpty
                    Word(text: "SEND", id: "capi-send", color: has ? Ink.accent : Ink.grey, help: "Send to Claude Code (Return)") { go() }
                }
            }
            .clipped()
            .font(.system(size: 13, weight: .bold, design: .monospaced))
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 12).padding(.bottom, 10).padding(.top, 2)
    }

    func go() {
        let s = text
        guard !c.busy, !(s.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && c.attachments.isEmpty) else { return }
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
                    .overlay(r.id == c.convId ? RoundedRectangle(cornerRadius: 6).stroke(Ink.green, lineWidth: 1.5).padding(2) : nil)
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
