// Queen's Swift server tests (Phase A, 14.11.2026). Run by GitHub only (mac_app/test.sh in mac-app.yml).
// The server starts on a free port with a temporary ~/.groq, a fake Groq (401, 429 and a good key), a fake Python
// backend (local commands, after-turn, a slow stream, events) and a fake `claude`. Every core route is checked for the
// shape app.py gives; the proxy, the failover, NDJSON streaming, SSE and the system prompt (byte for byte) too.
import Foundation

var passes = 0
var failures: [String] = []
func check(_ ok: Bool, _ name: String, _ detail: @autoclosure () -> String = "") {
    if ok { passes += 1; print("ok    \(name)") } else { failures.append(name); print("FAIL  \(name)  \(detail())") }
}

let env = ProcessInfo.processInfo.environment
let tmp = NSTemporaryDirectory() + "queen-test-" + String(UUID().uuidString.prefix(8))
let groqDir = tmp + "/.groq"
try! FileManager.default.createDirectory(atPath: groqDir + "/qwen_app", withIntermediateDirectories: true)

let K401 = "gsk_test401" + String(repeating: "a", count: 41)
let K429 = "gsk_test429" + String(repeating: "b", count: 41)
let KOK = "gsk_testok0" + String(repeating: "c", count: 41)
let allKeys = [K401, K429, KOK]
// noisy, like a real keys.txt (an export line, a JSON line)
try! "# my keys\n\(K401)\nexport GROQ_X=\"\(K429)\"\n{\"k\": \"\(KOK)\"}\n".write(toFile: groqDir + "/keys.txt", atomically: true, encoding: .utf8)
try! "{\"version\": 5, \"updated_at\": \"2026-11-14T22:00:00+0100\", \"log\": [{\"version\": 5, \"message\": \"m\"}]}"
    .write(toFile: groqDir + "/version.json", atomically: true, encoding: .utf8)

// ---------------------------------------------------------------- fake Groq
var lastGroqBody: [String: Any] = [:]
let fakeGroq = HTTPServer { req, res in
    let auth = (req.header("Authorization") ?? "").replacingOccurrences(of: "Bearer ", with: "")
    if req.path == "/openai/v1/models" {
        if auth == KOK || auth == K429 {
            res.send(200, "application/json", jsonBytes(["data": [["id": "qwen/qwen3.6-27b"], ["id": "whisper-large-v3"],
                                                                  ["id": "llama-3.1-8b-instant"]]]),
                     headers: [("x-groq-region", "test"), ("x-ratelimit-remaining-requests", "99")])
        } else {
            res.json(401, ["error": ["message": "Invalid API Key"]])
        }
        return
    }
    guard req.path == "/openai/v1/chat/completions" else { res.json(404, ["error": "no"]); return }
    if auth == K429 {
        res.send(429, "application/json", jsonBytes(["error": ["message": "Rate limit reached"]]), headers: [("retry-after", "7")])
        return
    }
    guard auth == KOK else { res.json(401, ["error": ["message": "Invalid API Key"]]); return }
    lastGroqBody = req.json
    res.begin(200, "text/event-stream")
    func ev(_ o: [String: Any]) { var d = Data("data: ".utf8); d.append(jsonBytes(o)); d.append(contentsOf: [10, 10]); res.chunk(d) }
    ev(["choices": [["delta": ["reasoning": "think "]]]])
    ev(["choices": [["delta": ["content": "Hello"]]]])
    Thread.sleep(forTimeInterval: 0.05)
    ev(["choices": [["delta": ["content": " Marko"]]]])
    ev(["choices": [["delta": [:], "finish_reason": "stop"]], "x_groq": ["id": "req_123", "usage": [
        "prompt_tokens": 1000, "completion_tokens": 50, "completion_tokens_details": ["reasoning_tokens": 10]]]])
    res.chunk("data: [DONE]\n\n")
}
let groqPort = try! fakeGroq.start(port: 0)

