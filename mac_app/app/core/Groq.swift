// Groq.swift: Groq's OpenAI-compatible API from Swift (Phase A, 14.11.2026). URLSession, no SDK.
// One streamed chat completion with key failover BEFORE the first token, exactly like app.py's chat()/remote_send():
// a key that fails is cooled (401/403: every model for 30 days; anything else: this model for Retry-After) and the next
// key is tried; once a token has arrived, a failure is an error line, never a silent retry.
import Foundation

/// A URLSession data task read line by line from a worker thread.
final class LineStream: NSObject, URLSessionDataDelegate {
    private let cond = NSCondition()
    private var buf = Data()
    private var done = false
    private var gotResponse = false
    private(set) var status = 0
    private(set) var headers: [String: String] = [:]
    private(set) var error: Error?
    private var session: URLSession!
    private var task: URLSessionDataTask?

    init(_ request: URLRequest, idleTimeout: Double = 300) {
        super.init()
        let c = URLSessionConfiguration.ephemeral
        c.timeoutIntervalForRequest = idleTimeout
        c.timeoutIntervalForResource = 3600
        c.requestCachePolicy = .reloadIgnoringLocalCacheData
        c.urlCache = nil
        session = URLSession(configuration: c, delegate: self, delegateQueue: nil)
        task = session.dataTask(with: request)
        task?.resume()
    }

    func urlSession(_ s: URLSession, dataTask: URLSessionDataTask, didReceive response: URLResponse,
                    completionHandler: @escaping (URLSession.ResponseDisposition) -> Void) {
        cond.lock()
        if let h = response as? HTTPURLResponse {
            status = h.statusCode
            for (k, v) in h.allHeaderFields { headers["\(k)".lowercased()] = "\(v)" }
        }
        gotResponse = true
        cond.broadcast()
        cond.unlock()
        completionHandler(.allow)
    }

    func urlSession(_ s: URLSession, dataTask: URLSessionDataTask, didReceive data: Data) {
        cond.lock()
        buf.append(data)
        cond.broadcast()
        cond.unlock()
    }

    func urlSession(_ s: URLSession, task: URLSessionTask, didCompleteWithError error: Error?) {
        cond.lock()
        self.error = error
        done = true
        cond.broadcast()
        cond.unlock()
        session.finishTasksAndInvalidate()
    }

    /// Waits for the status line; false when the request failed before any answer.
    func waitResponse() -> Bool {
        cond.lock(); defer { cond.unlock() }
        while !gotResponse && !done { cond.wait() }
        return gotResponse
    }

    /// The next line (without CR LF), nil at the end.
    func nextLine() -> String? {
        cond.lock(); defer { cond.unlock() }
        while true {
            if let i = buf.firstIndex(of: 10) {
                var line = buf.subdata(in: buf.startIndex..<i)
                buf = buf.subdata(in: (i + 1)..<buf.endIndex)
                if line.last == 13 { line.removeLast() }
                return String(decoding: line, as: UTF8.self)
            }
            if done {
                if buf.isEmpty { return nil }
                let l = String(decoding: buf, as: UTF8.self)
                buf = Data()
                return l
            }
            cond.wait()
        }
    }

    func readAll() -> Data {
        cond.lock(); defer { cond.unlock() }
        while !done { cond.wait() }
        return buf
    }

    func cancel() { task?.cancel() }
}

/// What one streamed turn gave.
struct GroqTurn {
    var content = ""
    var reasoning = ""
    var promptTokens = 0
    var completionTokens = 0
    var reasoningTokens = 0
    var reqId = ""
    var servedKey: String?
    var failovers = 0
    var error: String?          // set when the stream broke after the first token, or every key failed
    var started = false
    var allFailed = false
    var paused = false          // cut by PAUSE: nothing to settle, nothing cooled, answered as "paused"
}

final class GroqClient {
    let cfg: QueenConfig
    let pool: KeyPool
    let pause: PauseState

    init(_ cfg: QueenConfig, _ pool: KeyPool, _ pause: PauseState) {
        self.cfg = cfg
        self.pool = pool
        self.pause = pause
    }

    func request(_ path: String, key: String, body: [String: Any]? = nil, timeout: Double = 30) -> URLRequest {
        var r = URLRequest(url: URL(string: cfg.groqBase + path)!, timeoutInterval: timeout)
        r.setValue("Bearer " + key, forHTTPHeaderField: "Authorization")
        r.setValue("application/json", forHTTPHeaderField: "Accept")
        if let b = body {
            r.httpMethod = "POST"
            r.setValue("application/json", forHTTPHeaderField: "Content-Type")
            r.httpBody = jsonBytes(b)
        }
        return r
    }

    static func errorText(_ status: Int, _ body: Data) -> String {
        if let o = try? JSONSerialization.jsonObject(with: body) as? [String: Any] {
            if let e = o["error"] as? [String: Any], let m = e["message"] as? String { return "Error code: \(status) - \(m)" }
            if let m = o["error"] as? String { return "Error code: \(status) - \(m)" }
        }
        return "Error code: \(status) - " + String(decoding: body.prefix(300), as: UTF8.self)
    }

