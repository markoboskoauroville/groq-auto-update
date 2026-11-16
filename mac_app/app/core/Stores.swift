// Stores.swift: chats, supervisor approvals, training events, the live event stream (Phase A, 14.11.2026).
// Ports of app.py (chats), supervisor.py and training_log.py on the same files in ~/.groq, same fields.
import Foundation

// ---------------------------------------------------------------- chats (~/.groq/chats/<id>.json)
enum Chats {
    static func path(_ cfg: QueenConfig, _ id: String) -> String {
        let allowed = CharacterSet(charactersIn: "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-")
        var safe = ""
        for u in id.unicodeScalars where allowed.contains(u) { safe.unicodeScalars.append(u) }
        if safe.isEmpty { safe = "unknown" }
        return cfg.groqDir + "/chats/" + safe + ".json"
    }

    static func autoTitle(_ messages: [Any]) -> String {
        for case let m as [String: Any] in messages where (m["role"] as? String) == "user" {
            var text = ((m["content"] as? String) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            if text.contains("--- FILE:") {
                text = (text.components(separatedBy: "\n\n").last ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            }
            if !text.isEmpty {
                var title = pyPrefix(text, 50)
                if pyLen(text) > 50 {
                    if let sp = title.range(of: " ", options: .backwards) { title = String(title[title.startIndex..<sp.lowerBound]) }
                    title += "…"
                }
                return title
            }
        }
        return "New Chat"
    }

    static func list(_ cfg: QueenConfig) -> [[String: Any]] {
        let dir = cfg.groqDir + "/chats"
        try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        let names = ((try? FileManager.default.contentsOfDirectory(atPath: dir)) ?? []).filter { $0.hasSuffix(".json") }
        let sorted = names.map { ($0, Files.mtime(dir + "/" + $0)) }.sorted { $0.1 > $1.1 }
        var out: [[String: Any]] = []
        for (n, _) in sorted {
            guard let d = Files.readJSON(dir + "/" + n) as? [String: Any] else { continue }
            out.append(["id": d["id"] ?? String(n.dropLast(5)), "title": d["title"] ?? "Untitled",
                        "message_count": ((d["messages"] as? [Any]) ?? []).count,
                        "updated_at": d["updated_at"] ?? "", "created_at": d["created_at"] ?? ""])
        }
        return out
    }

    static func writeChat(_ p: String, _ o: [String: Any]) -> Bool {
        guard JSONSerialization.isValidJSONObject(o),
              let d = try? JSONSerialization.data(withJSONObject: o, options: [.withoutEscapingSlashes]) else { return false }
        return Files.writeAtomic(p, d)
    }
}

// ---------------------------------------------------------------- supervisor (~/.groq/approvals/<id>.json)
enum Supervisor {
    struct Failure: Error { let message: String }

    static func dir(_ cfg: QueenConfig) -> String { cfg.groqDir + "/approvals" }

    static func path(_ cfg: QueenConfig, _ id: String) throws -> String {
        if id.isEmpty || id.contains("/") || id.contains("..") { throw Failure(message: "bad id") }
        return dir(cfg) + "/" + id + ".json"
    }

    static func write(_ p: String, _ rec: [String: Any]) {
        if JSONSerialization.isValidJSONObject(rec),
           let d = try? JSONSerialization.data(withJSONObject: rec, options: [.prettyPrinted, .withoutEscapingSlashes]) {
            Files.writeAtomic(p, d)
        }
    }

    static func propose(_ cfg: QueenConfig, task: String, step: String, summary: String, detail: String) -> String {
        try? FileManager.default.createDirectory(atPath: dir(cfg), withIntermediateDirectories: true)
        let id = Clock.format("HHmmss") + "-" + randomHex(6)
        let rec: [String: Any] = ["id": id, "task": task, "step": step, "summary": summary, "detail": detail,
                                  "status": "pending", "asked": Clock.stamp, "turn": NSNull()]
        if let p = try? path(cfg, id) { write(p, rec) }
        return id
    }

    static func get(_ cfg: QueenConfig, _ id: String) throws -> [String: Any] {
        let p = try path(cfg, id)
        guard let r = Files.readJSON(p) as? [String: Any] else {
            throw Failure(message: "[Errno 2] No such file or directory: '\(p)'")
        }
        return r
    }

    static func decide(_ cfg: QueenConfig, _ id: String, _ decision: String, note: String, by: String) throws -> [String: Any] {
        var rec = try get(cfg, id)
        let st = (rec["status"] as? String) ?? ""
        if st != "pending" { throw Failure(message: "\(id) is already \(st)") }
        if decision != "approve" && decision != "reject" { throw Failure(message: "decision is approve or reject") }
        rec["status"] = decision == "approve" ? "approved" : "rejected"
        rec["note"] = note
        rec["by"] = by
        rec["decided"] = Clock.stamp
        let p = try path(cfg, id)
        write(p, rec)
        Training.logVerdict(cfg, rec)
        return rec
    }

    static func all(_ cfg: QueenConfig) -> [(String, [String: Any])] {
        try? FileManager.default.createDirectory(atPath: dir(cfg), withIntermediateDirectories: true)
        let names = ((try? FileManager.default.contentsOfDirectory(atPath: dir(cfg))) ?? []).filter { $0.hasSuffix(".json") }
        return names.compactMap { n in (Files.readJSON(dir(cfg) + "/" + n) as? [String: Any]).map { (n, $0) } }
    }

    static func pending(_ cfg: QueenConfig) -> [[String: Any]] {
        all(cfg).sorted { $0.0 < $1.0 }.map { $0.1 }.filter { ($0["status"] as? String) == "pending" }
    }

    static func recent(_ cfg: QueenConfig, _ n: Int) -> [[String: Any]] {
        let d = dir(cfg)
        return all(cfg).sorted { Files.mtime(d + "/" + $0.0) > Files.mtime(d + "/" + $1.0) }.prefix(n).map { $0.1 }
    }
}

// ---------------------------------------------------------------- training (~/.groq/training/events/<date>.jsonl)
enum Training {
    static func record(_ cfg: QueenConfig, _ kind: String, _ data: [String: Any]) {
        var ev = data
        ev["kind"] = kind
        ev["at"] = Clock.iso
        guard JSONSerialization.isValidJSONObject(ev),
              let d = try? JSONSerialization.data(withJSONObject: ev, options: [.withoutEscapingSlashes]) else { return }
        Files.appendLine(cfg.groqDir + "/training/events/" + Clock.day + ".jsonl", String(decoding: d, as: UTF8.self))
    }

    static func logVerdict(_ cfg: QueenConfig, _ rec: [String: Any]) {
        let detail = (rec["detail"] as? String) ?? ""
        record(cfg, "verdict", ["turn": rec["turn"] ?? NSNull(), "proposal": rec["id"] ?? NSNull(),
                                "task": rec["task"] ?? NSNull(), "step": rec["step"] ?? NSNull(),
                                "summary": rec["summary"] ?? NSNull(), "detail": pyPrefix(detail, 8000),
                                "decision": rec["status"] ?? NSNull(), "note": rec["note"] ?? "", "by": rec["by"] ?? ""])
    }

    static func lastTurn(_ cfg: QueenConfig) -> String? {
        let dir = cfg.groqDir + "/training/events"
        let files = ((try? FileManager.default.contentsOfDirectory(atPath: dir)) ?? []).filter { $0.hasSuffix(".jsonl") }.sorted()
        var last: String?
        for f in files {
            for line in (Files.read(dir + "/" + f) ?? "").components(separatedBy: "\n") where !line.isEmpty {
                if let o = try? JSONSerialization.jsonObject(with: Data(line.utf8)) as? [String: Any],
                   (o["kind"] as? String) == "output", let t = o["turn"] as? String { last = t }
            }
        }
        return last
    }
}

// ---------------------------------------------------------------- /api/events
/// The live event stream (app.py broadcast_event / sse_events): at most 12 listeners, the oldest is let go; a listener
/// that falls 100 events behind is dropped. Events are kept as JSON text so the backend's events pass through as they are.
final class EventHub {
    final class Listener {
        let cond = NSCondition()
        var queue: [Data] = []
        var closed = false
    }
    static let maxListeners = 12
    private let lock = NSLock()
    private var listeners: [Listener] = []

    func subscribe() -> Listener {
        let l = Listener()
        lock.lock()
        while listeners.count >= EventHub.maxListeners {
            let old = listeners.removeFirst()
            old.cond.lock()
            old.queue.append(jsonBytes(["type": "closed", "why": "a newer page took this slot"]))
            old.closed = true
            old.cond.broadcast()
            old.cond.unlock()
        }
        listeners.append(l)
        lock.unlock()
        return l
    }

    func unsubscribe(_ l: Listener) {
        lock.lock()
        listeners.removeAll { $0 === l }
        lock.unlock()
    }

    var count: Int { lock.lock(); defer { lock.unlock() }; return listeners.count }

    func broadcast(_ ev: [String: Any]) { broadcastRaw(jsonBytes(ev)) }

    func broadcastRaw(_ d: Data) {
        lock.lock()
        var dead: [Listener] = []
        for l in listeners {
            l.cond.lock()
            if l.queue.count >= 100 { dead.append(l) } else { l.queue.append(d); l.cond.broadcast() }
            l.cond.unlock()
        }
        listeners.removeAll { l in dead.contains { $0 === l } }
        lock.unlock()
    }

    /// The next event for a listener; nil after `timeout` seconds (time for a ping).
    func next(_ l: Listener, timeout: Double) -> Data? {
        l.cond.lock(); defer { l.cond.unlock() }
        let until = Date().addingTimeInterval(timeout)
        while l.queue.isEmpty {
            if !l.cond.wait(until: until) { return nil }
        }
        return l.queue.removeFirst()
    }
}

// ---------------------------------------------------------------- the local Claude Code (claude_link.py)
/// Queen <-> the local Claude Code on Marko's plan, headless `claude -p`, never an API key. The consent gate stays:
/// Claude Code not reachable -> 409 {need_consent, message: "I cannot reach the local Claude Code. Do you want to use API credits?"}.
final class ClaudeLink {
    static let consentText = "I cannot reach the local Claude Code. Do you want to use API credits?"
    static let headlessNote = "You are answering QUEEN, headless, through `claude -p`: no human is watching this run. "
        + "Do not speak (no langsay or voice), no handover report, no greeting, no questions back. "
        + "Do only what the request asks and answer with the result in plain text."

    enum Failure: Error {
        case needConsent
        case bad(String)        // ValueError / RuntimeError -> 400
        case timeout            // -> 504
    }

    private let cfg: QueenConfig
    private let lock = NSLock()
    private var cached: (Double, [String: Any])?

    init(_ cfg: QueenConfig) { self.cfg = cfg }

    func env() -> [String: String] {
        var e = ProcessInfo.processInfo.environment.filter {
            !($0.key.hasPrefix("CLAUDE") || $0.key == "ANTHROPIC_API_KEY" || $0.key == "ANTHROPIC_AUTH_TOKEN")
        }
        let bin = (cfg.claude as NSString).deletingLastPathComponent
        e["PATH"] = bin + ":" + cfg.fullPath
        e["HOME"] = cfg.userHome
        return e
    }

    func status(force: Bool = false) -> [String: Any] {
        lock.lock()
        if !force, let c = cached, Clock.now - c.0 < 60 { lock.unlock(); return c.1 }
        lock.unlock()
        var v: [String: Any] = ["reachable": false, "why": ""]
        if !FileManager.default.fileExists(atPath: cfg.claude) {
            v["why"] = "no Claude Code at \(cfg.claude)"
        } else {
            let r = runProcess(cfg.claude, ["auth", "status"], env: env(), timeout: 20)
            if r.timedOut {
                v["why"] = "auth check failed: TimeoutExpired"
            } else {
                let a = (try? JSONSerialization.jsonObject(with: Data((r.out.isEmpty ? "{}" : r.out).utf8)) as? [String: Any]) ?? nil
                if a == nil {
                    v["why"] = "auth check failed: JSONDecodeError: \(String(r.out.prefix(120)))"
                } else if (a?["loggedIn"] as? Bool) != true {
                    v["why"] = "Claude Code is not logged in"
                } else if (a?["authMethod"] as? String) != "claude.ai" {
                    v["why"] = "Claude Code is logged in by \(a?["authMethod"] ?? "None"), not the claude.ai plan"
                } else {
                    v = ["reachable": true, "why": "", "auth": "claude.ai plan"]
                }
            }
        }
        lock.lock()
        cached = (Clock.now, v)
        lock.unlock()
        return v
    }

    func ask(_ question: String, model: String = "sonnet", timeout: Double = 600) throws -> [String: Any] {
        guard (status()["reachable"] as? Bool) == true else { throw Failure.needConsent }
        let work = cfg.groqDir + "/claude_link"
        let args = ["-p", question, "--output-format", "json", "--no-session-persistence", "--model", model,
                    "--append-system-prompt", ClaudeLink.headlessNote, "--disallowedTools", "Bash"]
        let r = runProcess(cfg.claude, args, env: env(), cwd: work, timeout: timeout)
        if r.timedOut { throw Failure.timeout }
        guard let d = try? JSONSerialization.jsonObject(with: Data(r.out.utf8)) as? [String: Any] else {
            let tail = (r.err.isEmpty ? r.out : r.err).prefix(300)
            throw Failure.bad("Claude Code gave no answer (rc \(r.code)): \(tail)")
        }
        if (d["is_error"] as? Bool) == true {
            throw Failure.bad("Claude Code: \(d["result"] ?? d["subtype"] ?? "error")")
        }
        return ["answer": d["result"] ?? "", "duration_ms": d["duration_ms"] ?? NSNull(), "via": "local Claude Code (plan)",
                "model": model, "turns": d["num_turns"] ?? NSNull()]
    }

    private func hub(_ args: [String], timeout: Double = 30) -> ProcResult {
        runProcess("/usr/bin/env", ["python3", cfg.hub + "/other_sessions.py"] + args, env: env(), timeout: timeout)
    }

    func sessions() throws -> [Any] {
        if !FileManager.default.fileExists(atPath: cfg.hub + "/other_sessions.py") { return [] }
        let r = hub(["json"])
        if r.code != 0 { throw Failure.bad("other_sessions.py json failed: \(r.err.trimmingCharacters(in: .whitespacesAndNewlines).prefix(200))") }
        return (try? JSONSerialization.jsonObject(with: Data((r.out.isEmpty ? "[]" : r.out).utf8)) as? [Any]) ?? []
    }

    func transcript(_ sidRaw: String, n: Int) throws -> [String: Any] {
        let sid = sidRaw.trimmingCharacters(in: .whitespacesAndNewlines)
        if sid.isEmpty || sid.contains("/") || sid.contains("..") { throw Failure.bad("pass sid=<session id>") }
        let projects = cfg.userHome + "/.claude/projects"
        let dirs = ((try? FileManager.default.contentsOfDirectory(atPath: projects)) ?? []).sorted()
        guard let hit = dirs.map({ projects + "/" + $0 + "/" + sid + ".jsonl" }).first(where: { FileManager.default.fileExists(atPath: $0) }) else {
            throw Failure.bad("no transcript for \(sid)")
        }
        var turns: [[String: Any]] = []
        let text = String(decoding: FileManager.default.contents(atPath: hit) ?? Data(), as: UTF8.self)
        for line in text.components(separatedBy: "\n") where !line.isEmpty {
            guard let e = try? JSONSerialization.jsonObject(with: Data(line.utf8)) as? [String: Any],
                  let type = e["type"] as? String, type == "user" || type == "assistant" else { continue }
            var c: Any? = (e["message"] as? [String: Any])?["content"]
            if let list = c as? [Any] {
                c = list.compactMap { x -> String? in
                    guard let d = x as? [String: Any], (d["type"] as? String) == "text" else { return nil }
                    return (d["text"] as? String) ?? ""
                }.joined(separator: " ")
            }
            if let s = c as? String {
                let t = s.trimmingCharacters(in: .whitespacesAndNewlines)
                if !t.isEmpty && !s.drop(while: { $0.isWhitespace }).hasPrefix("<") {
                    turns.append(["role": type, "when": e["timestamp"] ?? "", "text": pyPrefix(t, 4000)])
                }
            }
        }
        let k = n > 0 ? n : 20
        return ["sid": sid, "file": hit, "turns": Array(turns.suffix(k))]
    }

    func tell(_ sid: String, _ text: String) throws -> [String: Any] {
        let r = hub(["type", sid, "[Queen] \(text)"])
        if r.code != 0 {
            throw Failure.bad("could not type into \(sid): \((r.err.isEmpty ? r.out : r.err).trimmingCharacters(in: .whitespacesAndNewlines).prefix(200))")
        }
        return ["typed": true, "sid": sid]
    }
}
