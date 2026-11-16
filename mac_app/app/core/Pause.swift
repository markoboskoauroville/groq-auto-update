// Pause.swift: PAUSE / RESUME / STATUS (Marko, 16.11.2026: "All our tools need to be paused at the same time and need
// to have this kind of API calls to be stopped."). One shared truth, ~/.groq/pause.json {"paused", "since"}, read and
// written by this app and by the Python backend (qwen_app/pause_state.py), so it survives a restart and reaches every hand.
// While paused: no new Groq/Claude call starts; a chat waits (queued) until resume, a route that would start work is
// answered at once {"paused":true,...}; a Groq stream in flight is cancelled cleanly (no ledger line, no cooled key, no
// half-written chat) and answered as "paused", never as an error.
import Foundation

final class PauseState {
    private let path: String
    private let cond = NSCondition()
    private var paused = false
    private var since: Double?
    private var mtime: Double = -1
    private var waiting = 0
    private var streams: [ObjectIdentifier: LineStream] = [:]
    private var applied = false
    var onChange: (Bool) -> Void = { _ in }

    init(_ cfg: QueenConfig) {
        path = cfg.groqDir + "/pause.json"
        load()
        applied = paused
        let t = Thread { [weak self] in
            while let me = self {
                me.poll()
                Thread.sleep(forTimeInterval: 0.3)
            }
        }
        t.name = "pause-watch"
        t.start()
    }

    private func fileMtime() -> Double {
        guard let a = try? FileManager.default.attributesOfItem(atPath: path), let d = a[.modificationDate] as? Date else { return -1 }
        return d.timeIntervalSince1970
    }

    /// Reads the file when it changed (the Python backend may have written it).
    private func load() {
        let m = fileMtime()
        cond.lock(); defer { cond.unlock() }
        if m == mtime { return }
        mtime = m
        if let d = Files.readJSON(path) as? [String: Any] {
            paused = (d["paused"] as? Bool) == true
            since = paused ? (d["since"] as? NSNumber)?.doubleValue : nil
        } else {
            paused = false
            since = nil
        }
    }

    /// A change seen (ours or the Python side's): cancel what is in flight, wake the waiting.
    private func poll() {
        load()
        cond.lock()
        let now = paused
        let changed = now != applied
        applied = now
        let toCancel = now ? Array(streams.values) : []
        cond.broadcast()
        cond.unlock()
        for s in toCancel { s.cancel() }
        if changed { onChange(now) }
    }

    var isPaused: Bool { load(); cond.lock(); defer { cond.unlock() }; return paused }

    func set(_ on: Bool) {
        load()
        cond.lock()
        if on == paused { cond.unlock(); return }
        paused = on
        since = on ? Date().timeIntervalSince1970 : nil
        let sv: Any = on ? ((since ?? 0) as Any) : (NSNull() as Any)
        let obj: [String: Any] = ["paused": on, "since": sv, "by": "queen-app"]
        cond.unlock()
        Files.writeAtomic(path, jsonBytes(obj))    // atomic: tmp + rename, never a half-written pause file
        mtime = fileMtime()
        poll()
    }

    var queued: Int { cond.lock(); defer { cond.unlock() }; return waiting }
    var sinceValue: Any { cond.lock(); defer { cond.unlock() }; return since.map { $0 as Any } ?? NSNull() }

    /// Blocks while paused (queued). true = resumed, false = still paused after maxWait.
    func waitWhilePaused(maxWait: Double) -> Bool {
        if !isPaused { return true }
        let deadline = Date().addingTimeInterval(maxWait)
        cond.lock()
        waiting += 1
        defer { waiting -= 1; cond.unlock() }
        while paused {
            load2()
            if !paused { break }
            if !cond.wait(until: min(deadline, Date().addingTimeInterval(0.5))) , Date() >= deadline { return !paused }
        }
        return true
    }

    // load() takes the lock itself; inside the waiting loop (lock held) re-read without re-locking
    private func load2() {
        let m = fileMtime()
        if m == mtime { return }
        mtime = m
        if let d = Files.readJSON(path) as? [String: Any] {
            paused = (d["paused"] as? Bool) == true
            since = paused ? (d["since"] as? NSNumber)?.doubleValue : nil
        } else { paused = false; since = nil }
    }

    func register(_ s: LineStream) {
        cond.lock(); streams[ObjectIdentifier(s)] = s; let p = paused; cond.unlock()
        if p { s.cancel() }
    }
    func unregister(_ s: LineStream) { cond.lock(); streams[ObjectIdentifier(s)] = nil; cond.unlock() }

    func statusJSON(extraQueued: Int = 0) -> [String: Any] {
        ["paused": isPaused, "since": sinceValue, "queued": queued + extraQueued]
    }

    /// 'pause' / 'resume' / 'pause status' typed in the chat: answered locally, $0. nil = not a pause command.
    func chatCommand(_ text: String) -> String? {
        let t = text.lowercased().replacingOccurrences(of: "!", with: " ").replacingOccurrences(of: ".", with: " ")
            .split(separator: " ").joined(separator: " ")
        switch t {
        case "pause", "pause all", "pause everything", "pause queen", "pause tools", "pause all tools":
            set(true)
            return "Paused. No new model or tool calls start; running ones stop between steps. Say 'resume' to go on."
        case "resume", "resume all", "resume everything", "resume queen", "unpause":
            set(false)
            return "Resumed. Queued work goes on."
        case "pause status", "paused", "am i paused", "are you paused", "queen pause status":
            if isPaused {
                let s = (sinceValue as? Double).map { Clock.format("HH:mm:ss", Date(timeIntervalSince1970: $0)) } ?? "?"
                return "Paused since \(s); \(queued) waiting."
            }
            return "Not paused."
        default: return nil
        }
    }

    /// Routes that stay answerable while paused (bookkeeping, pause itself). Anything else that is a POST is refused at once.
    static let exempt = ["/api/pause", "/api/resume", "/api/internal/", "/api/chats", "/api/keys", "/api/reset-keys",
                         "/api/supervisor", "/api/training", "/api/terminal/log", "/api/events"]
    static func isExempt(_ path: String) -> Bool { exempt.contains { path.hasPrefix($0) } }
}
