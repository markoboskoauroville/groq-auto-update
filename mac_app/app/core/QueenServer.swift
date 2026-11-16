// QueenServer.swift: Queen on 127.0.0.1:8765, served by the Swift app itself (Phase A, Marko 14.11.2026: "one Queen
// only, the Swift app, no Flask server behind it, done in phases").
//
// NATIVE here (same paths, same JSON / NDJSON / SSE shapes as app.py):
//   /health  /api/version  /api/app/status  /api/models  /api/billing  /api/chat  /api/events  /api/session/messages
//   /api/remote/send  /api/chats  /api/chats/<id>  /api/chats/save|rename|delete  /api/keys  /api/keys/import|upload|
//   delete|clear|load-file  /api/reset-keys  /api/claude/ask|tell|status|sessions|transcript  /api/supervisor/*
//   /api/skills/list  /api/training/correct|status|build
// PROXIED, unchanged and streamed, to the Python backend on 127.0.0.1:8766 (~/.groq/backend_port): every other route.
// /api/chat asks the backend for two things that stay in Python in Phase A: the local chat commands (before Groq is
// called: POST /api/internal/local_command) and the after-turn work (training log, her command lines run, handover:
// POST /api/internal/after_turn). Backend down = no local commands, Groq still answers.
import Foundation

let MAX_MESSAGES = 80
let CODE_BOX_CHAT = "You are in CODE BOX mode. Provide ONLY executable code formatted in a single clean markdown code block with appropriate language tag. No pleasantries, no conversational preamble, no closing text."
let CODE_BOX_REMOTE = "You are in CODE BOX mode. Provide ONLY the code solution. Format the code inside a single clean markdown code block with appropriate language tag. No pleasantries, no conversational preamble, no closing text."
let SECURITY_DROP = ["connection", "keep-alive", "transfer-encoding", "content-length", "expect", "proxy-connection"]

final class QueenServer {
    let cfg: QueenConfig
    let pool: KeyPool
    let ledger: Ledger
    let groq: GroqClient
    let prompt: PromptBuilder
    let claude: ClaudeLink
    let events = EventHub()
    let token: String
    private(set) var http: HTTPServer!
    private let msgLock = NSLock()
    private var activeMessages: [[String: Any]] = []
    private var relayRunning = false
    var backendUp: () -> Bool = { true }
    var backendInfo: () -> [String: Any] = { [:] }

    init(_ cfg: QueenConfig) {
        self.cfg = cfg
        pool = KeyPool(cfg)
        ledger = Ledger(cfg)
        groq = GroqClient(cfg, pool)
        prompt = PromptBuilder(cfg)
        claude = ClaudeLink(cfg)
        token = LocalToken.ensure(cfg)
        http = HTTPServer { [unowned self] req, res in self.handle(req, res) }
        http.raw = { [unowned self] req, sock in self.rawRoute(req, sock) }
    }

    /// Binds and serves. Throws ServerError (inUse when another program holds the port).
    @discardableResult
    func start(port: UInt16) throws -> UInt16 {
        let p = try http.start(port: port)
        startRelay()
        return p
    }

    func stop() { http.stop() }

    // ------------------------------------------------------------ security (app.py local_api_security_guard)
    static func trustedLocal(_ s: String) -> Bool {
        guard let u = URLComponents(string: s), let scheme = u.scheme?.lowercased(), scheme == "http" || scheme == "https",
              let h = u.host?.lowercased() else { return false }
        return h == "127.0.0.1" || h == "localhost"
    }

    func guardCheck(_ r: HTTPRequest) -> (Int, [String: Any])? {
        guard r.path.hasPrefix("/api/") else { return nil }
        if r.method == "OPTIONS" { return (403, ["ok": false, "error": "Cross-origin preflight rejected"]) }
        let sent = (r.header("X-Queen-Token") ?? "").trimmingCharacters(in: .whitespaces)
        if !sent.isEmpty && sent == token { return nil }
        if (r.header("Sec-Fetch-Site") ?? "").lowercased() == "cross-site" {
            return (403, ["ok": false, "error": "Blocked cross-site browser request to local Queen API"])
        }
        let origin = (r.header("Origin") ?? "").trimmingCharacters(in: .whitespaces)
        if !origin.isEmpty && (origin == "null" || !QueenServer.trustedLocal(origin)) {
            return (403, ["ok": false, "error": "Untrusted Origin '\(origin)' blocked by Queen security guard"])
        }
        let ref = (r.header("Referer") ?? "").trimmingCharacters(in: .whitespaces)
        if !ref.isEmpty && !QueenServer.trustedLocal(ref) {
            return (403, ["ok": false, "error": "Untrusted Referer blocked by Queen security guard"])
        }
        return nil
    }

