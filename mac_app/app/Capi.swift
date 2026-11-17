// Capi.swift: the CAPI tab (17.11.2026). Marko: "can queen be used as capi ... add capi tab to queen software so i can have
// nicer ui". A chat with Claude Code on the $100 API credit: the server (qwen_app/capi_chat.py, /api/capi/*) runs exactly
// what `capi` runs (headless claude -p, one session per room, working folder, model) and streams the events here.
// One module: the list, bubbles, Markdown and speaker are the shared ones (MessageList, Bubble, MarkdownView, SpeakerButton).
import SwiftUI
import Foundation

struct FolderItem: Identifiable, Equatable {
    var id: String { path }
    let name: String
    let path: String
}

final class Capi: ObservableObject {
    static let shared = Capi()

    @Published var active = false
    @Published var roomId = ""
    @Published var title = ""
    @Published var messages: [Msg] = []          // role: marko | claude | tool
    @Published var rooms: [RoomMeta] = []
    @Published var folders: [FolderItem] = []
    @Published var model = "claude-sonnet-5-5"
    @Published var cwd = ""
    @Published var total = 0.0
    @Published var left: Double? = nil
    @Published var busy = false
    @Published var notice = ""
    private var task: Task<Void, Never>?

    var creditText: String { left.map { String(format: "API ($%.2f left)", $0) } ?? "API ($ ?)" }
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
        if !roomId.isEmpty { return }
        await loadRooms()
        if let first = rooms.first { await open(first.id) } else { await newRoom() }
    }

    @MainActor
    func loadCredit() async {
        if let j = await Queen.shared.json("/api/capi/credit") { left = j["left"] as? Double }
    }

    @MainActor
    func loadRooms() async {
        guard let j = await Queen.shared.json("/api/capi/list"), let list = j["rooms"] as? [[String: Any]] else { return }
        rooms = list.compactMap { r in
            guard let id = r["id"] as? String else { return nil }
            return RoomMeta(id: id, title: (r["title"] as? String) ?? "CAPI chat", count: (r["count"] as? Int) ?? 0)
        }
    }

    @MainActor
    private func apply(_ room: [String: Any]) {
        roomId = (room["id"] as? String) ?? roomId
        title = (room["title"] as? String) ?? "CAPI chat"
        model = (room["model"] as? String) ?? model
        cwd = (room["cwd"] as? String) ?? cwd
        total = (room["total"] as? Double) ?? 0
        let ms = (room["messages"] as? [[String: Any]]) ?? []
        messages = ms.compactMap { m in
            guard let r = m["role"] as? String else { return nil }
            return Msg(role: r, content: (m["text"] as? String) ?? "", cost: (m["cost"] as? Double) ?? 0)
        }
    }

    @MainActor
    func open(_ id: String) async {
        guard !busy, let j = await Queen.shared.json("/api/capi/get?id=" + id), let room = j["room"] as? [String: Any] else { return }
        apply(room)
    }

    @MainActor
    func newRoom() async {
        guard !busy else { return }
        let body: [String: Any] = ["cwd": cwd, "model": model]
        guard let j = await Queen.shared.json("/api/capi/new", body: body), let room = j["room"] as? [String: Any] else { return }
        apply(room)
        notice = ""
        await loadRooms()
    }

    @MainActor
    func setModel(_ m: String) { model = m; saveSettings() }

    @MainActor
    func setFolder(_ p: String) { cwd = p; saveSettings() }

    @MainActor
    private func saveSettings() {
        let body: [String: Any] = ["id": roomId, "model": model, "cwd": cwd]
        Task { _ = await Queen.shared.json("/api/capi/settings", body: body) }
    }

    @MainActor
    func send(_ text: String) {
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !busy, !roomId.isEmpty, !t.isEmpty else { return }
        messages.append(Msg(role: "marko", content: t))
        busy = true
        notice = ""
        task = Task { @MainActor in
            await self.stream(t)
            self.busy = false
            await self.reload()
            await self.loadCredit()
            await self.loadRooms()
        }
    }

    /// Stop: the server kills the claude run, then the stream ends by itself.
    @MainActor
    func stop() {
        let id = roomId
        Task { _ = await Queen.shared.json("/api/capi/stop", body: ["id": id]) }
    }

    @MainActor
    private func reload() async {
        guard let j = await Queen.shared.json("/api/capi/get?id=" + roomId), let room = j["room"] as? [String: Any] else { return }
        apply(room)
    }

    @MainActor
    private func stream(_ text: String) async {
        let body: [String: Any] = ["id": roomId, "text": text]
        guard let r = Queen.shared.request("/api/capi/turn", body: body, timeout: 1800) else { return }
        do {
            let (bytes, resp) = try await URLSession.shared.bytes(for: r)
            if let h = resp as? HTTPURLResponse, h.statusCode >= 400 {
                notice = "CAPI answered \(h.statusCode)."
                return
            }
            for try await l in bytes.lines {
                guard let o = try? JSONSerialization.jsonObject(with: Data(l.utf8)) as? [String: Any] else { continue }
                if let t = o["text"] as? String { messages.append(Msg(role: "claude", content: t)) }
                if let t = o["tool"] as? String { messages.append(Msg(role: "tool", content: t)) }
                if let c = o["cost"] as? Double, let i = messages.lastIndex(where: { $0.role == "claude" }) {
                    messages[i].cost = c
                    total = (o["total"] as? Double) ?? total
                    if let lf = o["left"] as? Double { left = lf }
                }
                if let e = o["error"] as? String { notice = e == "stopped" ? "Stopped." : "ERROR: " + e }
            }
        } catch {
            notice = "No answer: \(error.localizedDescription)"
        }
    }
}

