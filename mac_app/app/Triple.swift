// Triple.swift: TRIPLE CHAT (17.11.2026). One room for three brains: Marko, Queen (Groq) and Claude (the local Claude Code
// on the plan, or the API). Marko: "we all can hear each other and comment on each other's thoughts". The room lives in
// Python (qwen_app/triple_chat.py, /api/triple/*, proxied by the QueenServer); this file is its model and its window parts.
// One module: it reuses Bubble, Word, Hairline, Ink, axButton and pressHover from App.swift, no second copy.
import SwiftUI
import Foundation

struct RoomMeta: Identifiable, Equatable {
    let id: String
    let title: String
    let count: Int
}

final class Triple: ObservableObject {
    static let shared = Triple()
    static let models = ["claude-haiku-5-5", "claude-sonnet-5-5", "claude-opus-5-5", "claude-fable-5-2"]

    @Published var active = false
    @Published var roomId = ""
    @Published var title = ""
    @Published var messages: [Msg] = []          // Msg.role is the speaker here: marko | queen | claude
    @Published var rooms: [RoomMeta] = []
    @Published var claudeVia = "local"
    @Published var claudeModel = "claude-sonnet-5-5"
    @Published var busy = false
    @Published var consent: String? = nil        // "I cannot reach the local Claude Code. Do you want to use API credits?"
    @Published var notice = ""
    private var task: Task<Void, Never>?
    private var pendingTo = "auto"

    static func short(_ m: String) -> String { (m.split(separator: "-").dropFirst().first.map(String.init) ?? m).uppercased() }

    /// Claude's last line asked Queen something: ASK QUEEN with an empty box relays it.
    var canRelay: Bool {
        guard let last = messages.last(where: { $0.role == "claude" }) else { return false }
        return last.content.range(of: "ASK QUEEN:", options: .caseInsensitive) != nil
    }

    // ---------------------------------------------------------------- the room
    @MainActor
    func toggle() {
        active.toggle()
        if active { Capi.shared.active = false }
        if active && roomId.isEmpty { Task { await begin() } }
    }

    @MainActor
    func begin() async {
        await loadRooms()
        if let first = rooms.first { await open(first.id) } else { await newRoom() }
    }

    @MainActor
    func loadRooms() async {
        guard let j = await Queen.shared.json("/api/triple/list"), let list = j["rooms"] as? [[String: Any]] else { return }
        rooms = list.compactMap { r in
            guard let id = r["id"] as? String else { return nil }
            return RoomMeta(id: id, title: (r["title"] as? String) ?? "Triple chat", count: (r["count"] as? Int) ?? 0)
        }
    }

    @MainActor
    private func apply(_ room: [String: Any]) {
        roomId = (room["id"] as? String) ?? roomId
        title = (room["title"] as? String) ?? "Triple chat"
        claudeVia = (room["claude_via"] as? String) ?? "local"
        claudeModel = (room["claude_model"] as? String) ?? claudeModel
        let ms = (room["messages"] as? [[String: Any]]) ?? []
        messages = ms.compactMap { m in
            guard let s = m["speaker"] as? String else { return nil }
            return Msg(role: s, content: (m["text"] as? String) ?? "")
        }
    }

    @MainActor
    func open(_ id: String) async {
        guard !busy, let j = await Queen.shared.json("/api/triple/get?id=" + id), let room = j["room"] as? [String: Any] else { return }
        consent = nil
        apply(room)
    }

    @MainActor
    func newRoom() async {
        guard !busy, let j = await Queen.shared.json("/api/triple/new", body: [:]), let room = j["room"] as? [String: Any] else { return }
        consent = nil
        apply(room)
        await loadRooms()
    }

    @MainActor
    func setVia(_ via: String) {
        claudeVia = via
        consent = nil
        saveSettings()
    }

    @MainActor
    func setModel(_ m: String) {
        claudeModel = m
        saveSettings()
    }

    @MainActor
    private func saveSettings() {
        let body: [String: Any] = ["id": roomId, "claude_via": claudeVia, "claude_model": claudeModel]
        Task { _ = await Queen.shared.json("/api/triple/settings", body: body) }
    }