    // ------------------------------------------------------------ routing
    static let native: Set<String> = [
        "GET /health", "GET /api/version", "GET /api/app/status", "GET /api/models", "GET /api/billing",
        "POST /api/chat", "GET /api/events", "GET /api/session/messages", "POST /api/remote/send",
        "GET /api/chats", "POST /api/chats/save", "POST /api/chats/rename", "POST /api/chats/delete",
        "GET /api/keys", "POST /api/keys/import", "POST /api/keys/upload", "POST /api/keys/delete", "POST /api/keys/clear",
        "POST /api/keys/load-file", "POST /api/reset-keys",
        "GET /api/claude/status", "GET /api/claude/sessions", "GET /api/claude/transcript", "POST /api/claude/ask",
        "POST /api/claude/tell",
        "POST /api/supervisor/propose", "GET /api/supervisor/pending", "GET /api/supervisor/get",
        "GET /api/supervisor/recent", "POST /api/supervisor/decide", "GET /api/skills/list",
        "POST /api/training/correct", "GET /api/training/status", "POST /api/training/build",
        "GET /", "HEAD /",
    ]

    func isNative(_ r: HTTPRequest) -> Bool {
        // a key upload as a file (multipart) stays with Python (the old page used it; the pool reads keys.txt after)
        if r.method == "POST" && (r.path == "/api/keys/import" || r.path == "/api/keys/upload"),
           (r.header("Content-Type") ?? "").lowercased().hasPrefix("multipart/") { return false }
        if QueenServer.native.contains(r.method + " " + r.path) { return true }
        if r.method == "GET", r.path.hasPrefix("/api/chats/"), r.path.count > "/api/chats/".count,
           !r.path.dropFirst("/api/chats/".count).contains("/") { return true }
        return false
    }

    /// Takes the request before the handler when it must be piped: the guard, then the proxy.
    private func rawRoute(_ r: HTTPRequest, _ s: Sock) -> Bool {
        if let (code, body) = guardCheck(r) {
            let res = Responder(s, http10: r.version == "HTTP/1.0")
            res.json(code, body)
            return true
        }
        if isNative(r) { return false }
        proxy(r, s)
        return true
    }

