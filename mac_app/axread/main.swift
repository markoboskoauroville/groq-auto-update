// axread: the text of any Mac app through the Accessibility API, as JSON (Queen, 14.11.2026).
// Marko, 14.11.2026: "upgrade it with new skills for accessibility ... Without taking screenshots, it needs to use
// accessibility to get the text". Queen (qwen_app/ax_read.py, POST /api/ax/read) calls this; nothing is clicked or typed.
//
//   axread --app Firefox [--window TEXT] [--depth 60] [--max 8000] [--timeout 15] [--roles StaticText,Cell]
//          [--frames] [--focused] [--text] [--query TEXT]
//   axread --apps                 the running apps with a window
//   axread --trusted              {"trusted": true|false} (is the process that started this allowed under Accessibility)
//
// Output: {ok, trusted, app, pid, windows:[{role,title?,value?,description?,x?,y?,w?,h?,children?}], nodes, secs, truncated}
// Firefox and Chromium show their web pages (AXWebArea) only when an assistive client asks: AXManualAccessibility and
// AXEnhancedUserInterface are set on the app element first. Only windows on the current Space and the selected tab are there.
import AppKit
import ApplicationServices

let usage = """
axread --app <name> [--window TEXT] [--depth N] [--max N] [--timeout S] [--roles A,B] [--frames] [--focused] [--text] [--query TEXT]
axread --apps | --trusted
"""

var appName = ""
var windowFilter: String? = nil
var depthMax = 60
var maxNodes = 8000
var timeLimit = 15.0
var roles = Set<String>()
var frames = false
var focusedOnly = false
var asText = false
var query: String? = nil
var listApps = false
var onlyTrust = false

let args = Array(CommandLine.arguments.dropFirst())
var idx = 0
func nextArg() -> String {
    idx += 1
    return idx < args.count ? args[idx] : ""
}
while idx < args.count {
    switch args[idx] {
    case "--app", "-a": appName = nextArg()
    case "--window", "-w": windowFilter = nextArg()
    case "--depth", "-d": depthMax = Int(nextArg()) ?? 60
    case "--max": maxNodes = Int(nextArg()) ?? 8000
    case "--timeout", "-t": timeLimit = Double(nextArg()) ?? 15
    case "--roles":
        roles = Set(nextArg().split(separator: ",").map { r -> String in
            let s = String(r).trimmingCharacters(in: .whitespaces)
            return s.hasPrefix("AX") ? s : "AX" + s
        })
    case "--frames": frames = true
    case "--focused": focusedOnly = true
    case "--text": asText = true
    case "--query", "-q": query = nextArg()
    case "--apps": listApps = true
    case "--trusted": onlyTrust = true
    case "-h", "--help":
        print(usage)
        exit(0)
    default:
        if appName.isEmpty { appName = args[idx] }
    }
    idx += 1
}

func emit(_ o: [String: Any]) -> Never {
    if let d = try? JSONSerialization.data(withJSONObject: o, options: [.sortedKeys]),
       let s = String(data: d, encoding: .utf8) {
        print(s)
    } else {
        print("{\"ok\":false,\"error\":\"could not encode the result\"}")
    }
    exit(0)
}

let trusted = AXIsProcessTrusted()
if onlyTrust { emit(["ok": true, "trusted": trusted]) }

func norm(_ s: String) -> String { s.lowercased().filter { !$0.isWhitespace } }

let running = NSWorkspace.shared.runningApplications.filter { $0.activationPolicy != .prohibited }
if listApps {
    emit(["ok": true, "trusted": trusted, "apps": running.map { a -> [String: Any] in
        ["name": a.localizedName ?? "", "bundle": a.bundleIdentifier ?? "", "pid": Int(a.processIdentifier), "front": a.isActive]
    }])
}
guard trusted else {
    emit(["ok": false, "trusted": false, "via": "axread",
          "error": "Accessibility is not allowed for the process that started axread (System Settings > Privacy & Security > Accessibility)"])
}
guard !appName.isEmpty else { emit(["ok": false, "trusted": true, "error": "no --app given"]) }

let n = norm(appName)
let target = running.first { norm($0.localizedName ?? "") == n }
    ?? running.first { norm($0.localizedName ?? "").hasPrefix(n) }
    ?? running.first { norm($0.localizedName ?? "").contains(n) }
    ?? running.first { norm($0.bundleIdentifier ?? "").contains(n) }
guard let app = target else { emit(["ok": false, "trusted": true, "via": "axread", "error": "not running: " + appName]) }

func attr(_ e: AXUIElement, _ a: String) -> AnyObject? {
    var v: AnyObject?
    return AXUIElementCopyAttributeValue(e, a as CFString, &v) == .success ? v : nil
}