// ---------------------------------------------------------------- fake Python backend (the 8766 of the tests)
var afterTurnCalls: [[String: Any]] = []
var dirtyCalls = 0
let fakeBackend = HTTPServer { req, res in
    switch req.method + " " + req.path {
    case "GET /health": res.json(["ok": true])
    case "POST /api/internal/local_command":
        let t = (req.json["text"] as? String) ?? ""
        res.json(["ok": true, "answer": t.contains("volume") ? "Volume is 40 %." as Any : NSNull()])
    case "POST /api/internal/after_turn":
        afterTurnCalls.append(req.json)
        res.json(["ok": true, "lines": ["\n\n▶ open app Notes\nopened"]])
    case "POST /api/internal/mark_dirty":
        dirtyCalls += 1
        res.json(["ok": true])
    case "GET /api/auto_update/config": res.json(["active_provider": "google"])
    case "POST /api/brain/plan": res.json(["ok": true, "got": req.json, "target": req.target, "method": req.method])
    case "GET /api/dummy/stream":
        res.begin(200, "application/x-ndjson")
        for w in ["one", "two", "three"] {
            res.chunk("{\"w\": \"\(w)\"}\n")
            Thread.sleep(forTimeInterval: 0.4)
        }
    case "GET /api/events":
        res.begin(200, "text/event-stream")
        res.chunk("data: {\"type\": \"init\", \"messages\": []}\n\n")
        for _ in 0..<40 {
            guard res.chunk("data: {\"type\": \"backend_hello\"}\n\n") else { return }
            Thread.sleep(forTimeInterval: 0.5)
        }
    default: res.json(404, ["ok": false, "error": "fake backend: no \(req.path)"])
    }
}
let backendPort = try! fakeBackend.start(port: 0)
try! "\(backendPort)".write(toFile: groqDir + "/backend_port", atomically: true, encoding: .utf8)

// ---------------------------------------------------------------- fake claude
let binDir = tmp + "/.local/bin"
try! FileManager.default.createDirectory(atPath: binDir, withIntermediateDirectories: true)
let fakeClaude = binDir + "/claude"
try! """
#!/bin/sh
if [ "$1" = "auth" ]; then echo '{"loggedIn": true, "authMethod": "claude.ai"}'; exit 0; fi
if [ -n "$CLAUDECODE" ]; then echo '{"is_error": true, "result": "nested"}'; exit 0; fi
echo "{\\"result\\": \\"claude says: $2\\", \\"duration_ms\\": 5, \\"num_turns\\": 1, \\"is_error\\": false}"
""".write(toFile: fakeClaude, atomically: true, encoding: .utf8)
chmod(fakeClaude, 0o755)
let proj = tmp + "/.claude/projects/p1"
try! FileManager.default.createDirectory(atPath: proj, withIntermediateDirectories: true)
try! """
{"type": "user", "timestamp": "t1", "message": {"content": "hello Claude"}}
{"type": "assistant", "timestamp": "t2", "message": {"content": [{"type": "text", "text": "hello Queen"}]}}
{"type": "user", "message": {"content": "<command>skip me</command>"}}
""".write(toFile: proj + "/sid123.jsonl", atomically: true, encoding: .utf8)

// training helper files (build_dataset + training_log) where the server looks for them
if let appPy = env["QT_APP_PY"] {
    let src = (appPy as NSString).deletingLastPathComponent
    for f in ["build_dataset.py", "training_log.py"] { try? FileManager.default.copyItem(atPath: src + "/" + f, toPath: groqDir + "/qwen_app/" + f) }
}

// ---------------------------------------------------------------- the server under test
var cfg = QueenConfig(groqDir: groqDir, userHome: tmp)
cfg.groqBase = "http://127.0.0.1:\(groqPort)/openai/v1"
cfg.bundledPrompt = env["QT_PROMPT"]
cfg.promptHelper = env["QT_HELPER"]
cfg.appPy = env["QT_APP_PY"]
cfg.python = env["QT_PYTHON"] ?? "/usr/bin/python3"
cfg.skillsDir = env["QT_SKILLS"]
cfg.location = "mac"
cfg.reportCost = false
cfg.appVersion = 5
let server = QueenServer(cfg)
let port = try! server.start(port: 0)
print("server on \(port), fake groq \(groqPort), fake backend \(backendPort)")

var bodies: [Data] = []
func call(_ method: String, _ path: String, _ body: [String: Any]? = nil, headers: [(String, String)] = [],
          on p: UInt16 = port) -> LocalResponse {
    let r = LocalHTTP.call(port: p, method: method, path: path, body: body.map { jsonBytes($0) }, headers: headers, timeout: 60)
        ?? LocalResponse(status: 0, headers: [:], body: Data())
    bodies.append(r.body)
    return r
}