    /// One streamed completion over the pool. `extraFirst` keys are tried first (a test of failover; they are never
    /// cooled because they are not in the pool). `onEvent` gets ("failover", attempt, fromMask, toMask) before a retry;
    /// `onToken(kind, text)` gets "r" (reasoning) and "t" (content) and returns false when the client has gone.
    func stream(model: String, messages: [[String: Any]], extraFirst: [String] = [],
                onFailover: (Int, String, String) -> Void = { _, _, _ in },
                onToken: (String, String) -> Bool) -> GroqTurn {
        var turn = GroqTurn()
        let candidates = extraFirst + pool.candidates(model)
        let inPool = Set(pool.keys)
        var lastError = ""
        attempts: for (i, key) in candidates.enumerated() {
            let attempt = i + 1
            if pause.isPaused { turn.paused = true; turn.error = "paused"; return turn }   // no new call while paused
            turn.servedKey = key
            if attempt > 1 {
                turn.failovers += 1
                onFailover(attempt, KeyPool.mask(candidates[attempt - 2]), KeyPool.mask(key))
            }
            let body: [String: Any] = ["model": model, "messages": messages, "stream": true, "max_tokens": cfg.maxOutput]
            let ls = LineStream(request("/chat/completions", key: key, body: body, timeout: 300))
            pause.register(ls)
            defer { pause.unregister(ls) }
            guard ls.waitResponse() else {
                if pause.isPaused { turn.paused = true; turn.error = "paused"; return turn }
                lastError = ls.error?.localizedDescription ?? "no answer"
                if inPool.contains(key) { pool.cool(key, model, status: 0, retryAfter: nil) }
                continue
            }
            if ls.status >= 400 {
                let b = ls.readAll()
                lastError = GroqClient.errorText(ls.status, b)
                if inPool.contains(key) { pool.cool(key, model, status: ls.status, retryAfter: ls.headers["retry-after"]) }
                continue
            }
            var broken: String?
            while let line = ls.nextLine() {
                guard line.hasPrefix("data:") else { continue }
                let payload = line.dropFirst(5).trimmingCharacters(in: .whitespaces)
                if payload == "[DONE]" { break }
                guard let o = try? JSONSerialization.jsonObject(with: Data(payload.utf8)) as? [String: Any] else { continue }
                if let e = o["error"] {
                    broken = (e as? [String: Any])?["message"] as? String ?? "\(e)"
                    break
                }
                if let ch = (o["choices"] as? [[String: Any]])?.first, let d = ch["delta"] as? [String: Any] {
                    if let r = d["reasoning"] as? String, !r.isEmpty {
                        turn.reasoning += r
                        turn.started = true
                        if !onToken("r", r) { ls.cancel(); turn.error = "client gone"; return turn }
                    }
                    if let c = d["content"] as? String, !c.isEmpty {
                        turn.content += c
                        turn.started = true
                        if !onToken("t", c) { ls.cancel(); turn.error = "client gone"; return turn }
                    }
                }
                var usage = o["usage"] as? [String: Any]
                if let xg = o["x_groq"] as? [String: Any] {
                    if usage == nil { usage = xg["usage"] as? [String: Any] }
                    if let id = xg["id"] as? String, !id.isEmpty { turn.reqId = id }
                }
                if let u = usage {
                    let pt = Ledger.int(u["prompt_tokens"]), ct = Ledger.int(u["completion_tokens"])
                    let rt = Ledger.int((u["completion_tokens_details"] as? [String: Any])?["reasoning_tokens"])
                    if pt > 0 { turn.promptTokens = pt }
                    if ct > 0 { turn.completionTokens = ct }
                    if rt > 0 { turn.reasoningTokens = rt }
                }
            }
            if pause.isPaused && (broken != nil || ls.error != nil || !turn.started) {
                // cut by PAUSE (the stream was cancelled): not an error, the key is not cooled
                ls.cancel(); turn.paused = true; turn.error = "paused"; return turn
            }
            if broken == nil, let e = ls.error, (e as NSError).code != NSURLErrorCancelled { broken = e.localizedDescription }
            if let b = broken {
                if inPool.contains(key) { pool.cool(key, model, status: 0, retryAfter: nil) }
                if !turn.started { lastError = b; continue attempts }
                turn.error = "Stream interrupted on \(KeyPool.mask(key)): \(b)"
                return turn
            }
            if inPool.contains(key) { pool.good(key, model) }
            return turn
        }
        turn.allFailed = true
        turn.error = candidates.isEmpty ? "No Groq API keys loaded." : "Every Groq key failed. Last: \(lastError)"
        return turn
    }

    /// GET /models with one key: (status, json, headers).
    func models(key: String) -> (Int, [String: Any], [String: String])? {
        if pause.isPaused { return nil }    // no new API call while paused
        let ls = LineStream(request("/models", key: key, timeout: 15), idleTimeout: 15)
        guard ls.waitResponse() else { return nil }
        let d = ls.readAll()
        return (ls.status, (try? JSONSerialization.jsonObject(with: d) as? [String: Any]) ?? [:], ls.headers)
    }
}