func plain(_ v: AnyObject?) -> Any? {
    guard let v = v else { return nil }
    if CFGetTypeID(v) == CFBooleanGetTypeID() { return (v as? Bool) ?? false }
    if let s = v as? String { return s.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty ? nil : s }
    if let num = v as? NSNumber {
        let d = num.doubleValue
        return d.isFinite ? num : nil
    }
    return nil
}

func point(_ e: AXUIElement) -> CGPoint? {
    guard let v = attr(e, kAXPositionAttribute), CFGetTypeID(v) == AXValueGetTypeID() else { return nil }
    var p = CGPoint.zero
    return AXValueGetValue(v as! AXValue, .cgPoint, &p) ? p : nil
}

func size(_ e: AXUIElement) -> CGSize? {
    guard let v = attr(e, kAXSizeAttribute), CFGetTypeID(v) == AXValueGetTypeID() else { return nil }
    var s = CGSize.zero
    return AXValueGetValue(v as! AXValue, .cgSize, &s) ? s : nil
}

let root = AXUIElementCreateApplication(app.processIdentifier)
AXUIElementSetMessagingTimeout(root, 3.0)
_ = AXUIElementSetAttributeValue(root, "AXManualAccessibility" as CFString, kCFBooleanTrue)
_ = AXUIElementSetAttributeValue(root, "AXEnhancedUserInterface" as CFString, kCFBooleanTrue)

let t0 = Date()
var count = 0
var truncated = false

func node(_ e: AXUIElement, _ d: Int) -> [String: Any]? {
    if count >= maxNodes || Date().timeIntervalSince(t0) > timeLimit {
        truncated = true
        return nil
    }
    count += 1
    let role = (attr(e, kAXRoleAttribute) as? String) ?? ""
    var o: [String: Any] = ["role": role]
    if let v = plain(attr(e, kAXTitleAttribute)) { o["title"] = v }
    if let v = plain(attr(e, kAXValueAttribute)) { o["value"] = v }
    if let v = plain(attr(e, kAXDescriptionAttribute)) { o["description"] = v }
    if frames, let p = point(e), let s = size(e), p.x.isFinite, p.y.isFinite, s.width.isFinite, s.height.isFinite {
        o["x"] = Double(p.x); o["y"] = Double(p.y); o["w"] = Double(s.width); o["h"] = Double(s.height)
    }
    if d < depthMax, let kids = attr(e, kAXChildrenAttribute) as? [AXUIElement] {
        var c: [[String: Any]] = []
        for k in kids {
            if let x = node(k, d + 1) { c.append(x) }
        }
        if !c.isEmpty { o["children"] = c }
    }
    if !roles.isEmpty && !roles.contains(role) && o["children"] == nil { return nil }
    return o
}

var tops: [AXUIElement] = []
if focusedOnly {
    if let f = attr(root, kAXFocusedUIElementAttribute), CFGetTypeID(f) == AXUIElementGetTypeID() {
        tops = [f as! AXUIElement]
    }
} else {
    tops = (attr(root, kAXWindowsAttribute) as? [AXUIElement]) ?? []
    if let wf = windowFilter?.lowercased(), !wf.isEmpty {
        tops = tops.filter { ((attr($0, kAXTitleAttribute) as? String) ?? "").lowercased().contains(wf) }
    }
}
var trees: [[String: Any]] = []
for w in tops {
    if let t = node(w, 0) { trees.append(t) }
}

func lines(_ t: [String: Any], _ d: Int, _ out: inout [(Int, String, String)]) {
    let parts = ["title", "value", "description"].compactMap { k -> String? in
        guard let v = t[k] else { return nil }
        return "\(v)"
    }
    if !parts.isEmpty { out.append((d, (t["role"] as? String) ?? "", parts.joined(separator: " | "))) }
    for c in (t["children"] as? [[String: Any]]) ?? [] { lines(c, d + 1, &out) }
}

var result: [String: Any] = ["ok": true, "trusted": true, "via": "axread", "app": app.localizedName ?? appName,
                             "pid": Int(app.processIdentifier), "nodes": count, "truncated": truncated,
                             "secs": (Date().timeIntervalSince(t0) * 100).rounded() / 100]
if let q = query?.lowercased(), !q.isEmpty {
    var all: [(Int, String, String)] = []
    for t in trees { lines(t, 0, &all) }
    result["matches"] = all.filter { $0.2.lowercased().contains(q) }.prefix(300).map { ["role": $0.1, "text": $0.2] }
} else if asText {
    var all: [(Int, String, String)] = []
    for t in trees { lines(t, 0, &all) }
    result["text"] = all.map { String(repeating: "  ", count: min($0.0, 12)) + $0.1.replacingOccurrences(of: "AX", with: "") + ": " + $0.2 }
        .joined(separator: "\n")
} else {
    result["windows"] = trees
}
emit(result)