    func handle(_ r: HTTPRequest, _ res: Responder) {
        let key = r.method + " " + r.path
        switch key {
        case "GET /", "HEAD /":
            res.text(200, "Queen is the Swift app Queen. This is her API on http://127.0.0.1:8765.\n")
        case "GET /health": res.json(health())
        case "GET /api/version": res.json(version())
        case "GET /api/app/status": res.json(appStatus())
        case "GET /api/models": res.json(models())
        case "GET /api/billing": res.json(billing())
        case "POST /api/chat": chat(r, res)
        case "GET /api/events": sse(res)
        case "GET /api/session/messages":
            msgLock.lock(); let m = activeMessages; msgLock.unlock()
            res.json(["messages": m, "count": m.count])
        case "POST /api/remote/send": remoteSend(r, res)
        case "GET /api/chats":
            let c = Chats.list(cfg)
            res.json(["ok": true, "chats": c, "count": c.count])
        case "POST /api/chats/save": chatSave(r, res)
        case "POST /api/chats/rename": chatRename(r, res)
        case "POST /api/chats/delete": chatDelete(r, res)
        case "GET /api/keys": res.json(keysInfo())
        case "POST /api/keys/import", "POST /api/keys/upload": keysImport(r, res)
        case "POST /api/keys/delete": keysDelete(r, res)
        case "POST /api/keys/clear":
            pool.clear()
            events.broadcast(["type": "keys_cleared"])
            res.json(["ok": true, "count": 0, "items": [Any](), "message": "All API keys cleared from manager."])
        case "POST /api/keys/load-file": keysLoadFile(r, res)
        case "POST /api/reset-keys":
            pool.reset()
            res.json(["ok": true, "count": pool.count, "items": pool.statusRich(), "message": "Key cooldowns reset."])
        case "GET /api/claude/status":
            claudeWrap(res) {
                var s = self.claude.status(force: r.query["force"] == "1")
                s["live_sessions"] = try self.claude.sessions().count
                return s
            }
        case "GET /api/claude/sessions": claudeWrap(res) { ["sessions": try self.claude.sessions()] }
        case "GET /api/claude/transcript":
            claudeWrap(res) { try self.claude.transcript(r.query["sid"] ?? "", n: Int(r.query["n"] ?? "20") ?? 20) }
        case "POST /api/claude/ask":
            let d = r.json
            let q = ((d["question"] as? String) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            if q.isEmpty { res.json(400, ["ok": false, "error": "pass {question}"]); return }
            let model = (d["model"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? "sonnet"
            claudeWrap(res) { try self.claude.ask(q, model: model) }
        case "POST /api/claude/tell":
            let d = r.json
            claudeWrap(res) { try self.claude.tell((d["sid"] as? String) ?? "", (d["text"] as? String) ?? "") }
        case "POST /api/supervisor/propose":
            let d = r.json
            func s(_ k: String) -> String { (d[k] as? String) ?? "" }
            res.json(["ok": true, "id": Supervisor.propose(cfg, task: s("task"), step: s("step"), summary: s("summary"), detail: s("detail"))])
        case "GET /api/supervisor/pending": res.json(["ok": true, "pending": Supervisor.pending(cfg)])
        case "GET /api/supervisor/get":
            do {
                var o = try Supervisor.get(cfg, r.query["id"] ?? "")
                o["ok"] = true
                res.json(o)
            } catch { res.json(404, ["ok": false, "error": (error as? Supervisor.Failure)?.message ?? "\(error)"]) }
        case "GET /api/supervisor/recent":
            res.json(["ok": true, "recent": Supervisor.recent(cfg, Int(r.query["n"] ?? "40") ?? 40)])
        case "POST /api/supervisor/decide":
            let d = r.json
            do {
                let by = (d["by"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? "Claude Code"
                var o = try Supervisor.decide(cfg, (d["id"] as? String) ?? "", (d["decision"] as? String) ?? "",
                                              note: (d["note"] as? String) ?? "", by: by)
                o["ok"] = true
                res.json(o)
            } catch { res.json(400, ["ok": false, "error": (error as? Supervisor.Failure)?.message ?? "\(error)"]) }
        case "GET /api/skills/list":
            let names = ((try? FileManager.default.contentsOfDirectory(atPath: cfg.skills)) ?? []).filter { $0.hasSuffix(".md") }.sorted()
            let out = names.map { ["name": String($0.dropLast(3)), "text": Files.read(cfg.skills + "/" + $0) ?? ""] }
            res.json(["ok": true, "skills": out])
        case "POST /api/training/correct": trainingCorrect(r, res)
        case "GET /api/training/status": trainingHelper(r, res, call: "status()")
        case "POST /api/training/build":
            let force = (r.json["force"] as? Bool) == true
            trainingHelper(r, res, call: "build(force=\(force ? "True" : "False"))")
        default:
            if r.method == "GET", r.path.hasPrefix("/api/chats/") {
                chatGet(String(r.path.dropFirst("/api/chats/".count)), res)
            } else {
                res.json(404, ["ok": false, "error": "not found"])
            }
        }
    }

    // ------------------------------------------------------------ proxy to the Python backend
    func proxy(_ r: HTTPRequest, _ client: Sock) {
        let port = cfg.backendPort
        guard let up = Sock.open(port: port, timeout: 3600) else {
            let res = Responder(client, http10: r.version == "HTTP/1.0")
            res.json(502, ["ok": false, "error": "Queen's backend (127.0.0.1:\(port)) is not running: \(r.path) lives there in Phase A. It restarts by itself within 20 s; START QUEEN starts it now."])
            return
        }
        defer { up.shut() }
        var head = "\(r.method) \(r.target) \(r.version == "HTTP/1.0" ? "HTTP/1.0" : "HTTP/1.1")\r\n"
        for (k, v) in r.headers where !SECURITY_DROP.contains(k.lowercased()) { head += "\(k): \(v)\r\n" }
        if !r.body.isEmpty || r.method == "POST" || r.method == "PUT" || r.method == "PATCH" { head += "Content-Length: \(r.body.count)\r\n" }
        head += "Connection: close\r\n\r\n"
        guard up.write(head), r.body.isEmpty || up.write(r.body) else { return }
        while let chunk = up.readSome() {
            if !client.write(chunk) { break }
        }
    }

    /// One JSON call to the backend (internal routes). nil = backend down.
    func backend(_ method: String, _ path: String, _ body: [String: Any]? = nil, timeout: Double = 30) -> LocalResponse? {
        LocalHTTP.call(port: cfg.backendPort, method: method, path: path, body: body.map { jsonBytes($0) },
                       headers: [("X-Queen-Token", token)], timeout: timeout)
    }

    func markDirty() {
        DispatchQueue.global().async { _ = self.backend("POST", "/api/internal/mark_dirty", [:], timeout: 5) }
    }

    /// The backend's events reach /api/events here too (task chat, its key failovers, auto-update...).
    private func startRelay() {
        if relayRunning { return }
        relayRunning = true
        let t = Thread { [weak self] in
            while let me = self {
                let port = me.cfg.backendPort
                if me.events.count > 0, let s = Sock.open(port: port, timeout: 60) {
                    s.write("GET /api/events HTTP/1.0\r\nHost: 127.0.0.1\r\nX-Queen-Token: \(me.token)\r\n\r\n")
                    if let h = LocalHTTP.readHead(s), h.0 == 200 {
                        while let line = s.readLine() {
                            guard line.hasPrefix("data: ") else { continue }
                            let payload = Data(line.dropFirst(6).utf8)
                            let o = (try? JSONSerialization.jsonObject(with: payload)) as? [String: Any]
                            let type = (o?["type"] as? String) ?? ""
                            if type == "init" || type == "closed" { continue }
                            me.events.broadcastRaw(payload)
                        }
                    }
                    s.shut()
                }
                Thread.sleep(forTimeInterval: 3)
            }
        }
        t.name = "queen-events-relay"
        t.start()
    }

    // ------------------------------------------------------------ small routes
    func health() -> [String: Any] {
        ["app": "groq-modern-chat", "version": prompt.version(), "ok": true, "default_model": DEFAULT_MODEL,
         "has_keys": pool.count > 0, "face": "swift"]
    }

    func version() -> [String: Any] {
        let d = (Files.readJSON(cfg.versionFile) as? [String: Any]) ?? [:]
        let log = (d["log"] as? [Any]) ?? []
        return ["version": d["version"] ?? 1, "version_str": prompt.version(), "updated_at": d["updated_at"] ?? "",
                "auto_update_repo": "markoboskoauroville/groq-auto-update", "log": Array(log.suffix(10))]
    }

    func appStatus() -> [String: Any] {
        let l = ledger.load()
        let items = pool.statusRich()
        let cooling = items.filter { ($0["state_type"] as? String) == "cooling" }.count
        let first = pool.first
        return ["ok": true, "version": prompt.version(), "model": DEFAULT_MODEL, "keys": items.count, "cooling": cooling,
                "active_key": first.map { KeyPool.mask($0) as Any } ?? NSNull(),
                "total_spent": pyRound(Ledger.num(l["total_spent"]), 6), "prompts": Ledger.int(l["prompts_count"]),
                "location": cfg.location, "pid": Int(ProcessInfo.processInfo.processIdentifier),
                "face": "swift", "app_version": cfg.appVersion, "backend": backendInfo(), "prompt_source": prompt.source]
    }

    func models() -> [String: Any] {
        guard let key = pool.first else {
            return ["models": FALLBACK_MODELS, "default": DEFAULT_MODEL, "pricing": ledger.mergedPricing, "needs_key": true]
        }
        guard let got = groq.models(key: key) else {
            return ["models": FALLBACK_MODELS, "default": DEFAULT_MODEL, "pricing": ledger.mergedPricing, "error": "Connection error."]
        }
        let (status, j, _) = got
        if status >= 400 {
            return ["models": FALLBACK_MODELS, "default": DEFAULT_MODEL, "pricing": ledger.mergedPricing,
                    "error": GroqClient.errorText(status, jsonBytes(j))]
        }
        var chat: [String] = []
        for m in (j["data"] as? [[String: Any]]) ?? [] {
            guard let id = m["id"] as? String else { continue }
            if !id.contains("whisper") && !id.contains("guard") { chat.append(id) }
            if let p = m["pricing"] as? [String: Any] {
                var pin = Ledger.num(p["prompt"] ?? p["input"]), pout = Ledger.num(p["completion"] ?? p["output"])
                if pin > 0 && pin < 0.01 { pin *= 1_000_000; pout *= 1_000_000 }
                if pin > 0 || pout > 0 { ledger.livePricing[id] = (pyRound(pin, 4), pyRound(pout, 4)) }
            }
        }
        if chat.isEmpty { chat = FALLBACK_MODELS }
        return ["models": chat, "default": DEFAULT_MODEL, "pricing": ledger.mergedPricing]
    }

    func billing() -> [String: Any] {
        let l = ledger.load()
        var out: [String: Any] = [
            "total_spent": pyRound(Ledger.num(l["total_spent"]), 6), "total_tokens": Ledger.int(l["total_tokens"]),
            "total_prompt_tokens": Ledger.int(l["total_prompt_tokens"]),
            "total_completion_tokens": Ledger.int(l["total_completion_tokens"]),
            "prompts_count": Ledger.int(l["prompts_count"]),
            "recent_history": Array(((l["history"] as? [Any]) ?? []).suffix(15)),
            "pricing": Ledger.pricingJSON(MODEL_PRICING),
        ]
        var api: [String: Any] = ["confirmed": false, "ok": false]
        if pool.count == 0 {
            api = ["ok": false, "confirmed": false, "error": "No API key configured. Click '📥 Import Keys' to add your key file."]
        } else {
            pool.reload()
            for key in pool.keys {
                guard let got = groq.models(key: key) else { api["error"] = "Connection error."; continue }
                let (status, j, h) = got
                if status >= 400 { api["error"] = GroqClient.errorText(status, jsonBytes(j)); continue }
                api = ["ok": true, "confirmed": true, "region": h["x-groq-region"] ?? "fra",
                       "request_id": h["x-request-id"] ?? "live-check",
                       "rate_limit_limit_requests": h["x-ratelimit-limit-requests"] ?? "500000",
                       "rate_limit_limit_tokens": h["x-ratelimit-limit-tokens"] ?? "250000",
                       "rate_limit_remaining_requests": h["x-ratelimit-remaining-requests"] ?? "N/A",
                       "rate_limit_remaining_tokens": h["x-ratelimit-remaining-tokens"] ?? "N/A",
                       "rate_limit_reset_tokens": h["x-ratelimit-reset-tokens"] ?? "0ms",
                       "verified_at": Clock.format("HH:mm:ss"), "active_key": KeyPool.mask(key)]
                break
            }
        }
        out["api"] = api
        return out
    }

    // ------------------------------------------------------------ /api/events
    func sse(_ res: Responder) {
        let l = events.subscribe()
        defer { events.unsubscribe(l) }
        res.begin(200, "text/event-stream; charset=utf-8", headers: [("Cache-Control", "no-cache"), ("X-Accel-Buffering", "no"), ("X-Content-Type-Options", "nosniff")])
        msgLock.lock(); let m = activeMessages; msgLock.unlock()
        var initData = Data("data: ".utf8)
        initData.append(jsonBytes(["type": "init", "messages": m, "count": m.count]))
        initData.append(contentsOf: [10, 10])
        guard res.chunk(initData) else { return }
        while true {
            if let d = events.next(l, timeout: 20) {
                var out = Data("data: ".utf8)
                out.append(d)
                out.append(contentsOf: [10, 10])
                guard res.chunk(out) else { return }
                if l.closed && l.queue.isEmpty { return }
            } else {
                guard res.chunk(": ping\n\n") else { return }
            }
        }
    }

    // ------------------------------------------------------------ /api/chat (NDJSON)
    static func telemetry(_ t: GroqTurn, model: String, mode: String, elapsed: Double, cost: [String: Double],
                          totalSpent: Double, autoCode: Bool, prefix: String) -> [String: Any] {
        var pt = t.promptTokens, ct = t.completionTokens
        var rt = t.reasoningTokens
        if rt == 0 && !t.reasoning.isEmpty { rt = max(1, pyLen(t.reasoning) / 4) }
        var total = pt + ct
        if total == 0 {
            let chars = pyLen(t.content) + pyLen(t.reasoning)
            total = Int(Double(chars) / 3.8) + 10
            pt = max(5, total - chars / 4)
            ct = max(1, total - pt)
        }
        return [
            "prompt_tokens": pt, "completion_tokens": ct, "reasoning_tokens": rt, "answer_tokens": max(0, ct - rt),
            "total_tokens": total, "cost": cost["total_cost"] ?? 0, "prompt_cost": cost["prompt_cost"] ?? 0,
            "completion_cost": cost["completion_cost"] ?? 0, "total_spent": totalSpent, "elapsed": pyRound(elapsed, 2),
            "speed": pyRound(Double(ct) / max(elapsed, 0.05), 1),
            "req_id": t.reqId.isEmpty ? "\(prefix)\(Int(Clock.now * 1000))" : t.reqId, "confirmed": true, "model": model,
            "mode": mode, "served_by_key": t.servedKey.map { KeyPool.mask($0) } ?? "unknown", "failovers": t.failovers,
            "auto_detected_code": autoCode,
        ]
    }

    /// The same token estimate app.py uses when Groq sent no usage, so the ledger records the same numbers.
    static func settle(_ t: inout GroqTurn) {
        if t.reasoningTokens == 0 && !t.reasoning.isEmpty { t.reasoningTokens = max(1, pyLen(t.reasoning) / 4) }
        if t.promptTokens + t.completionTokens == 0 {
            let chars = pyLen(t.content) + pyLen(t.reasoning)
            let total = Int(Double(chars) / 3.8) + 10
            t.promptTokens = max(5, total - chars / 4)
            t.completionTokens = max(1, total - t.promptTokens)
        }
    }

    func chat(_ r: HTTPRequest, _ res: Responder) {
        if pool.count == 0 {
            res.json(400, ["error": "No Groq API keys loaded. Please click '📥 Import Keys' or '⚙️' to add your key."])
            return
        }
        let data = r.json
        let messages = (data["messages"] as? [Any]) ?? []
        let model = (data["model"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? DEFAULT_MODEL
        var mode = (data["output_mode"] as? String) ?? "normal"
        let persona = ((data["system_prompt"] as? String) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        var lastUser = ""
        for case let m as [String: Any] in messages.reversed() where (m["role"] as? String) == "user" {
            lastUser = (m["content"] as? String) ?? ""
            break
        }
        let ndjson: [(String, String)] = [("Cache-Control", "no-cache"), ("X-Accel-Buffering", "no"), ("X-Content-Type-Options", "nosniff")]

        // 1. her local chat commands, matched before Groq is called (in Python for Phase A)
        if let lr = backend("POST", "/api/internal/local_command", ["text": lastUser], timeout: 1800), lr.status == 200,
           let answer = lr.json["answer"] as? String, !answer.isEmpty {
            res.begin(200, "application/x-ndjson", headers: ndjson)
            res.chunk(jsonLine(["t": answer]))
            res.chunk(jsonLine(["u": [
                "prompt_tokens": 0, "completion_tokens": 0, "reasoning_tokens": 0, "answer_tokens": 0, "total_tokens": 0,
                "cost": 0, "prompt_cost": 0, "completion_cost": 0, "total_spent": ledger.totalSpent, "elapsed": 0, "speed": 0,
                "req_id": "local_affinity_\(Int(Clock.now * 1000))", "confirmed": true, "model": "local", "mode": mode,
                "served_by_key": "local", "failovers": 0, "auto_detected_code": false] as [String: Any]]))
            return
        }

        // 2. the prompt, built like build_queen_system_prompt()
        let autoCode = detectCodeIntent(lastUser)
        if autoCode && mode != "code" { mode = "code" }
        guard let system = prompt.build(persona: persona) else {
            res.json(500, ["error": "Queen's system prompt could not be built (no app.py, no bundled copy)"])
            return
        }
        var groqMsgs: [[String: Any]] = [["role": "system", "content": system]]
        if mode == "code" { groqMsgs.append(["role": "system", "content": CODE_BOX_CHAT]) }
        for case let m as [String: Any] in messages.suffix(MAX_MESSAGES) {
            let role = (m["role"] as? String) ?? "user"
            guard ["user", "assistant", "system"].contains(role), let c = m["content"] else { continue }
            if let s = c as? String, s.isEmpty { continue }
            if c is NSNull { continue }
            groqMsgs.append(["role": role, "content": c])
        }

        // 3. Groq, streamed, failover before the first token
        res.begin(200, "application/x-ndjson", headers: ndjson)
        if pool.candidates(model).isEmpty {
            res.chunk(jsonLine(["error": "All API keys in key manager are currently cooling down. Wait or import another key."]))
            return
        }
        let start = Clock.now
        var turn = groq.stream(model: model, messages: groqMsgs, onFailover: { attempt, from, to in
            self.events.broadcast(["type": "key_failover", "attempt": attempt, "from_key": from, "to_key": to])
        }, onToken: { kind, text in res.chunk(jsonLine([kind: text])) })
        if let e = turn.error {
            if e != "client gone" { res.chunk(jsonLine(["error": e])) }
            return
        }
        let elapsed = Clock.now - start

        // 4. after the turn (Python): training log, her command lines run, handover
        if let ar = backend("POST", "/api/internal/after_turn",
                            ["prompt": lastUser, "content": turn.content, "model": model, "mode": mode], timeout: 1800) {
            for case let line as String in (ar.json["lines"] as? [Any]) ?? [] { res.chunk(jsonLine(["t": line])) }
        }

        // 5. the spend and the telemetry line
        QueenServer.settle(&turn)
        let (ci, l) = ledger.record(model, turn.promptTokens, turn.completionTokens, reqId: turn.reqId)
        res.chunk(jsonLine(["u": QueenServer.telemetry(turn, model: model, mode: mode, elapsed: elapsed, cost: ci,
                                                        totalSpent: Ledger.num(l["total_spent"]), autoCode: autoCode,
                                                        prefix: "groq_stm_")]))
    }

    // ------------------------------------------------------------ /api/remote/send (JSON)
    func remoteSend(_ r: HTTPRequest, _ res: Responder) {
        if pool.count == 0 {
            res.json(400, ["ok": false, "error": "No API key configured. Call /api/keys/load-file first."])
            return
        }
        let data = r.json
        let promptText = ((data["prompt"] as? String) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        var mode = (data["mode"] as? String) ?? "normal"
        let model = (data["model"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? DEFAULT_MODEL
        let persona = ((data["system_prompt"] as? String) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if promptText.isEmpty { res.json(400, ["ok": false, "error": "Prompt is required"]); return }
        let autoCode = detectCodeIntent(promptText)
        if autoCode && mode != "code" { mode = "code" }
        events.broadcast(["type": "invisible_hand_typing", "prompt": promptText, "mode": mode, "auto_detected_code": autoCode,
                          "timestamp": Clock.now])
        let fresh = (data["fresh"] as? Bool) == true
        let userMsg: [String: Any] = ["role": "user", "content": promptText, "mode": mode, "timestamp": Clock.now]
        msgLock.lock()
        if !fresh { activeMessages.append(userMsg) }
        let history = fresh ? [userMsg] : Array(activeMessages.suffix(MAX_MESSAGES))
        msgLock.unlock()
        guard let system = prompt.build(persona: persona) else {
            res.json(500, ["ok": false, "error": "Queen's system prompt could not be built"])
            return
        }
        var groqMsgs: [[String: Any]] = [["role": "system", "content": system]]
        if mode == "code" { groqMsgs.append(["role": "system", "content": CODE_BOX_REMOTE]) }
        for m in history { groqMsgs.append(["role": m["role"] ?? "user", "content": m["content"] ?? ""]) }
        if pool.candidates(model).isEmpty { res.json(503, ["ok": false, "error": "All keys are cooling down"]); return }
        // test_bad_key: true puts a key Groq refuses in front, to see the failover live (morning test). Never cooled.
        let extra = (data["test_bad_key"] as? Bool) == true ? ["gsk_" + String(repeating: "0", count: 52)] : []
        let start = Clock.now
        var turn = groq.stream(model: model, messages: groqMsgs, extraFirst: extra, onFailover: { attempt, from, to in
            self.events.broadcast(["type": "key_failover", "attempt": attempt, "from_key": from, "to_key": to])
        }, onToken: { kind, text in
            if kind == "t" { self.events.broadcast(["type": "stream_chunk", "token": text]) }
            return true
        })
        if let e = turn.error {
            if turn.allFailed { res.json(503, ["ok": false, "error": e]) } else { res.json(500, ["ok": false, "error": e]) }
            return
        }
        let elapsed = Clock.now - start
        QueenServer.settle(&turn)
        let (ci, l) = ledger.record(model, turn.promptTokens, turn.completionTokens, reqId: turn.reqId)
        let total = Ledger.num(l["total_spent"])
        let tel = QueenServer.telemetry(turn, model: model, mode: mode, elapsed: elapsed, cost: ci, totalSpent: total,
                                        autoCode: autoCode, prefix: "groq_bt_")
        let asst: [String: Any] = ["role": "assistant", "content": turn.content, "reasoning": turn.reasoning, "telemetry": tel,
                                   "mode": mode, "timestamp": Clock.now]
        msgLock.lock()
        if !fresh { activeMessages.append(asst) }
        let count = activeMessages.count
        msgLock.unlock()
        events.broadcast(["type": "turn_complete", "user_message": userMsg, "assistant_message": asst, "telemetry": tel,
                          "total_spent": total])
        res.json(["ok": true, "reply": turn.content, "reasoning": turn.reasoning, "telemetry": tel, "total_spent": total,
                  "messages_count": count, "fresh": fresh])
    }

    // ------------------------------------------------------------ chats
    func chatGet(_ id: String, _ res: Responder) {
        let p = Chats.path(cfg, id)
        guard FileManager.default.fileExists(atPath: p) else { res.json(404, ["error": "Chat '\(id)' not found"]); return }
        guard let d = Files.readJSON(p) else { res.json(500, ["error": "the chat file is not JSON"]); return }
        res.json(["ok": true, "chat": d])
    }

    func chatSave(_ r: HTTPRequest, _ res: Responder) {
        markDirty()
        guard !r.body.isEmpty, let data = (try? JSONSerialization.jsonObject(with: r.body)) as? [String: Any], !data.isEmpty else {
            res.json(400, ["error": "No data"])
            return
        }
        let id = ((data["id"] as? String) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if id.isEmpty { res.json(400, ["error": "Missing chat id"]); return }
        let messages = (data["messages"] as? [Any]) ?? []
        var title = ((data["title"] as? String) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if title.isEmpty { title = Chats.autoTitle(messages) }
        let now = Clock.isoZ
        let p = Chats.path(cfg, id)
        var created = now
        if let old = Files.readJSON(p) as? [String: Any], let c = old["created_at"] as? String { created = c }
        let chat: [String: Any] = ["id": id, "title": title, "messages": messages, "message_count": messages.count,
                                   "created_at": created, "updated_at": now]
        guard Chats.writeChat(p, chat) else { res.json(500, ["error": "could not write the chat"]); return }
        res.json(["ok": true, "id": id, "title": title, "message_count": messages.count])
    }

    func chatRename(_ r: HTTPRequest, _ res: Responder) {
        let d = r.json
        let id = ((d["id"] as? String) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let title = ((d["title"] as? String) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if id.isEmpty { res.json(400, ["error": "Missing chat id"]); return }
        if title.isEmpty { res.json(400, ["error": "Missing new title"]); return }
        let p = Chats.path(cfg, id)
        guard FileManager.default.fileExists(atPath: p) else { res.json(404, ["error": "Chat '\(id)' not found"]); return }
        guard var c = Files.readJSON(p) as? [String: Any] else { res.json(500, ["error": "the chat file is not JSON"]); return }
        c["title"] = title
        c["updated_at"] = Clock.isoZ
        guard Chats.writeChat(p, c) else { res.json(500, ["error": "could not write the chat"]); return }
        res.json(["ok": true, "id": id, "title": title])
    }

    func chatDelete(_ r: HTTPRequest, _ res: Responder) {
        markDirty()
        let id = ((r.json["id"] as? String) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if id.isEmpty { res.json(400, ["error": "Missing chat id"]); return }
        let p = Chats.path(cfg, id)
        if FileManager.default.fileExists(atPath: p) {
            try? FileManager.default.removeItem(atPath: p)
            res.json(["ok": true, "id": id, "message": "Chat deleted"])
        } else {
            res.json(404, ["error": "Chat not found"])
        }
    }

    // ------------------------------------------------------------ keys
    func autoUpdateConfig() -> Any {
        if let r = backend("GET", "/api/auto_update/config", nil, timeout: 5), r.status == 200,
           let o = try? JSONSerialization.jsonObject(with: r.body) { return o }
        return NSNull()
    }

    func keysInfo() -> [String: Any] {
        let items = pool.statusRich()
        let first = pool.first
        return ["configured": !items.isEmpty, "count": items.count, "keys": pool.statusLegacy(), "items": items,
                "active_key": first.map { KeyPool.mask($0) as Any } ?? NSNull(), "auto_update": autoUpdateConfig(),
                "version": prompt.version()]
    }

    static func hasOtherProviderKeys(_ s: String) -> Bool {
        s.range(of: "AIza[0-9A-Za-z_-]{20,}", options: .regularExpression) != nil
            || s.range(of: "sk-ant-[0-9A-Za-z_-]{20,}", options: .regularExpression) != nil
    }

    func keysImport(_ r: HTTPRequest, _ res: Responder) {
        let d = r.json
        let content = ((d["content"] as? String) ?? (d["text"] as? String) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if content.isEmpty { res.json(400, ["ok": false, "error": "Key input is empty"]); return }
        let groqFound = KeyPool.extract(content)
        let other = QueenServer.hasOtherProviderKeys(content)
        if groqFound.isEmpty && !other {
            res.json(400, ["ok": false, "error": "No valid API keys found. Supported formats: Groq ('gsk_…'), Google Cloud/Gemini ('AIza…'), Anthropic Claude ('sk-ant-…')."])
            return
        }
        var added = 0
        if !groqFound.isEmpty { added = pool.addKeys(groqFound).added }
        var auAdded: Any = ["google": 0, "anthropic": 0]
        var parts: [String] = []
        if !groqFound.isEmpty { parts.append("Groq Chat: +\(added) (\(pool.count) total)") }
        if other {
            // Google / Anthropic keys belong to the auto-update store (auto_updater.py): the backend files them
            if let br = backend("POST", "/api/auto_update/keys/import", ["content": content], timeout: 30), br.status == 200 {
                let j = br.json
                auAdded = j["auto_update_added"] ?? auAdded
                if let a = auAdded as? [String: Any] {
                    if let g = a["google"] as? NSNumber, g.intValue >= 0 { parts.append("Google Auto-Update: +\(g.intValue)") }
                    if let an = a["anthropic"] as? NSNumber, an.intValue >= 0 { parts.append("Anthropic Auto-Update: +\(an.intValue)") }
                }
            } else {
                parts.append("Google/Anthropic keys NOT filed: the backend is not running")
            }
        }
        let au = autoUpdateConfig()
        events.broadcast(["type": "keys_updated", "count": pool.count, "added": added, "auto_update": au])
        res.json(["ok": true, "added": added, "auto_update_added": auAdded, "count": pool.count, "total": pool.count,
                  "items": pool.statusRich(), "auto_update": au, "message": "Imported API keys — " + parts.joined(separator: " · ")])
    }

    func keysDelete(_ r: HTTPRequest, _ res: Responder) {
        let d = r.json
        var removed = false
        if let idx = d["index"], !(idx is NSNull) {
            if let n = (idx as? NSNumber)?.intValue ?? Int("\(idx)") { removed = pool.remove(index: n) }
        } else if let id = (d["id"] as? String) ?? (d["key"] as? String), !id.isEmpty {
            removed = pool.remove(id: id)
        }
        if !removed { res.json(404, ["ok": false, "error": "Key not found in pool"]); return }
        events.broadcast(["type": "keys_updated", "count": pool.count])
        res.json(["ok": true, "count": pool.count, "items": pool.statusRich(), "message": "Key removed from Key Manager."])
    }

    func keysLoadFile(_ r: HTTPRequest, _ res: Responder) {
        var path = ((r.json["path"] as? String) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if path.isEmpty {
            let cwd = FileManager.default.currentDirectoryPath + "/groq-api.txt"
            path = FileManager.default.fileExists(atPath: cwd) ? cwd : cfg.userHome + "/Downloads/API/groq-api.txt"
        }
        if path.hasPrefix("~/") { path = cfg.userHome + String(path.dropFirst(1)) }
        guard let content = Files.read(path) else { res.json(404, ["ok": false, "error": "File not found: \(path)"]); return }
        let found = KeyPool.extract(content)
        if found.isEmpty { res.json(400, ["ok": false, "error": "No valid Groq keys found in \(path)"]); return }
        let (added, total) = pool.addKeys(found)
        let active = pool.first.map { KeyPool.mask($0) } ?? ""
        events.broadcast(["type": "key_loaded", "count": total, "active_key": active])
        res.json(["ok": true, "added": added, "count": total, "active_key": active, "file": path,
                  "message": "Loaded \(added) new key(s) (total \(total)) from \(path)."])
    }

    // ------------------------------------------------------------ claude
    func claudeWrap(_ res: Responder, _ fn: () throws -> [String: Any]) {
        do {
            var o = try fn()
            o["ok"] = true
            res.json(o)
        } catch ClaudeLink.Failure.needConsent {
            res.json(409, ["ok": false, "need_consent": true, "message": ClaudeLink.consentText])
        } catch ClaudeLink.Failure.bad(let m) {
            res.json(400, ["ok": false, "error": m])
        } catch ClaudeLink.Failure.timeout {
            res.json(504, ["ok": false, "error": "Claude Code did not answer in time"])
        } catch {
            res.json(500, ["ok": false, "error": "\(error)"])
        }
    }

    // ------------------------------------------------------------ training
    func trainingCorrect(_ r: HTTPRequest, _ res: Responder) {
        let d = r.json
        var turn = (d["turn"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? "last"
        if turn == "last" { turn = Training.lastTurn(cfg) ?? "" }
        let better = ((d["better"] as? String) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if turn.isEmpty || better.isEmpty { res.json(400, ["ok": false, "error": "need a turn and the better answer"]); return }
        let by = (d["by"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? "Claude Code (Opus)"
        Training.record(cfg, "correction", ["turn": turn, "better": better, "by": by, "why": (d["why"] as? String) ?? ""])
        markDirty()
        res.json(["ok": true, "turn": turn])
    }

    /// build_dataset.status() / build() through a small Python helper (allowed in Phase A); the backend if it fails.
    func trainingHelper(_ r: HTTPRequest, _ res: Responder, call: String) {
        let qapp = cfg.groqDir + "/qwen_app"
        let code = "import sys, json; sys.path.insert(0, \(QueenServer.pyString(qapp))); import build_dataset as b; "
            + "r = b.\(call); print('\\n@@QUEEN_JSON@@' + json.dumps(r, default=str))"
        if FileManager.default.fileExists(atPath: qapp + "/build_dataset.py") {
            let p = runProcess(cfg.pythonExe, ["-c", code], env: ProcessInfo.processInfo.environment.merging(["PATH": cfg.fullPath, "HOME": cfg.userHome]) { $1 },
                               cwd: qapp, timeout: 600)
            if p.code == 0, let m = p.out.range(of: "@@QUEEN_JSON@@", options: .backwards),
               var o = (try? JSONSerialization.jsonObject(with: Data(p.out[m.upperBound...].utf8))) as? [String: Any] {
                o["ok"] = true
                res.json(o)
                return
            }
        }
        if let b = backend(r.method, r.target, r.method == "POST" ? r.json : nil, timeout: 600) {
            res.send(b.status, b.headers["content-type"] ?? "application/json", b.body)
        } else {
            res.json(500, ["ok": false, "error": "build_dataset could not run (no ~/.groq/qwen_app, backend down)"])
        }
    }

    static func pyString(_ s: String) -> String {
        "'" + s.replacingOccurrences(of: "\\", with: "\\\\").replacingOccurrences(of: "'", with: "\\'") + "'"
    }
}