/// A streamed request the way the Swift window and URLSession callers read it (HTTP/1.1 chunked).
func streamLines(_ path: String, _ body: [String: Any]?, on p: UInt16 = port) -> (Int, [String], String) {
    var r = URLRequest(url: URL(string: "http://127.0.0.1:\(p)\(path)")!, timeoutInterval: 60)
    if let b = body {
        r.httpMethod = "POST"
        r.httpBody = jsonBytes(b)
        r.setValue("application/json", forHTTPHeaderField: "Content-Type")
    }
    let ls = LineStream(r, idleTimeout: 60)
    guard ls.waitResponse() else { return (0, [], "") }
    var lines: [String] = []
    while let l = ls.nextLine() { if !l.isEmpty { lines.append(l) } }
    bodies.append(Data(lines.joined(separator: "\n").utf8))
    return (ls.status, lines, ls.headers["content-type"] ?? "")
}

func obj(_ line: String) -> [String: Any] {
    (try? JSONSerialization.jsonObject(with: Data(line.utf8)) as? [String: Any]) ?? [:]
}

// ---------------------------------------------------------------- 1. small routes
do {
    let h = call("GET", "/health").json
    check(h["ok"] as? Bool == true && h["app"] as? String == "groq-modern-chat" && h["version"] as? String == "v5"
          && h["default_model"] as? String == DEFAULT_MODEL && h["has_keys"] as? Bool == true, "GET /health shape", "\(h)")
    let v = call("GET", "/api/version").json
    check((v["version"] as? NSNumber)?.intValue == 5 && v["version_str"] as? String == "v5" && v["log"] is [Any]
          && v["auto_update_repo"] as? String == "markoboskoauroville/groq-auto-update", "GET /api/version shape", "\(v)")
    let s = call("GET", "/api/app/status").json
    check(s["ok"] as? Bool == true && (s["keys"] as? NSNumber)?.intValue == 3 && s["face"] as? String == "swift"
          && s["active_key"] as? String == KeyPool.mask(K401) && s["model"] as? String == DEFAULT_MODEL
          && s["total_spent"] != nil && s["pid"] != nil && s["location"] as? String == "mac", "GET /api/app/status shape", "\(s)")
    let root = call("GET", "/")
    check(root.status == 200 && String(decoding: root.body, as: UTF8.self).contains("Swift app"), "GET / is a plain line")
}

// ---------------------------------------------------------------- 2. the system prompt, byte for byte with Python
do {
    if let exp = env["QT_EXPECTED"], let expected = Files.read(exp) {
        let built = server.prompt.build() ?? ""
        check(built == expected, "system prompt == build_queen_system_prompt() (live app.py)",
              "swift \(built.count) chars, python \(expected.count) chars, source \(server.prompt.source)")
        check(server.prompt.source == "live app.py", "prompt template from the live app.py helper", server.prompt.source)
        var c2 = cfg
        c2.appPy = tmp + "/no/app.py"
        let pb = PromptBuilder(c2)
        check(pb.build() == expected && pb.source == "bundle", "prompt fallback: the bundled template", pb.source)
        check(built.contains("### skill: claude-link") && built.contains("YOUR SKILLS"), "every queen_skills/*.md is in the prompt")
        check(server.prompt.build(persona: "Be brief.")?.hasSuffix("\nAdditional Persona / Instructions:\nBe brief.") == true,
              "persona appended like app.py")
    } else {
        check(false, "system prompt test inputs (QT_EXPECTED) missing")
    }
}