    // ---------------------------------------------------------------- one turn: to = queen | claude | both | auto
    @MainActor
    func send(_ text: String, to: String) {
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !busy, !roomId.isEmpty else { return }
        if t.isEmpty && !(to == "queen" && canRelay) { return }
        if !t.isEmpty { messages.append(Msg(role: "marko", content: t)) }
        run(text: t, to: to, allowApi: false, resume: false)
    }

    /// YES to "Do you want to use API credits?": the room switches to API and Claude answers what is already there.
    @MainActor
    func useApi() {
        guard !busy else { return }
        consent = nil
        claudeVia = "api"
        run(text: "", to: pendingTo, allowApi: true, resume: true)
    }

    @MainActor
    func declineApi() { consent = nil }

    @MainActor
    func stop() {
        task?.cancel()
        busy = false
    }

    @MainActor
    private func run(text: String, to: String, allowApi: Bool, resume: Bool) {
        busy = true
        consent = nil
        notice = ""
        pendingTo = to
        task = Task { @MainActor in
            await self.stream(text: text, to: to, allowApi: allowApi, resume: resume)
            self.busy = false
            if self.consent == nil, !Task.isCancelled { await self.reload() }   // the server's copy is the truth
            await self.loadRooms()
        }
    }

    @MainActor
    private func reload() async {
        guard let j = await Queen.shared.json("/api/triple/get?id=" + roomId), let room = j["room"] as? [String: Any] else { return }
        apply(room)
    }

    @MainActor
    private func appendToLast(_ s: String) {
        guard !messages.isEmpty else { return }
        messages[messages.count - 1].content += s
    }

    @MainActor
    private func stream(text: String, to: String, allowApi: Bool, resume: Bool) async {
        let body: [String: Any] = ["id": roomId, "text": text, "to": to, "allow_api": allowApi, "resume": resume]
        guard let r = Queen.shared.request("/api/triple/turn", body: body, timeout: 900) else { return }
        do {
            let (bytes, resp) = try await URLSession.shared.bytes(for: r)
            if let h = resp as? HTTPURLResponse, h.statusCode >= 400 {
                notice = "The room answered \(h.statusCode)."
                return
            }
            for try await l in bytes.lines {
                if Task.isCancelled { break }
                guard let o = try? JSONSerialization.jsonObject(with: Data(l.utf8)) as? [String: Any] else { continue }
                if let who = o["speaker"] as? String, o["start"] != nil { messages.append(Msg(role: who, content: "")) }
                if let tok = o["t"] as? String { appendToLast(tok) }
                if let c = o["need_consent"] as? String { consent = c }
                if let e = o["error"] as? String { notice = "ERROR: " + e }
            }
        } catch {
            if !Task.isCancelled { notice = "No answer: \(error.localizedDescription)" }
        }
        if Task.isCancelled { notice = "Stopped." }
    }
}

// ---------------------------------------------------------------- the window parts
/// The three speakers and the room's settings on one grid: who answers, how Claude is reached, which Claude.
struct TripleControls: View {
    @ObservedObject var t = Triple.shared
    @Binding var showRooms: Bool
    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(spacing: 4) {
                Text("CLAUDE VIA").foregroundStyle(Ink.dim).padding(.horizontal, 6)
                Word(text: "LOCAL", id: "via-local", color: t.claudeVia == "local" ? Ink.claude : Ink.grey,
                     help: "The local Claude Code on your plan: no credits") { t.setVia("local") }
                Word(text: "API", id: "via-api", color: t.claudeVia == "api" ? Ink.claude : Ink.grey,
                     help: "The Anthropic API: spends credits, booked in the spend ledger") { t.setVia("api") }
                Spacer(minLength: 4)
                Word(text: "ROOMS", id: "rooms", color: showRooms ? Ink.accent : Ink.text, help: "Your triple chat rooms") {
                    showRooms.toggle()
                    if showRooms { Task { await t.loadRooms() } }
                }
                Word(text: "NEW ROOM", id: "new-room", help: "A clean room for the three of you") { Task { await t.newRoom() } }
            }
            HStack(spacing: 4) {
                Text("CLAUDE").foregroundStyle(Ink.dim).padding(.horizontal, 6)
                ForEach(Triple.models, id: \.self) { m in
                    Word(text: Triple.short(m), id: "model-" + m, color: t.claudeModel == m ? Ink.claude : Ink.grey,
                         help: m) { t.setModel(m) }
                }
                Spacer(minLength: 0)
            }
        }
        .font(.system(size: 12, weight: .bold, design: .monospaced))
        .padding(.horizontal, 8).padding(.vertical, 2)
    }
}

