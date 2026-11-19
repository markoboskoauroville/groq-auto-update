// Queen.swift: status and the local HTTP connection shared by CAPI and Auto Update.
import Foundation
import AppKit

struct Msg: Identifiable, Equatable {
    let id = UUID()
    var role: String
    var content: String
    var cost: Double = 0
    var status: String = ""
    var reason: String = ""
    var label: String = ""
}

final class Queen: ObservableObject {
    static let shared = Queen()

    @Published var up = false
    @Published var line = "looking for Queen"
    @Published var version = ""
    @Published var starting = false
    @Published var backend = true

    private var timer: Timer?
    private let home = FileManager.default.homeDirectoryForCurrentUser.path

    static func bare(_ value: String) -> String {
        value.hasPrefix("v") ? String(value.dropFirst()) : value
    }

    var base: String { "http://127.0.0.1:8765" }

    private var token: String {
        ((try? String(contentsOfFile: home + "/.queen/api_token", encoding: .utf8)) ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
    }

    func request(_ path: String, body: [String: Any]? = nil, timeout: Double = 15) -> URLRequest? {
        guard let url = URL(string: base + path) else { return nil }
        var request = URLRequest(url: url, timeoutInterval: timeout)
        if !token.isEmpty { request.setValue(token, forHTTPHeaderField: "X-Queen-Token") }
        if let body {
            request.httpMethod = "POST"
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        }
        return request
    }

    func json(_ path: String, body: [String: Any]? = nil, timeout: Double = 15) async -> [String: Any]? {
        guard let request = request(path, body: body, timeout: timeout) else { return nil }
        do {
            let (data, _) = try await URLSession.shared.data(for: request)
            return try JSONSerialization.jsonObject(with: data) as? [String: Any]
        } catch {
            return nil
        }
    }

    func start() {
        linkAxread()
        Task { @MainActor in
            try? await Task.sleep(nanoseconds: 600_000_000)
            await refresh()
        }
        timer = Timer.scheduledTimer(withTimeInterval: 5, repeats: true) { [weak self] _ in
            Task { @MainActor in await self?.refresh() }
        }
    }

    func linkAxread() {
        let fileManager = FileManager.default
        let inner = Bundle.main.bundlePath + "/Contents/MacOS/axread"
        guard fileManager.isExecutableFile(atPath: inner) else { return }
        let directory = home + "/.local/bin"
        let link = directory + "/axread"
        try? fileManager.createDirectory(atPath: directory, withIntermediateDirectories: true)
        if let destination = try? fileManager.destinationOfSymbolicLink(atPath: link), destination == inner { return }
        if (try? fileManager.attributesOfItem(atPath: link)) != nil {
            guard (try? fileManager.destinationOfSymbolicLink(atPath: link)) != nil else { return }
            try? fileManager.removeItem(atPath: link)
        }
        try? fileManager.createSymbolicLink(atPath: link, withDestinationPath: inner)
    }

    @MainActor
    func refresh() async {
        if let status = await json("/api/app/status", timeout: 4), status["ok"] as? Bool == true {
            up = true
            starting = false
            version = Queen.bare("\(status["version"] ?? "")")
            backend = ((status["backend"] as? [String: Any])?["up"] as? Bool) ?? true
            line = "running"
        } else if let health = await json("/health", timeout: 4), health["ok"] as? Bool == true {
            up = true
            starting = false
            version = Queen.bare("\(health["version"] ?? "")")
            line = "running"
        } else {
            up = false
            line = starting ? "starting" : QueenHost.shared.line
        }
    }

    func startServer() {
        starting = true
        line = "starting"
        DispatchQueue.global().async {
            QueenHost.shared.restartBackend()
            DispatchQueue.main.asyncAfter(deadline: .now() + 6) { self.starting = false }
        }
    }

    func stopIfOurs() {
        QueenHost.shared.stop()
    }
}