// ---------------------------------------------------------------- 3. /api/chat: failover 401 -> 429 -> good, NDJSON
do {
    let (status, lines, type) = streamLines("/api/chat", ["messages": [["role": "user", "content": "Say hello"]]])
    check(status == 200 && type.hasPrefix("application/x-ndjson"), "POST /api/chat answers NDJSON", "\(status) \(type)")
    let objs = lines.map(obj)
    check(objs.contains { $0["r"] as? String == "think " }, "NDJSON has the {\"r\"} reasoning line", "\(lines)")
    let text = objs.compactMap { $0["t"] as? String }.joined()
    check(text.hasPrefix("Hello Marko"), "NDJSON {\"t\"} tokens give the answer", text)
    check(text.contains("▶ open app Notes"), "after-turn lines (backend) are part of the answer", text)
    let u = objs.last?["u"] as? [String: Any] ?? [:]
    check((u["failovers"] as? NSNumber)?.intValue == 2 && u["served_by_key"] as? String == KeyPool.mask(KOK)
          && u["req_id"] as? String == "req_123" && (u["prompt_tokens"] as? NSNumber)?.intValue == 1000
          && (u["completion_tokens"] as? NSNumber)?.intValue == 50 && (u["reasoning_tokens"] as? NSNumber)?.intValue == 10
          && (u["answer_tokens"] as? NSNumber)?.intValue == 40 && u["model"] as? String == DEFAULT_MODEL
          && u["mode"] as? String == "normal" && u["confirmed"] as? Bool == true, "the last line is {\"u\": telemetry}", "\(u)")
    check(abs(((u["cost"] as? NSNumber)?.doubleValue ?? 0) - 0.001) < 1e-9, "cost = 1000 in x 0.80 + 50 out x 4.00 per 1M", "\(u["cost"] ?? "")")
    let st = (Files.readJSON(groqDir + "/key_state.json") as? [String: Any]) ?? [:]
    let cd = (st["cooldown"] as? [String: Any]) ?? [:]
    let r401 = (cd[KeyPool.id(K401) + ":*"] as? NSNumber)?.doubleValue ?? 0
    let r429 = (cd[KeyPool.id(K429) + ":" + DEFAULT_MODEL] as? NSNumber)?.doubleValue ?? 0
    check(r401 - Clock.now > 29 * 24 * 3600, "401 key cooled for every model, 30 days (key_state.json)", "\(cd)")
    check(r429 - Clock.now > 5 && r429 - Clock.now < 8, "429 key cooled for this model, Retry-After 7 s", "\(r429 - Clock.now)")
    check(st["current"] as? String == KeyPool.id(KOK), "the good key is current", "\(st)")
    let sys = ((lastGroqBody["messages"] as? [[String: Any]])?.first?["content"] as? String) ?? ""
    check(sys == env["QT_EXPECTED"].flatMap { Files.read($0) }, "Groq got the full system prompt as message 1")
    check((lastGroqBody["max_tokens"] as? NSNumber)?.intValue == 16000 && lastGroqBody["stream"] as? Bool == true,
          "Groq call: stream true, max_tokens 16000")
    let led = (Files.readJSON(groqDir + "/spend_ledger.json") as? [String: Any]) ?? [:]
    check((led["prompts_count"] as? NSNumber)?.intValue == 1 && ((led["history"] as? [Any])?.count ?? 0) == 1
          && (led["total_prompt_tokens"] as? NSNumber)?.intValue == 1000, "spend_ledger.json written like record_spend", "\(led)")
    check(afterTurnCalls.last?["content"] as? String == "Hello Marko" && afterTurnCalls.last?["prompt"] as? String == "Say hello",
          "after_turn got the prompt and her answer", "\(afterTurnCalls)")

    // code box intent
    _ = streamLines("/api/chat", ["messages": [["role": "user", "content": "write it in a code box: hello"]]])
    let msgs = (lastGroqBody["messages"] as? [[String: Any]]) ?? []
    check(msgs.count >= 3 && (msgs[1]["content"] as? String)?.hasPrefix("You are in CODE BOX mode") == true, "code box intent adds the CODE BOX system line")

    // a local command: answered before Groq is called
    let before = lastGroqBody.count
    lastGroqBody = [:]
    let (_, ll, _) = streamLines("/api/chat", ["messages": [["role": "user", "content": "set the volume to 40"]]])
    let lo = ll.map(obj)
    check(lo.first?["t"] as? String == "Volume is 40 %." && (lo.last?["u"] as? [String: Any])?["model"] as? String == "local"
          && lastGroqBody.isEmpty, "local chat command answered without Groq", "\(ll)")
    _ = before
}

// ---------------------------------------------------------------- 4. /api/remote/send, failover with a bad key, session
do {
    let r = call("POST", "/api/remote/send", ["prompt": "hi", "test_bad_key": true])
    let j = r.json
    let t = j["telemetry"] as? [String: Any] ?? [:]
    check(r.status == 200 && j["ok"] as? Bool == true && j["reply"] as? String == "Hello Marko" && j["reasoning"] as? String == "think "
          && (t["failovers"] as? NSNumber)?.intValue == 1 && (j["messages_count"] as? NSNumber)?.intValue == 2
          && j["fresh"] as? Bool == false, "POST /api/remote/send shape + failover over a refused key", "\(r.status) \(j)")
    let s = call("GET", "/api/session/messages").json
    check((s["count"] as? NSNumber)?.intValue == 2 && (s["messages"] as? [Any])?.count == 2, "GET /api/session/messages", "\(s)")
    let e = call("POST", "/api/remote/send", ["prompt": ""])
    check(e.status == 400 && e.json["error"] as? String == "Prompt is required", "remote/send without a prompt: 400")
}

