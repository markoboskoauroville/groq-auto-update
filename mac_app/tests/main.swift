// Offline tests for Queen's Swift-owned API and Python backend proxy.
import Foundation

var failures: [String] = []
func check(_ condition: Bool, _ name: String, _ detail: String = "") {
    if condition {
        print("ok    \(name)")
    } else {
        failures.append(name)
        print("FAIL  \(name) \(detail)")
    }
}

let temp = NSTemporaryDirectory() + "queen-backend-test-" + String(UUID().uuidString.prefix(8))
try! FileManager.default.createDirectory(atPath: temp, withIntermediateDirectories: true)
let streamStarted = DispatchSemaphore(value: 0)
let allowStreamEnd = DispatchSemaphore(value: 0)

let fakeBackend = HTTPServer { request, response in
    switch (request.method, request.path) {
    case ("GET", "/health"):
        response.json(["ok": true, "app": "Queen Python skills"])
    case ("GET", "/api/capi/list"):
        response.json([
            "ok": true,
            "method": request.method,
            "path": request.path,
            "has_token": request.header("X-Queen-Token") != nil
        ])
    case ("GET", "/api/events"):
        response.begin(200, "text/event-stream")
        response.chunk("data: first\n\n")
        streamStarted.signal()
        _ = allowStreamEnd.wait(timeout: .now() + 3)
        response.chunk("data: second\n\n")
    default:
        response.json(404, ["ok": false, "error": "not found"])
    }
}
let backendPort = try! fakeBackend.start(port: 0)

var config = QueenConfig(dataDir: temp + "/.queen", userHome: temp, defaultBackendPort: backendPort)
config.appVersion = 31
try! FileManager.default.createDirectory(atPath: config.dataDir, withIntermediateDirectories: true)
try! "{\"version\":31,\"log\":[]}".write(toFile: config.versionFile, atomically: true, encoding: .utf8)

let server = QueenServer(config)
server.backendInfo = { ["port": Int(backendPort), "up": true] }
let port = try! server.start(port: 0)
let host = QueenHost(config)
check(host.backendHealthy(), "host accepts only the new Python backend identity")

let legacyBackend = HTTPServer { _, response in
    response.json(["ok": true, "app": "groq-modern-chat"])
}
let legacyPort = try! legacyBackend.start(port: 0)
let legacyConfig = QueenConfig(dataDir: temp + "/.legacy", userHome: temp, defaultBackendPort: legacyPort)
check(!QueenHost(legacyConfig).backendHealthy(), "host rejects a healthy but retired backend")
legacyBackend.stop()

func call(_ method: String, _ path: String, headers: [(String, String)] = []) -> LocalResponse {
    LocalHTTP.call(port: port, method: method, path: path, headers: headers, timeout: 10)
        ?? LocalResponse(status: 0, headers: [:], body: Data())
}

let health = call("GET", "/health")
check(health.status == 200 && health.json["ok"] as? Bool == true
      && health.json["version"] as? String == "v31", "health reports Swift service and app version")

let appStatus = call("GET", "/api/app/status")
check(appStatus.status == 200 && appStatus.json["face"] as? String == "swift"
      && ((appStatus.json["backend"] as? [String: Any])?["up"] as? Bool) == true,
      "app status identifies Swift host and Python backend")

let version = call("GET", "/api/version")
check(version.status == 200 && (version.json["version"] as? Int) == 31
      && version.json["version_str"] as? String == "v31", "version endpoint uses installed app version")

let token = (try? String(contentsOfFile: config.dataDir + "/api_token", encoding: .utf8))?
    .trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
let proxied = call("GET", "/api/capi/list", headers: [("X-Queen-Token", token)])
check(proxied.status == 200 && proxied.json["path"] as? String == "/api/capi/list"
      && proxied.json["has_token"] as? Bool == true, "CAPI route is proxied with its local token")

let retiredRoute = call("GET", "/api/groq/models")
check(retiredRoute.status == 404, "retired Groq API is unavailable")

let crossOrigin = call("GET", "/api/app/status", headers: [("Origin", "https://attacker.example")])
check(crossOrigin.status == 403, "cross-origin requests are rejected")

let deceptiveOrigin = call("GET", "/api/app/status", headers: [("Origin", "http://127.0.0.1.attacker.example")])
check(deceptiveOrigin.status == 403, "deceptive loopback origin is rejected")

let badToken = call("GET", "/api/capi/list", headers: [("X-Queen-Token", "invalid")])
check(badToken.status == 403, "invalid local API token is rejected")

let stream = Sock.open(port: port, timeout: 1)
let streamRequest = "GET /api/events HTTP/1.1\r\nHost: 127.0.0.1:\(port)\r\nConnection: close\r\n\r\n"
_ = stream?.write(streamRequest)
let streamHead = stream?.readHead()
let firstEvent = stream?.readSome().map { String(decoding: $0, as: UTF8.self) } ?? ""
allowStreamEnd.signal()
check(streamStarted.wait(timeout: .now() + 1) == .success && streamHead != nil
      && firstEvent.contains("data: first"), "proxied event stream forwards chunks before completion")
_ = stream?.readToEnd()
stream?.shut()

server.stop()
fakeBackend.stop()
try? FileManager.default.removeItem(atPath: temp)

if failures.isEmpty {
    print("PASS")
} else {
    fputs("\(failures.count) test(s) failed\n", stderr)
    exit(1)
}
