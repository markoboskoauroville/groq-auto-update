// QueenServer.swift: the Swift-owned local API, with CAPI and updater routes proxied to Python.
import Foundation

final class QueenServer {
    let cfg: QueenConfig
    var backendInfo: (() -> [String: Any])?
    private var http: HTTPServer?
    private let token: String

    init(_ cfg: QueenConfig) {
        self.cfg = cfg
        token = LocalToken.ensure(cfg)
    }

    @discardableResult
    func start(port: UInt16) throws -> UInt16 {
        let server = HTTPServer { [weak self] request, response in
            self?.handle(request, response)
        }
        server.raw = { [weak self] request, client in
            guard let self else { return false }
            guard self.isNative(request) else {
                self.proxy(request, client)
                return true
            }
            return false
        }
        let boundPort = try server.start(port: port)
        http = server
        return boundPort
    }

    func stop() {
        http?.stop()
        http = nil
    }

    private func isNative(_ request: HTTPRequest) -> Bool {
        request.method == "GET" && ["/", "/health", "/api/app/status", "/api/version"].contains(request.path)
    }

    private func handle(_ request: HTTPRequest, _ response: Responder) {
        guard authorized(request) else {
            response.json(403, ["ok": false, "error": "local Queen API only"])
            return
        }
        switch (request.method, request.path) {
        case ("GET", "/"):
            response.text(200, "Queen is running\n")
        case ("GET", "/health"):
            response.json(["ok": true, "service": "queen-swift", "version": "v\(cfg.appVersion)"])
        case ("GET", "/api/app/status"):
            response.json([
                "ok": true,
                "face": "swift",
                "pid": ProcessInfo.processInfo.processIdentifier,
                "version": "v\(cfg.appVersion)",
                "backend": backendInfo?() ?? [:]
            ])
        case ("GET", "/api/version"):
            var value = Files.readJSON(cfg.versionFile) as? [String: Any] ?? [:]
            value["version"] = cfg.appVersion
            value["version_str"] = "v\(cfg.appVersion)"
            value["app_version"] = cfg.appVersion
            value["auto_update_repo"] = "markoboskoauroville/groq-auto-update"
            value["ok"] = true
            response.json(value)
        default:
            response.json(404, ["ok": false, "error": "not found"])
        }
    }

    private func authorized(_ request: HTTPRequest) -> Bool {
        if let supplied = request.header("X-Queen-Token"), supplied != token { return false }
        guard let origin = request.header("Origin"), !origin.isEmpty else { return true }
        guard let components = URLComponents(string: origin),
              components.scheme == "http",
              let host = components.host?.lowercased() else { return false }
        return host == "127.0.0.1" || host == "localhost" || host == "::1"
    }

    private func proxy(_ request: HTTPRequest, _ client: Sock) {
        guard authorized(request) else {
            writeError(403, "local Queen API only", to: client)
            return
        }
        let port = cfg.backendPort
        guard let backend = Sock.open(port: port, timeout: 3600) else {
            writeError(502, "Queen Python backend is unavailable", to: client)
            return
        }
        defer { backend.shut() }

        var head = "\(request.method) \(request.target) HTTP/1.1\r\nHost: 127.0.0.1:\(port)\r\nConnection: close\r\n"
        let ignored: Set<String> = [
            "connection", "content-length", "expect", "host", "keep-alive", "proxy-connection",
            "te", "trailer", "transfer-encoding", "upgrade"
        ]
        for (name, value) in request.headers where !ignored.contains(name.lowercased()) {
            head += "\(name): \(value)\r\n"
        }
        if !request.body.isEmpty { head += "Content-Length: \(request.body.count)\r\n" }
        head += "\r\n"
        guard backend.write(head), request.body.isEmpty || backend.write(request.body) else {
            writeError(502, "could not send request to Queen Python backend", to: client)
            return
        }
        guard let responseHead = backend.readHead() else {
            writeError(502, "Queen Python backend returned no response", to: client)
            return
        }
        guard client.write(responseHead) else { return }
        while let chunk = backend.readSome() {
            guard client.write(chunk) else { return }
        }
    }

    private func writeError(_ status: Int, _ message: String, to client: Sock) {
        let body = jsonBytes(["ok": false, "error": message])
        let reason = HTTP_REASONS[status] ?? "Error"
        var head = "HTTP/1.1 \(status) \(reason)\r\nContent-Type: application/json\r\n"
        head += "Content-Length: \(body.count)\r\nConnection: close\r\nServer: queen-swift\r\n\r\n"
        client.write(head)
        client.write(body)
    }
}
