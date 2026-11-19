// Updater.swift: the app updates itself from its own GitHub releases (Marko, 14.11.2026: "When the application starts,
// AUTO MODE (Queen, Marko 17.11.2026: "update is happening automatically"): Config.auto = true skips the question; the swap script signs axread and the app, relaunches, and leaves update-result.txt (ok vN / failed vN: reason). A failed version is not retried in a loop.
// it checks for it, downloads it, and asks you, 'Do you want to update?' Then I say 'yes,' and it downloads and runs the
// update."). One file, the same in every Mac app: only the three constants in Updater.Config change.
//
// At start (a few seconds after launch, in the background): `gh release view` on the app's repository (private repos
// work, gh is signed in on the Mac). A Latest tag vN with N > VERSION: the release's app.zip is downloaded quietly to
// ~/Library/Caches/<bundle id>/update, unpacked and checked, then the question is asked. Yes: a small script waits for
// this app to quit, swaps the new .app in at the same path (the old one kept until the new one is signed "Mantra Apps",
// so Accessibility and the other permissions stay), and opens it. Later: nothing changes, the question comes again at the
// next start. No gh, no network, no newer release: silent.
import AppKit

enum Updater {
    struct Config {
        static let repo = "markoboskoauroville/groq_ai_studio"
        static let asset = "app.zip"
        static let sign = "Mantra Apps"
        static let auto = true     // Queen (Marko, 17.11.2026): updates by itself, no question. false = ask (the kit default)
    }

    static var busy = false
    static let gh = ["/opt/homebrew/bin/gh", "/usr/local/bin/gh"].first { FileManager.default.isExecutableFile(atPath: $0) }
    static var cache: URL {
        let id = Bundle.main.bundleIdentifier ?? APP_NAME
        return FileManager.default.homeDirectoryForCurrentUser.appendingPathComponent("Library/Caches/\(id)/update")
    }