struct RoomList: View {
    @ObservedObject var t = Triple.shared
    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 0) {
                ForEach(t.rooms) { r in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(r.title).font(.system(size: 13, weight: r.id == t.roomId ? .bold : .regular))
                            .foregroundStyle(r.id == t.roomId ? Ink.claude : Ink.text)
                            .fixedSize(horizontal: false, vertical: true)
                        Text("\(r.count) messages").font(.system(size: 11, design: .monospaced)).foregroundStyle(Ink.dim)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 12).padding(.vertical, 8)
                    .contentShape(Rectangle())
                    .onTapGesture { Task { await t.open(r.id) } }
                    .axButton("Room " + r.title, id: "room-" + r.id) { Task { await t.open(r.id) } }
                    .pressHover()
                    Hairline()
                }
            }
        }
        .background(Ink.panel)
    }
}

struct TripleConversation: View {
    @ObservedObject var t = Triple.shared
    var body: some View {
        MessageList(messages: t.messages,
                    empty: "Three brains in one room: you, Queen and Claude. Say \"Queen, what do you think?\" or \"Claude, how do we do this?\"; everyone hears everything. Queen can ask Claude, and Claude can suggest what Queen should do.",
                    notice: t.notice, trigger: t.consent == nil ? 0 : 1) {
            if let c = t.consent {
                        VStack(alignment: .leading, spacing: 6) {
                            Text(c).font(.system(size: 14)).foregroundStyle(Ink.amber)
                                .fixedSize(horizontal: false, vertical: true)
                            HStack(spacing: 8) {
                                Word(text: "YES, USE API CREDITS", id: "consent-yes", color: Ink.amber,
                                     help: "Switch this room to the API: Claude answers now and the cost is booked") { t.useApi() }
                                Word(text: "NO", id: "consent-no", color: Ink.grey) { t.declineApi() }
                            }
                            .font(.system(size: 12, weight: .bold, design: .monospaced))
                        }
                        .padding(16)
                    }
        }
    }
}

struct TripleInput: View {
    @ObservedObject var t = Triple.shared
    @State private var text = ""
    @FocusState private var focused: Bool
    var body: some View {
        VStack(spacing: 6) {
            TextField("Write to the room (name Queen or Claude, or use a word below)", text: $text, axis: .vertical)
                .textFieldStyle(.plain)
                .font(.system(size: 14))
                .foregroundStyle(Ink.text)
                .lineLimit(1...8)
                .focused($focused)
                .onSubmit { go("auto") }
                .padding(10)
                .background(RoundedRectangle(cornerRadius: 6).fill(Ink.panel))
                .overlay(RoundedRectangle(cornerRadius: 6).stroke(Ink.line, lineWidth: 1))
                .accessibilityIdentifier("triple-prompt")
            HStack(spacing: 6) {
                if t.busy {
                    Word(text: "STOP", id: "triple-stop", color: Ink.amber, help: "Stop the answer") { t.stop() }
                } else {
                    let has = !text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
                    Word(text: "ASK QUEEN", id: "ask-queen", color: (has || t.canRelay) ? Ink.accent : Ink.grey,
                         help: has ? "Queen answers" : "Empty box: Queen answers what Claude asked her") { go("queen") }
                    Word(text: "ASK CLAUDE", id: "ask-claude", color: has ? Ink.claude : Ink.grey, help: "Claude answers") { go("claude") }
                    Word(text: "ASK BOTH", id: "ask-both", color: has ? Ink.text : Ink.grey, help: "Queen answers, then Claude") { go("both") }
                }
                Spacer(minLength: 0)
            }
            .font(.system(size: 13, weight: .bold, design: .monospaced))
        }
        .padding(12)
        .onAppear { focused = true }
    }

    func go(_ to: String) {
        let s = text
        guard !t.busy else { return }
        if s.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && !(to == "queen" && t.canRelay) { return }
        text = ""
        t.send(s, to: to)
    }
}