// ---------------------------------------------------------------- 5. proxy to the backend (streaming, body, method)
do {
    let p = call("POST", "/api/brain/plan?x=1", ["goal": "open Notes"])
    let got = p.json["got"] as? [String: Any] ?? [:]
    check(p.status == 200 && got["goal"] as? String == "open Notes" && p.json["target"] as? String == "/api/brain/plan?x=1",
          "proxy: POST /api/brain/plan reaches the backend unchanged", "\(p.status) \(p.json)")
    // streaming: the first line must arrive long before the last one is written
    let t0 = Clock.now
    if let s = Sock.open(port: port, timeout: 10) {
        s.write("GET /api/dummy/stream HTTP/1.0\r\nHost: x\r\n\r\n")
        _ = LocalHTTP.readHead(s)
        var times: [Double] = []
        var got: [String] = []
        while let l = s.readLine() { if !l.isEmpty { got.append(l); times.append(Clock.now - t0) } }
        s.shut()
        check(got.count == 3 && times[0] < 0.35 && times[2] > 0.7, "proxy streams (first line at once, not at the end)", "\(got) \(times)")
    } else { check(false, "proxy stream: no connection") }
    let (st, lines, _) = streamLines("/api/dummy/stream", nil)
    check(st == 200 && lines.count == 3, "proxy stream read by URLSession (HTTP/1.1 chunked)", "\(st) \(lines)")
    let miss = call("GET", "/api/vision/nothing")
    check(miss.status == 404 && miss.json["error"] as? String == "fake backend: no /api/vision/nothing", "unknown routes go to the backend")
}

// ---------------------------------------------------------------- 6. /api/events (SSE) with the backend relayed
do {
    if let s = Sock.open(port: port, timeout: 10) {
        s.write("GET /api/events HTTP/1.0\r\nHost: x\r\n\r\n")
        let head = LocalHTTP.readHead(s)
        check(head?.0 == 200 && (head?.1["content-type"] ?? "").hasPrefix("text/event-stream"), "GET /api/events is SSE")
        var lines: [String] = []
        let deadline = Clock.now + 8
        DispatchQueue.global().asyncAfter(deadline: .now() + 0.5) { server.events.broadcast(["type": "test_event", "n": 1]) }
        while Clock.now < deadline, let l = s.readLine() {
            if l.hasPrefix("data: ") { lines.append(l) }
            if lines.contains(where: { $0.contains("backend_hello") }) && lines.contains(where: { $0.contains("test_event") }) { break }
        }
        s.shut()
        check(lines.first.map { obj(String($0.dropFirst(6)))["type"] as? String == "init" } == true, "SSE starts with init", "\(lines.prefix(2))")
        check(lines.contains { $0.contains("test_event") }, "SSE carries Swift events")
        check(lines.contains { $0.contains("backend_hello") }, "SSE relays the backend's events", "\(lines.count) lines")
    } else { check(false, "SSE: no connection") }
}

