// Util.swift: the configuration of the Swift Queen server, files, processes, times (Phase A, 14.11.2026).
import Foundation
import CryptoKit

/// Everything the server needs to know about where it lives.
struct QueenConfig {
    var dataDir: String                 // ~/.queen: CAPI chats, provider keys, updater state, and backend files
    var userHome: String                // ~ (for ~/.claude, ~/.local/bin/claude, ~/Developer/claude-code/tools, ~/.config)
    var defaultBackendPort: UInt16 = 8766
    var python: String? = nil           // a python3 for the helpers
    var skillsDir: String? = nil        // default ~/.queen/queen_skills
    var claudeBin: String? = nil        // default ~/.local/bin/claude
    var hubTools: String? = nil         // default ~/Developer/claude-code/tools
    var location = ProcessInfo.processInfo.environment["QUEEN_LOCATION"] ?? "mac"
    var maxOutput = Int(ProcessInfo.processInfo.environment["QWEN_MAX_OUTPUT"] ?? "") ?? 16000
    var reportCost = true               // POST /spent to the Cost Agent after a paid call
    var appVersion = 0                  // the Swift app's own whole number (VERSION in App.swift)

    static var standard: QueenConfig {
        let home = FileManager.default.homeDirectoryForCurrentUser.path
        return QueenConfig(dataDir: home + "/.queen", userHome: home)
    }

    var skills: String { skillsDir ?? dataDir + "/queen_skills" }
    var claude: String { claudeBin ?? userHome + "/.local/bin/claude" }
    var hub: String { hubTools ?? userHome + "/Developer/claude-code/tools" }
    var pythonExe: String {
        if let p = python { return p }
        let venv = dataDir + "/venv/bin/python"
        return FileManager.default.isExecutableFile(atPath: venv) ? venv : "/usr/bin/python3"
    }

    /// The port of the Python backend: ~/.queen/backend_port, else 8766.
    var backendPort: UInt16 {
        if let s = try? String(contentsOfFile: dataDir + "/backend_port", encoding: .utf8),
           let p = UInt16(s.trimmingCharacters(in: .whitespacesAndNewlines)), p > 0 { return p }
        return defaultBackendPort
    }

    /// version.json from the source checkout when available, else the installed Queen directory.
    var versionFile: String {
        let dev = userHome + "/Developer/groq_ai_studio"
        if FileManager.default.fileExists(atPath: dev + "/.git") { return dev + "/version.json" }
        return dataDir + "/version.json"
    }

    /// The whole PATH a Mac app does not have (it starts with /usr/bin:/bin only).
    var fullPath: String {
        [dataDir, userHome + "/.local/bin", userHome + "/.pyenv/shims", "/opt/homebrew/bin", "/usr/local/bin",
         "/usr/bin", "/bin", "/usr/sbin", "/sbin"].joined(separator: ":")
    }
}

enum Files {
    static func read(_ p: String) -> String? { try? String(contentsOfFile: p, encoding: .utf8) }

    static func readJSON(_ p: String) -> Any? {
        guard let d = FileManager.default.contents(atPath: p) else { return nil }
        return try? JSONSerialization.jsonObject(with: d)
    }

    /// tmp + rename, like the Python side (tmp.replace). mode 0600 when private.
    @discardableResult
    static func writeAtomic(_ p: String, _ data: Data, privateFile: Bool = false) -> Bool {
        let dir = (p as NSString).deletingLastPathComponent
        try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        let tmp = p + "." + String(UUID().uuidString.prefix(8)) + ".tmp"
        guard FileManager.default.createFile(atPath: tmp, contents: data,
                                             attributes: privateFile ? [.posixPermissions: 0o600] : nil) else { return false }
        if rename(tmp, p) != 0 {
            unlink(tmp)
            return false
        }
        return true
    }

    static func writeJSON(_ p: String, _ o: Any, pretty: Bool = false, privateFile: Bool = false) -> Bool {
        var opts: JSONSerialization.WritingOptions = [.withoutEscapingSlashes]
        if pretty { opts.insert(.prettyPrinted); opts.insert(.sortedKeys) }
        guard JSONSerialization.isValidJSONObject(o), let d = try? JSONSerialization.data(withJSONObject: o, options: opts) else {
            return false
        }
        return writeAtomic(p, d, privateFile: privateFile)
    }

    static func mtime(_ p: String) -> Double {
        ((try? FileManager.default.attributesOfItem(atPath: p)[.modificationDate]) as? Date)?.timeIntervalSince1970 ?? 0
    }