    /// Called once from applicationDidFinishLaunching. `manual` (from the settings panel) also says "up to date".
    static func checkAtStart(delay: Double = 4, manual: Bool = false) {
        guard !busy else { return }
        showLastResult()
        busy = true
        DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + delay) {
            let found = findAndDownload()
            DispatchQueue.main.async {
                busy = false
                if let (v, app, notes) = found {
                    if Config.auto { install(app, version: v) } else { ask(version: v, newApp: app, notes: notes) }
                }
                else if manual { tell("\(APP_NAME) v\(VERSION) is the newest version.") }
            }
        }
    }

    /// The Latest release; downloaded and unpacked when it is newer. Returns (version, path of the new .app, notes).
    static func findAndDownload() -> (Int, URL, String)? {
        guard let gh else { log("no gh on this Mac"); return nil }
        guard let out = run(gh, ["release", "view", "--repo", Config.repo, "--json", "tagName,name,body"]),
              let j = try? JSONSerialization.jsonObject(with: Data(out.utf8)) as? [String: Any],
              let tag = j["tagName"] as? String,
              let v = Int(tag.filter(\.isNumber)) else { log("no release info"); return nil }
        guard v > VERSION else { log("v\(VERSION) is the newest (Latest is \(tag))"); return nil }
        if Config.auto, let r = try? String(contentsOf: resultFile, encoding: .utf8), r.hasPrefix("failed v\(v):") {
            log("v\(v) failed to install before (\(r)); not trying again automatically"); return nil
        }
        let fm = FileManager.default
        let dir = cache.appendingPathComponent(tag)
        let zip = dir.appendingPathComponent(Config.asset)
        let unpacked = dir.appendingPathComponent("app")
        let appName = (Bundle.main.bundlePath as NSString).lastPathComponent
        let newApp = unpacked.appendingPathComponent(appName)
        if !fm.fileExists(atPath: newApp.path) {       // never download the same version twice (SIM data)
            try? fm.removeItem(at: cache)
            try? fm.createDirectory(at: unpacked, withIntermediateDirectories: true)
            guard run(gh, ["release", "download", tag, "--repo", Config.repo, "--pattern", Config.asset,
                           "-D", dir.path, "--clobber"]) != nil,
                  run("/usr/bin/ditto", ["-x", "-k", zip.path, unpacked.path]) != nil,
                  fm.fileExists(atPath: newApp.path) else { log("download of \(tag) failed"); try? fm.removeItem(at: dir); return nil }
        }
        let notes = ((j["body"] as? String) ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        log("v\(v) downloaded, asking")
        return (v, newApp, notes)
    }

    static func ask(version v: Int, newApp: URL, notes: String) {
        NSApp.activate(ignoringOtherApps: true)
        let a = NSAlert()
        a.messageText = "\(APP_NAME) v\(v) is ready"
        a.informativeText = "You have v\(VERSION). Do you want to update?" + (notes.isEmpty ? "" : "\n\nWhat is new: \(notes.prefix(400))")
        a.addButton(withTitle: "Update")
        a.addButton(withTitle: "Later")
        if let icon = NSImage(contentsOf: newApp.appendingPathComponent("Contents/Resources/AppIcon.icns")) { a.icon = icon }
        guard a.runModal() == .alertFirstButtonReturn else { log("v\(v): later"); return }
        install(newApp, version: v)
    }

    static var resultFile: URL { cache.deletingLastPathComponent().appendingPathComponent("update-result.txt") }

    /// The swap script leaves one line ("ok vN" / "failed vN: reason"); shown once, quietly, at the next start.
    static func showLastResult() {
        guard let r = try? String(contentsOf: resultFile, encoding: .utf8) else { return }
        let line = r.trimmingCharacters(in: .whitespacesAndNewlines)
        if line.hasPrefix("ok v"), line == "ok v\(VERSION)" {
            try? FileManager.default.removeItem(at: resultFile)
            DispatchQueue.main.asyncAfter(deadline: .now() + 2) { toast("Updated to v\(VERSION)") }
        } else if line.hasPrefix("failed") {
            log(line)   // kept on disk so the same version is not retried in a loop
            DispatchQueue.main.asyncAfter(deadline: .now() + 2) { toast("Update not installed (\(line.dropFirst(7))). Still v\(VERSION).") }
        }
    }

    /// A small non-blocking note at the bottom of the screen, gone after 6 seconds.
    static func toast(_ s: String) {
        let label = NSTextField(labelWithString: s)
        label.textColor = .white; label.font = .systemFont(ofSize: 13, weight: .medium)
        label.sizeToFit()
        let w = NSWindow(contentRect: NSRect(x: 0, y: 0, width: label.frame.width + 28, height: label.frame.height + 16),
                         styleMask: [.borderless], backing: .buffered, defer: false)
        w.isOpaque = false; w.backgroundColor = NSColor.black.withAlphaComponent(0.85); w.level = .floating
        w.hasShadow = true; w.ignoresMouseEvents = true; w.isReleasedWhenClosed = false
        label.frame.origin = NSPoint(x: 14, y: 8); w.contentView?.addSubview(label)
        if let f = (NSApp.keyWindow ?? NSApp.windows.first)?.frame ?? NSScreen.main?.frame {
            w.setFrameOrigin(NSPoint(x: f.midX - w.frame.width / 2, y: f.minY + 40))
        }
        w.orderFrontRegardless()
        DispatchQueue.main.asyncAfter(deadline: .now() + 6) { w.close() }
    }

    /// The swap runs in a detached shell after this app quits; the old copy comes back if anything fails.
    static func install(_ newApp: URL, version v: Int) {
        let target = Bundle.main.bundlePath
        let script = cache.deletingLastPathComponent().appendingPathComponent("install.sh")
        let sh = """
        #!/bin/sh
        T="$1"; N="$2"; P="$3"; S="$4"; V="$5"; R="$6"
        fail() { echo "failed v$V: $1" > "$R"; open "$T"; exit 1; }
        while kill -0 "$P" 2>/dev/null; do sleep 0.2; done
        xattr -dr com.apple.quarantine "$N" 2>/dev/null
        [ -f "$N/Contents/MacOS/axread" ] && { codesign --force -s "$S" "$N/Contents/MacOS/axread" 2>/dev/null || true; }
        codesign --force -s "$S" "$N" 2>/dev/null || fail "could not sign with $S"
        rm -rf "$T.old"; mv "$T" "$T.old" || fail "could not move the old copy"
        if ditto "$N" "$T"; then rm -rf "$T.old"; else rm -rf "$T"; mv "$T.old" "$T"; fail "copy failed"; fi
        echo "ok v$V" > "$R"
        open "$T"
        """
        do { try FileManager.default.createDirectory(at: script.deletingLastPathComponent(), withIntermediateDirectories: true)
             try sh.write(to: script, atomically: true, encoding: .utf8) } catch { toast("Update failed: \(error)"); return }
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/bin/sh")
        p.arguments = [script.path, target, newApp.path, String(getpid()), Config.sign, String(v), resultFile.path]
        p.standardOutput = FileHandle.nullDevice; p.standardError = FileHandle.nullDevice
        do { try p.run() } catch { toast("Update failed: \(error)"); return }
        log("installing v\(v) from \(newApp.path) over \(target)")
        Delegate.quitWithoutAsking = true       // the swap script waits for this process: no Quit guard question
        NSApp.terminate(nil)
    }

    static func tell(_ s: String) {
        let a = NSAlert(); a.messageText = APP_NAME; a.informativeText = s; a.runModal()
    }

    @discardableResult
    static func run(_ exe: String, _ args: [String]) -> String? {
        let p = Process(), out = Pipe()
        p.executableURL = URL(fileURLWithPath: exe); p.arguments = args
        p.standardOutput = out; p.standardError = FileHandle.nullDevice
        var env = ProcessInfo.processInfo.environment
        env["PATH"] = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"; env["GH_PROMPT_DISABLED"] = "1"
        p.environment = env
        do { try p.run() } catch { return nil }
        let data = out.fileHandleForReading.readDataToEndOfFile()
        p.waitUntilExit()
        return p.terminationStatus == 0 ? String(decoding: data, as: UTF8.self) : nil
    }

    static func log(_ s: String) { NSLog("[Updater] %@", s) }
}