// ---------------------------------------------------------------- 7. chats
do {
    let sv = call("POST", "/api/chats/save", ["id": "s_1", "title": "", "messages": [["role": "user", "content": "Hello there friend"],
                                                                                    ["role": "assistant", "content": "Hi"]]])
    check(sv.json["ok"] as? Bool == true && sv.json["title"] as? String == "Hello there friend"
          && (sv.json["message_count"] as? NSNumber)?.intValue == 2, "POST /api/chats/save (auto title)", "\(sv.json)")
    let ls = call("GET", "/api/chats").json
    let first = (ls["chats"] as? [[String: Any]])?.first ?? [:]
    check((ls["count"] as? NSNumber)?.intValue == 1 && first["id"] as? String == "s_1" && (first["message_count"] as? NSNumber)?.intValue == 2
          && (first["updated_at"] as? String)?.count ?? 0 >= 19, "GET /api/chats", "\(ls)")
    let g = call("GET", "/api/chats/s_1").json
    check(((g["chat"] as? [String: Any])?["messages"] as? [Any])?.count == 2, "GET /api/chats/<id>")
    let rn = call("POST", "/api/chats/rename", ["id": "s_1", "title": "Renamed"]).json
    check(rn["ok"] as? Bool == true && rn["title"] as? String == "Renamed", "POST /api/chats/rename")
    let long = call("POST", "/api/chats/save", ["id": "s_2", "messages": [["role": "user", "content": String(repeating: "word ", count: 20)]]]).json
    check((long["title"] as? String)?.hasSuffix("…") == true, "auto title cut at a word with …", "\(long)")
    let dl = call("POST", "/api/chats/delete", ["id": "s_1"]).json
    check(dl["ok"] as? Bool == true && call("GET", "/api/chats/s_1").status == 404, "POST /api/chats/delete then 404")
    check(call("POST", "/api/chats/save", [:]).status == 400, "chats/save without data: 400")
    Thread.sleep(forTimeInterval: 0.3)
    check(dirtyCalls >= 2, "chat save/delete mark the data dirty (backend)", "\(dirtyCalls)")
}

// ---------------------------------------------------------------- 8. keys
do {
    let k = call("GET", "/api/keys").json
    let items = (k["items"] as? [[String: Any]]) ?? []
    check(k["configured"] as? Bool == true && (k["count"] as? NSNumber)?.intValue == 3 && items.count == 3
          && (k["keys"] as? [Any])?.count == 3 && (k["auto_update"] as? [String: Any])?["active_provider"] as? String == "google",
          "GET /api/keys shape", "\(k)")
    check(items.contains { $0["state_type"] as? String == "cooling" } && items.contains { $0["state_type"] as? String == "active" },
          "key items show cooling and active", "\(items)")
    let newKey = "gsk_testnew" + String(repeating: "d", count: 41)
    let imp = call("POST", "/api/keys/import", ["content": "pasted: \(newKey)."]).json
    check(imp["ok"] as? Bool == true && (imp["added"] as? NSNumber)?.intValue == 1 && (imp["count"] as? NSNumber)?.intValue == 4,
          "POST /api/keys/import adds a gsk_ key from noise", "\(imp)")
    check((Files.read(groqDir + "/keys.txt") ?? "").contains(newKey), "keys.txt holds the new key")
    let del = call("POST", "/api/keys/delete", ["index": 4]).json
    check(del["ok"] as? Bool == true && (del["count"] as? NSNumber)?.intValue == 3, "POST /api/keys/delete by index", "\(del)")
    check(call("POST", "/api/keys/delete", ["id": "nope"]).status == 404, "keys/delete of an unknown key: 404")
    check(call("POST", "/api/keys/import", ["content": "nothing"]).status == 400, "keys/import without a key: 400")
    try! "x \(newKey) y".write(toFile: tmp + "/groq-api.txt", atomically: true, encoding: .utf8)
    let lf = call("POST", "/api/keys/load-file", ["path": tmp + "/groq-api.txt"]).json
    check(lf["ok"] as? Bool == true && (lf["added"] as? NSNumber)?.intValue == 1, "POST /api/keys/load-file", "\(lf)")
    _ = call("POST", "/api/keys/delete", ["id": KeyPool.id(newKey)])
    let rs = call("POST", "/api/reset-keys").json
    check(rs["ok"] as? Bool == true && !(((rs["items"] as? [[String: Any]]) ?? []).contains { $0["state_type"] as? String == "cooling" }),
          "POST /api/reset-keys clears cooldowns")
}

// ---------------------------------------------------------------- 9. models, billing
do {
    let m = call("GET", "/api/models").json
    check((m["models"] as? [String])?.isEmpty == false && m["default"] as? String == DEFAULT_MODEL && m["pricing"] is [String: Any],
          "GET /api/models shape", "\(m)")
    let b = call("GET", "/api/billing").json
    let api = b["api"] as? [String: Any] ?? [:]
    check(b["total_spent"] != nil && b["recent_history"] is [Any] && api["ok"] as? Bool == true && api["region"] as? String == "test",
          "GET /api/billing shape (live check over the pool)", "\(b)")
}