// ---------------------------------------------------------------- the window parts
/// Top of the tab: the ONE credit number, the working folder, rooms.
struct CapiHeader: View {
    @ObservedObject var c = Capi.shared
    @Binding var showRooms: Bool
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 4) {
                Text(c.creditText.replacingOccurrences(of: " ", with: "\u{00A0}")).foregroundStyle(Ink.red).padding(.horizontal, 6)
                    .accessibilityIdentifier("capi-credit")
                Text(String(format: "this room $%.4f", c.total).replacingOccurrences(of: " ", with: "\u{00A0}"))
                    .foregroundStyle(Ink.dim)
                Spacer(minLength: 4)
                Word(text: "ROOMS", id: "capi-rooms", color: showRooms ? Ink.accent : Ink.text, help: "Your CAPI rooms") {
                    showRooms.toggle()
                    if showRooms { Task { await c.loadRooms() } }
                }
                Word(text: "NEW ROOM", id: "capi-new-room", help: "A clean conversation: a new Claude Code session") { Task { await c.newRoom() } }
            }
            HStack(spacing: 4) {
                Text("FOLDER").foregroundStyle(Ink.dim).padding(.horizontal, 6)
                Menu {
                    ForEach(c.folders) { f in Button(f.name) { c.setFolder(f.path) } }
                } label: {
                    Text(c.folderName.isEmpty ? "…" : c.folderName).foregroundStyle(Ink.accent)
                }
                .menuStyle(.borderlessButton).fixedSize()
                .padding(.horizontal, 6).padding(.vertical, 4)
                .pressHover()
                .accessibilityIdentifier("capi-folder")
                .help("The folder Claude Code works in")
                Spacer(minLength: 0)
            }
        }
        .font(.system(size: 12, weight: .bold, design: .monospaced))
        .padding(.horizontal, 8).padding(.vertical, 2)
    }
}

struct CapiConversation: View {
    @ObservedObject var c = Capi.shared
    var body: some View {
        MessageList(messages: c.messages,
                    empty: "Claude Code on your API credit. Ask for anything; it works in the folder above, remembers the conversation, and shows one line per tool it uses.",
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
            HStack(spacing: 4) {
                Text("MODEL").foregroundStyle(Ink.dim).padding(.horizontal, 6)
                ForEach(Triple.models, id: \.self) { m in
                    Word(text: Triple.short(m), id: "capi-model-" + m, color: c.model == m ? Ink.claude : Ink.grey, help: m) { c.setModel(m) }
                }
                Spacer(minLength: 4)
                if c.busy {
                    Word(text: "STOP", id: "capi-stop", color: Ink.amber, help: "Stop Claude Code's run") { c.stop() }
                } else {
                    let has = !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    Word(text: "SEND", id: "capi-send", color: has ? Ink.accent : Ink.grey, help: "Send to Claude Code (Return)") { go() }
                }
            }
            .font(.system(size: 13, weight: .bold, design: .monospaced))
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

struct CapiRoomList: View {
    @ObservedObject var c = Capi.shared
    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 0) {
                ForEach(c.rooms) { r in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(r.title).font(.system(size: 13, weight: r.id == c.roomId ? .bold : .regular))
                            .foregroundStyle(r.id == c.roomId ? Ink.claude : Ink.text)
                            .fixedSize(horizontal: false, vertical: true)
                        Text("\(r.count) lines").font(.system(size: 11, design: .monospaced)).foregroundStyle(Ink.dim)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 12).padding(.vertical, 8)
                    .contentShape(Rectangle())
                    .onTapGesture { Task { await c.open(r.id) } }
                    .axButton("Room " + r.title, id: "capi-room-" + r.id) { Task { await c.open(r.id) } }
                    .pressHover()
                    Hairline()
                }
            }
        }
        .background(Ink.panel)
    }
}
