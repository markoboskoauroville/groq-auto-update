// Host.swift: the Swift app as Queen's host (Phase A, 14.11.2026).
// 1. Serves 127.0.0.1:8765 itself (QueenServer). If an OLD Python Queen holds 8765 (its /api/app/status has no "face"),
//    she is asked to stop (SIGTERM to her pid) and the port is taken; another Swift Queen there is left alone.
// 2. Starts the Groq-free Python backend as its child: ~/.queen/queen-backend on 8766.
// 3. Watches it every 5 s; after 3 failed checks it is started again (at most once every 20 s). OFF stops it.
// 4. Writes ~/.queen/active_port = 8765 and app_url = http://127.0.0.1:8765, so every caller keeps the same address.
import Foundation

final class QueenHost {
    static let shared = QueenHost(QueenConfig.standard)

    let cfg: QueenConfig
    private(set) var server: QueenServer?
    private(set) var serving = false
    private(set) var line = "starting"
    private var child: Process?
    private var lastStart: Double = 0
    private var fails = 1
    private var timer: DispatchSourceTimer?
    private let lock = NSLock()
    var port: UInt16 = 8765

    init(_ cfg: QueenConfig) { self.cfg = cfg }

    func start(appVersion: Int) {
        var c = cfg
        c.appVersion = appVersion
        let s = QueenServer(c)
        s.backendInfo = { [weak self] in self?.backendInfo() ?? [:] }
        server = s
        DispatchQueue.global().async {
            self.bind(s)
            self.ensureBackend()
            let t = DispatchSource.makeTimerSource(queue: .global())
            t.schedule(deadline: .now() + 5, repeating: 5)
            t.setEventHandler { [weak self] in self?.watch() }
            t.resume()
            self.timer = t
        }
    }

    private func bind(_ s: QueenServer) {
        for attempt in 1...8 {
            do {
                try s.start(port: port)
                serving = true
                line = "serving 127.0.0.1:\(port)"
                writeAddress()
                return
            } catch let e as ServerError where e.inUse {
                let st = LocalHTTP.call(port: port, method: "GET", path: "/api/app/status", timeout: 4)?.json ?? [:]
                if (st["face"] as? String) == "swift" {
                    line = "another Queen app serves \(port): this window is its face"
                    return
                }
                if let pid = (st["pid"] as? NSNumber)?.int32Value, pid > 1, attempt <= 4 {
                    // the old Python Queen (before Phase A) on 8765: she moves to 8766 as the backend
                    kill(pid, SIGTERM)
                }
                Thread.sleep(forTimeInterval: 1.5)
            } catch {
                line = "could not serve \(port): \(error)"
                return
            }
        }
        line = "port \(port) is held by another program"
    }

    private func writeAddress() {
        Files.writeAtomic(cfg.dataDir + "/active_port", Data("\(port)".utf8))
        Files.writeAtomic(cfg.dataDir + "/app_url", Data("http://127.0.0.1:\(port)".utf8))
    }

    // ------------------------------------------------------------ the backend (Python, 8766)
    func backendHealthy() -> Bool {
        guard let r = LocalHTTP.call(port: cfg.backendPort, method: "GET", path: "/health", timeout: 4) else { return false }
        return r.status == 200 && (r.json["ok"] as? Bool) == true
            && (r.json["app"] as? String) == "Queen Python skills"
    }

    func backendInfo() -> [String: Any] {
        lock.lock(); defer { lock.unlock() }
        return ["port": Int(cfg.backendPort), "up": fails == 0, "ours": child?.isRunning ?? false,
                "pid": child.map { Int($0.processIdentifier) } ?? 0]
    }

    var backendUp: Bool { lock.lock(); defer { lock.unlock() }; return fails == 0 }

    private func ensureBackend() {
        if backendHealthy() {
            lock.lock(); fails = 0; lock.unlock()
            return
        }
        startBackend()
    }

    private func watch() {
        let ok = backendHealthy()
        lock.lock()
        fails = ok ? 0 : fails + 1
        let f = fails
        let running = child?.isRunning ?? false
        lock.unlock()
        if ok {
            // an old launcher may have written its own address over ours: 8765 is the address of Queen
            if Files.read(cfg.dataDir + "/app_url") != "http://127.0.0.1:\(port)" && serving { writeAddress() }
            return
        }
        if f >= 3 && !running { startBackend() }
    }

    /// START QUEEN: the backend now (also when it runs: it is restarted).
    func restartBackend() {
        stopBackend()
        lock.lock(); fails = 1; lock.unlock()
        lastStart = 0
        startBackend()
    }

    func startBackend() {
        lock.lock(); defer { lock.unlock() }
        if Clock.now - lastStart < 20 { return }
        lastStart = Clock.now
        let executable = cfg.dataDir + "/queen-backend"
        guard FileManager.default.isExecutableFile(atPath: executable) else {
            line = "backend not installed (~/.queen/queen-backend missing: run install.sh in groq_ai_studio)"
            return
        }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: executable)
        var env = ProcessInfo.processInfo.environment.filter { !$0.key.hasPrefix("CLAUDE") }
        env["QUEEN_BACKEND"] = "1"
        env["QUEEN_PORT"] = "\(cfg.defaultBackendPort)"
        env["PATH"] = cfg.fullPath
        p.environment = env
        let logPath = cfg.dataDir + "/backend.log"
        if !FileManager.default.fileExists(atPath: logPath) { FileManager.default.createFile(atPath: logPath, contents: nil) }
        if let log = FileHandle(forWritingAtPath: logPath) {
            log.seekToEndOfFile()
            p.standardOutput = log
            p.standardError = log
        }
        p.standardInput = FileHandle.nullDevice
        do {
            try p.run()
            child = p
        } catch {
            line = "backend could not start: \(error.localizedDescription)"
        }
    }

    func stopBackend() {
        lock.lock()
        let p = child
        child = nil
        lock.unlock()
        if let p = p, p.isRunning {
            p.terminate()
            DispatchQueue.global().asyncAfter(deadline: .now() + 3) { if p.isRunning { kill(p.processIdentifier, SIGKILL) } }
        }
    }

    /// OFF: the backend this app started is stopped; the port is let go.
    func stop() {
        stopBackend()
        server?.stop()
    }
}