    static func appendLine(_ p: String, _ line: String) {
        let dir = (p as NSString).deletingLastPathComponent
        try? FileManager.default.createDirectory(atPath: dir, withIntermediateDirectories: true)
        if !FileManager.default.fileExists(atPath: p) { FileManager.default.createFile(atPath: p, contents: nil) }
        guard let h = FileHandle(forWritingAtPath: p) else { return }
        h.seekToEndOfFile()
        h.write(Data((line + "\n").utf8))
        h.closeFile()
    }
}

enum Clock {
    /// strftime with the local zone, e.g. "%Y-%m-%dT%H:%M:%S%z" -> yyyy-MM-dd'T'HH:mm:ssZ
    static func format(_ pattern: String, _ date: Date = Date()) -> String {
        let f = DateFormatter()
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone.current
        f.dateFormat = pattern
        return f.string(from: date)
    }
    static var isoZ: String { format("yyyy-MM-dd'T'HH:mm:ssZ") }       // time.strftime("%Y-%m-%dT%H:%M:%S%z")
    static var iso: String { format("yyyy-MM-dd'T'HH:mm:ss") }          // "%Y-%m-%dT%H:%M:%S"
    static var stamp: String { format("yyyy-MM-dd HH:mm:ss") }          // "%Y-%m-%d %H:%M:%S"
    static var day: String { format("yyyy-MM-dd") }
    static var now: Double { Date().timeIntervalSince1970 }
}

func sha256hex(_ s: String) -> String {
    SHA256.hash(data: Data(s.utf8)).map { String(format: "%02x", $0) }.joined()
}

func randomHex(_ n: Int) -> String {
    (0..<n).map { _ in String(format: "%x", Int.random(in: 0..<16)) }.joined()
}

/// Python round(x, n) for the telemetry numbers.
func pyRound(_ x: Double, _ n: Int) -> Double {
    let m = pow(10.0, Double(n))
    return (x * m).rounded(.toNearestOrEven) / m
}

/// Code points, like Python's len() and slicing.
func pyPrefix(_ s: String, _ n: Int) -> String {
    String(String.UnicodeScalarView(s.unicodeScalars.prefix(n)))
}

func pyLen(_ s: String) -> Int { s.unicodeScalars.count }

// ---------------------------------------------------------------- processes
struct ProcResult {
    var code: Int32
    var out: String
    var err: String
    var timedOut: Bool
}

/// Runs a program, keyboard on /dev/null, output captured, killed after `timeout` seconds.
func runProcess(_ exe: String, _ args: [String], env: [String: String]? = nil, cwd: String? = nil,
                timeout: Double = 60) -> ProcResult {
    let p = Process()
    p.executableURL = URL(fileURLWithPath: exe)
    p.arguments = args
    if let env = env { p.environment = env }
    if let cwd = cwd {
        try? FileManager.default.createDirectory(atPath: cwd, withIntermediateDirectories: true)
        p.currentDirectoryURL = URL(fileURLWithPath: cwd)
    }
    let o = Pipe(), e = Pipe()
    p.standardOutput = o
    p.standardError = e
    p.standardInput = FileHandle.nullDevice
    let done = DispatchSemaphore(value: 0)
    p.terminationHandler = { _ in done.signal() }
    do { try p.run() } catch {
        return ProcResult(code: -1, out: "", err: "\(error.localizedDescription)", timedOut: false)
    }
    var od = Data(), ed = Data()
    let g = DispatchGroup()
    g.enter()
    DispatchQueue.global().async { od = o.fileHandleForReading.readDataToEndOfFile(); g.leave() }
    g.enter()
    DispatchQueue.global().async { ed = e.fileHandleForReading.readDataToEndOfFile(); g.leave() }
    var timedOut = false
    if done.wait(timeout: .now() + timeout) == .timedOut {
        timedOut = true
        p.terminate()
        if done.wait(timeout: .now() + 3) == .timedOut { kill(p.processIdentifier, SIGKILL); _ = done.wait(timeout: .now() + 2) }
    }
    _ = g.wait(timeout: .now() + 5)
    return ProcResult(code: p.isRunning ? -9 : p.terminationStatus, out: String(decoding: od, as: UTF8.self),
                      err: String(decoding: ed, as: UTF8.self), timedOut: timedOut)
}

// ---------------------------------------------------------------- the local API token (~/.queen/api_token)
enum LocalToken {
    /// A 48-character token, 0600, never logged.
    static func ensure(_ cfg: QueenConfig) -> String {
        let p = cfg.dataDir + "/api_token"
        if let t = Files.read(p)?.trimmingCharacters(in: .whitespacesAndNewlines), t.count >= 24 { return t }
        let t = randomHex(48)
        if Files.writeAtomic(p, Data((t + "\n").utf8), privateFile: true) { return t }
        return "local-queen-fallback-token"
    }
}