// ---------------------------------------------------------------- 10. supervisor, skills, training
do {
    let p = call("POST", "/api/supervisor/propose", ["task": "t", "step": "s", "summary": "sum", "detail": "d"]).json
    let id = p["id"] as? String ?? ""
    check(p["ok"] as? Bool == true && id.count == 13, "POST /api/supervisor/propose", "\(p)")
    let pend = call("GET", "/api/supervisor/pending").json
    check(((pend["pending"] as? [[String: Any]]) ?? []).contains { $0["id"] as? String == id }, "GET /api/supervisor/pending")
    let g = call("GET", "/api/supervisor/get?id=\(id)").json
    check(g["ok"] as? Bool == true && g["status"] as? String == "pending", "GET /api/supervisor/get")
    let d = call("POST", "/api/supervisor/decide", ["id": id, "decision": "approve", "note": "fine"]).json
    check(d["ok"] as? Bool == true && d["status"] as? String == "approved" && d["by"] as? String == "Claude Code", "POST /api/supervisor/decide")
    let again = call("POST", "/api/supervisor/decide", ["id": id, "decision": "reject"])
    check(again.status == 400 && (again.json["error"] as? String)?.contains("already approved") == true, "decide twice: 400")
    check(call("GET", "/api/supervisor/get?id=../x").status == 404, "supervisor/get refuses a bad id")
    let rec = call("GET", "/api/supervisor/recent?n=5").json
    check((rec["recent"] as? [Any])?.count == 1, "GET /api/supervisor/recent")
    let sk = call("GET", "/api/skills/list").json
    check(((sk["skills"] as? [[String: Any]]) ?? []).count > 10, "GET /api/skills/list")
    Training.record(cfg, "output", ["turn": "t_test_1", "prompt": "p", "output": "o", "model": "m", "mode": "normal"])
    let c = call("POST", "/api/training/correct", ["better": "a better answer", "why": "w"]).json
    check(c["ok"] as? Bool == true && c["turn"] as? String == "t_test_1", "POST /api/training/correct (turn last)", "\(c)")
    let ev = Files.read(groqDir + "/training/events/" + Clock.day + ".jsonl") ?? ""
    check(ev.contains("\"kind\":\"verdict\"") && ev.contains("\"kind\":\"correction\""), "training events: verdict + correction")
    let ts = call("GET", "/api/training/status")
    check(ts.status == 200 && ts.json["ok"] as? Bool == true && ts.json["new_examples"] != nil, "GET /api/training/status (helper)", "\(ts.status) \(ts.json)")
}

// ---------------------------------------------------------------- 11. claude link (+ the consent gate)
do {
    let s = call("GET", "/api/claude/status").json
    check(s["ok"] as? Bool == true && s["reachable"] as? Bool == true && (s["live_sessions"] as? NSNumber)?.intValue == 0, "GET /api/claude/status", "\(s)")
    let a = call("POST", "/api/claude/ask", ["question": "ping"]).json
    check(a["ok"] as? Bool == true && a["answer"] as? String == "claude says: ping" && a["via"] as? String == "local Claude Code (plan)",
          "POST /api/claude/ask (headless claude -p, no CLAUDE* vars)", "\(a)")
    check(call("POST", "/api/claude/ask", [:]).status == 400, "claude/ask without a question: 400")
    let t = call("GET", "/api/claude/transcript?sid=sid123&n=5").json
    check(((t["turns"] as? [[String: Any]]) ?? []).count == 2, "GET /api/claude/transcript", "\(t)")
    let ss = call("GET", "/api/claude/sessions").json
    check(ss["ok"] as? Bool == true && (ss["sessions"] as? [Any])?.isEmpty == true, "GET /api/claude/sessions (no hub: empty)")
    var c2 = QueenConfig(groqDir: tmp + "/g2", userHome: tmp + "/u2")
    c2.reportCost = false
    c2.defaultBackendPort = 1
    let s2 = QueenServer(c2)
    let p2 = try! s2.start(port: 0)
    let need = call("POST", "/api/claude/ask", ["question": "x"], on: p2)
    check(need.status == 409 && need.json["need_consent"] as? Bool == true
          && need.json["message"] as? String == "I cannot reach the local Claude Code. Do you want to use API credits?",
          "consent gate: no local Claude Code -> 409 need_consent", "\(need.status) \(need.json)")
    let noKeys = call("POST", "/api/chat", ["messages": [["role": "user", "content": "hi"]]], on: p2)
    check(noKeys.status == 400 && (noKeys.json["error"] as? String)?.hasPrefix("No Groq API keys loaded") == true, "chat without keys: 400")
    let down = call("GET", "/api/brain/health", on: p2)
    check(down.status == 502 && down.json["ok"] as? Bool == false, "backend down: proxied route gives 502 JSON", "\(down.status)")
}

// ---------------------------------------------------------------- 11b. PAUSE / RESUME / STATUS (16.11.2026)
do {
    let s0 = call("GET", "/api/pause/status")
    check(s0.status == 200 && s0.json["paused"] as? Bool == false && s0.json["since"] is NSNull && s0.json["queued"] is NSNumber,
          "pause status: not paused, since null, queued N", "\(s0.json)")
    let p = call("POST", "/api/pause")
    check(p.status == 200 && p.json["paused"] as? Bool == true && (p.json["since"] as? NSNumber) != nil, "POST /api/pause: paused, since epoch", "\(p.json)")
    check(FileManager.default.fileExists(atPath: groqDir + "/pause.json"), "the pause is stored in pause.json (survives a restart)")
    let rs = call("POST", "/api/remote/send", ["prompt": "hi", "fresh": true])
    check(rs.status == 200 && rs.json["paused"] as? Bool == true && rs.json["ok"] as? Bool == false, "paused: remote/send answered at once as paused", "\(rs.json)")
    let px = call("POST", "/api/brain/plan", ["goal": "x"])
    check(px.status == 200 && px.json["paused"] as? Bool == true, "paused: a proxied POST is answered as paused, not sent", "\(px.json)")
    let st = streamLines("/api/chat", ["messages": [["role": "user", "content": "pause status"]]])
    check(st.1.joined().contains("Paused since"), "chat line 'pause status' answers while paused", "\(st.1)")
    let s1 = call("GET", "/api/pause/status")
    check(s1.json["paused"] as? Bool == true, "status says paused", "\(s1.json)")
    let r = call("POST", "/api/resume")
    check(r.status == 200 && r.json["paused"] as? Bool == false && r.json["since"] is NSNull, "POST /api/resume: running again", "\(r.json)")
    let rs2 = call("POST", "/api/remote/send", ["prompt": "hi", "fresh": true])
    check(rs2.json["paused"] as? Bool != true, "after resume remote/send is not paused", "\(rs2.json)")
    let cp = streamLines("/api/chat", ["messages": [["role": "user", "content": "pause"]]])
    check(cp.1.joined().contains("Paused."), "chat 'pause' pauses", "\(cp.1)")
    check(call("GET", "/api/pause/status").json["paused"] as? Bool == true, "chat pause really paused")
    let cr = streamLines("/api/chat", ["messages": [["role": "user", "content": "resume"]]])
    check(cr.1.joined().contains("Resumed") && call("GET", "/api/pause/status").json["paused"] as? Bool == false, "chat 'resume' resumes", "\(cr.1)")
}

// ---------------------------------------------------------------- 12. the security guard
do {
    let bad = call("GET", "/api/keys", headers: [("Origin", "http://evil.example")])
    check(bad.status == 403 && (bad.json["error"] as? String)?.contains("Untrusted Origin") == true, "guard: a foreign Origin is refused")
    let badProxy = call("GET", "/api/vision/x", headers: [("Sec-Fetch-Site", "cross-site")])
    check(badProxy.status == 403, "guard: also before the proxy")
    let tok = Files.read(groqDir + "/api_token")?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
    let ok = call("GET", "/api/keys", headers: [("Origin", "http://evil.example"), ("X-Queen-Token", tok)])
    check(ok.status == 200 && tok.count == 48, "guard: the local token passes")
    check(call("GET", "/api/keys", headers: [("Origin", "http://127.0.0.1:8765")]).status == 200, "guard: a local Origin passes")
    check(call("OPTIONS", "/api/chat").status == 403, "guard: preflight refused")
}

// ---------------------------------------------------------------- 13. no key ever leaves in an answer
do {
    let all = bodies.map { String(decoding: $0, as: UTF8.self) }.joined()
    check(!allKeys.contains { all.contains($0) }, "no full key in any answer (\(bodies.count) answers checked)")
}

print("\n\(passes) passed, \(failures.count) failed")
if !failures.isEmpty {
    print("FAILED: " + failures.joined(separator: "; "))
    exit(1)
}
exit(0)
