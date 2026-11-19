import SwiftUI
import AppKit

struct AutoUpdateMessage: Identifiable, Codable, Equatable {
    let id: String
    let role: String
    let content: String

    init(role: String, content: String) {
        id = UUID().uuidString
        self.role = role
        self.content = content
    }
}

struct AutoUpdateModelOption: Identifiable, Equatable {
    let id: String
    let name: String
}

@MainActor
final class AutoUpdateChat: ObservableObject {
    @Published var messages: [AutoUpdateMessage]
    @Published var provider = "google"
    @Published var model = ""
    @Published var providers: [String: String] = ["google": "Google Cloud / Gemini", "anthropic": "Anthropic / Claude"]
    @Published var models: [AutoUpdateModelOption] = []
    @Published var status = ""
    @Published var workingOn = ""
    @Published var events: [String] = []
    @Published var running = false
    @Published var configured = false
    @Published var error = ""
    @Published var needsAPIConsent = false
    private var pendingPrompt = ""
    private let historyKey = "queen.autoUpdateChat.history"

    init() {
        if let data = UserDefaults.standard.data(forKey: historyKey),
           let saved = try? JSONDecoder().decode([AutoUpdateMessage].self, from: data) {
            messages = saved
        } else {
            messages = []
        }
    }

    func load() async {
        await loadConfig()
        await refreshStatus()
    }

    func loadConfig() async {
        guard let config = await Queen.shared.json("/api/auto_update/config") else {
            error = "Queen's Auto Update API did not answer."
            return
        }
        provider = config["active_provider"] as? String ?? provider
        configured = false
        if let providerData = config["providers"] as? [String: [String: Any]] {
            for (id, value) in providerData {
                providers[id] = value["name"] as? String ?? id
            }
            configured = providerData[provider]?["configured"] as? Bool ?? false
            loadModels(providerData[provider]?["models"])
        }
        let activeModels = config["active_models"] as? [String: String] ?? [:]
        model = activeModels[provider] ?? (config["active_model"] as? String ?? model)
        if !models.contains(where: { $0.id == model }), let first = models.first {
            model = first.id
        }
        error = ""
    }

    func selectProvider(_ value: String) {
        guard !running, value != provider else { return }
        Task { @MainActor in
            guard let config = await Queen.shared.json("/api/auto_update/config", body: ["provider": value]) else {
                error = "Could not change the Auto Update provider."
                return
            }
            provider = config["active_provider"] as? String ?? value
            if let providerData = config["providers"] as? [String: [String: Any]] {
                configured = providerData[provider]?["configured"] as? Bool ?? false
                loadModels(providerData[provider]?["models"])
            }
            let activeModels = config["active_models"] as? [String: String] ?? [:]
            model = activeModels[provider] ?? (models.first?.id ?? "")
            error = ""
        }
    }

    func selectModel(_ value: String) {
        guard !running, value != model else { return }
        Task { @MainActor in
            guard let config = await Queen.shared.json("/api/auto_update/config", body: ["provider": provider, "model": value]) else {
                error = "Could not change the Auto Update model."
                return
            }
            model = config["active_model"] as? String ?? value
            error = ""
        }
    }

    func requestRun(_ prompt: String) {
        let trimmed = prompt.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !running else { return }
        pendingPrompt = trimmed
        messages.append(AutoUpdateMessage(role: "user", content: trimmed))
        persistHistory()
        run(trimmed, allowAPI: false)
    }

    func continueWithAPIConsent() {
        guard !pendingPrompt.isEmpty, !running else { return }
        needsAPIConsent = false
        run(pendingPrompt, allowAPI: true)
    }

    func cancelAPIConsent() {
        needsAPIConsent = false
        guard !pendingPrompt.isEmpty else { return }
        messages.append(AutoUpdateMessage(role: "assistant", content: "No paid API call was authorized; the update was not run."))
        persistHistory()
        pendingPrompt = ""
    }

    func refreshStatus() async {
        guard let result = await Queen.shared.json("/api/auto_update/status") else { return }
        status = (result["running"] as? Bool ?? false) ? "Running" : "Ready"
        workingOn = result["working_on"] as? String ?? ""
        if let recent = result["events"] as? [[String: Any]] {
            events = recent.suffix(12).map { event in
                let stage = event["stage"].map { "Stage \($0): " } ?? ""
                let detail = event["working_on"] as? String ?? event["message"] as? String ?? event["title"] as? String ?? ""
                return stage + detail
            }.filter { !$0.isEmpty }
        }
    }

    private func run(_ prompt: String, allowAPI: Bool) {
        running = true
        error = ""
        status = "Starting"
        workingOn = "Submitting the update request…"
        events = []
        Task { @MainActor in
            let poller = Task { @MainActor in
                while !Task.isCancelled && running {
                    await refreshStatus()
                    try? await Task.sleep(nanoseconds: 1_000_000_000)
                }
            }
            let response = await Queen.shared.json(
                "/api/auto_update/run",
                body: ["instruction": prompt, "provider": provider, "model": model, "dry_run": false, "allow_api": allowAPI],
                timeout: 1800
            )
            running = false
            poller.cancel()
            await refreshStatus()
            guard let response else {
                finish("Queen's Auto Update API did not return a response.", failed: true)
                return
            }
            if response["need_consent"] as? Bool == true {
                needsAPIConsent = true
                running = false
                status = "Waiting for API consent"
                workingOn = response["message"] as? String ?? "This update requires explicit API consent."
                return
            }
            if response["ok"] as? Bool != true {
                let detail = response["error"] as? String ?? "The update failed without an error message."
                finish(detail, failed: true)
                return
            }
            finish(summary(response), failed: false)
            await loadConfig()
        }
    }

    private func finish(_ content: String, failed: Bool) {
        messages.append(AutoUpdateMessage(role: failed ? "error" : "assistant", content: content))
        persistHistory()
        pendingPrompt = ""
        status = failed ? "Failed" : "Complete"
        workingOn = ""
    }

    private func summary(_ response: [String: Any]) -> String {
        if let report = response["report"] as? String {
            let via = response["via"] as? String ?? ""
            let next = response["next"] as? String ?? ""
            return [via.isEmpty ? "" : "Handled by \(via).", report, next].filter { !$0.isEmpty }.joined(separator: "\n\n")
        }
        var lines: [String] = []
        if let summary = response["summary"] as? String { lines.append(summary) }
        if let version = response["version"] as? String { lines.append("Version: \(version)") }
        if let files = response["files_changed"] as? [String], !files.isEmpty {
            lines.append("Files changed: " + files.joined(separator: ", "))
        }
        if let cost = response["cost"] as? [String: Any], let formatted = cost["formatted_usd"] as? String {
            lines.append("Update cost: \(formatted) USD")
        }
        if let next = response["next"] as? String { lines.append(next) }
        return lines.isEmpty ? "The update completed." : lines.joined(separator: "\n")
    }

    private func loadModels(_ raw: Any?) {
        guard let items = raw as? [[String: Any]] else {
            models = []
            return
        }
        models = items.compactMap { item in
            guard let id = item["id"] as? String else { return nil }
            return AutoUpdateModelOption(id: id, name: id)
        }
    }

    private func persistHistory() {
        messages = Array(messages.suffix(100))
        guard let data = try? JSONEncoder().encode(messages) else {
            error = "Could not save Auto Update chat history."
            return
        }
        UserDefaults.standard.set(data, forKey: historyKey)
    }
}

struct AutoUpdatePane: View {
    @ObservedObject var chat: AutoUpdateChat
    @State private var prompt = ""
    @State private var showRunConfirmation = false

    var body: some View {
        VStack(spacing: 0) {
            FlowLayout(spacing: 8, rowSpacing: 2) {
                HStack(spacing: 6) {
                    Text("AUTO UPDATE").foregroundStyle(Ink.accent).unit()
                    Text("|").foregroundStyle(Ink.dim).unit()
                    Text("PROMPT → REVIEWED UPDATE").foregroundStyle(Ink.dim).unit()
                }.unit()
                HStack(spacing: 4) {
                    Text("PROVIDER").foregroundStyle(Ink.dim).unit()
                    Picker("Provider", selection: Binding(get: { chat.provider }, set: { chat.selectProvider($0) })) {
                        ForEach(chat.providers.keys.sorted(), id: \.self) { key in
                            Text(chat.providers[key] ?? key).tag(key)
                        }
                    }
                    .pickerStyle(.menu)
                    .fixedSize()
                    .disabled(chat.running)
                }.unit()
                HStack(spacing: 4) {
                    Text("MODEL").foregroundStyle(Ink.dim).unit()
                    Picker("Model", selection: Binding(get: { chat.model }, set: { chat.selectModel($0) })) {
                        ForEach(chat.models) { option in Text(option.name).tag(option.id) }
                    }
                    .pickerStyle(.menu)
                    .fixedSize()
                    .disabled(chat.running || chat.models.isEmpty)
                }.unit()
            }
            .font(.system(size: 12, weight: .bold, design: .monospaced))
            .padding(.horizontal, 14).padding(.vertical, 8)
            Hairline()

            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 10) {
                        if chat.messages.isEmpty {
                            Text("Describe a Queen backend change. The pipeline validates its allowlisted files and, on the full update route, can bump the version, publish, and sync local files. Swift app source uses the GitHub mac-app release workflow.")
                                .font(.system(size: 14)).foregroundStyle(Ink.dim)
                                .fixedSize(horizontal: false, vertical: true)
                                .padding(16)
                        }
                        ForEach(chat.messages) { message in
                            messageBubble(message)
                                .id(message.id)
                        }
                        if chat.running || !chat.workingOn.isEmpty {
                            VStack(alignment: .leading, spacing: 5) {
                                Text(chat.status.uppercased()).font(.system(size: 11, weight: .bold, design: .monospaced))
                                    .foregroundStyle(chat.running ? Ink.amber : Ink.dim)
                                if !chat.workingOn.isEmpty {
                                    Text(chat.workingOn).font(.system(size: 12, design: .monospaced)).foregroundStyle(Ink.text)
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                                ForEach(Array(chat.events.enumerated()), id: \.offset) { _, event in
                                    Text(event).font(.system(size: 11, design: .monospaced)).foregroundStyle(Ink.dim)
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                            }
                            .padding(12)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .background(RoundedRectangle(cornerRadius: 8).fill(Ink.panel))
                            .id("activity")
                        }
                        Color.clear.frame(height: 1).id("end")
                    }
                    .padding(14)
                }
                .onChange(of: chat.messages) { _ in proxy.scrollTo("end", anchor: .bottom) }
                .onChange(of: chat.workingOn) { _ in proxy.scrollTo("activity", anchor: .bottom) }
            }

            if !chat.error.isEmpty {
                Text(chat.error).font(.system(size: 12, design: .monospaced)).foregroundStyle(Ink.red)
                    .textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 14).padding(.vertical, 6)
            }
            if !chat.configured {
                Text("No paid API key is configured. Local Claude Code may still handle this request; a paid route will need a key.")
                    .font(.system(size: 11, design: .monospaced)).foregroundStyle(Ink.amber)
                    .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 14).padding(.bottom, 5)
            }
            Hairline()
            VStack(alignment: .leading, spacing: 8) {
                TextEditor(text: $prompt)
                    .font(.system(size: 14))
                    .foregroundStyle(Ink.text)
                    .scrollContentBackground(.hidden)
                    .padding(6)
                    .frame(minHeight: 76, maxHeight: 140)
                    .background(RoundedRectangle(cornerRadius: 6).fill(Ink.panel))
                    .overlay(RoundedRectangle(cornerRadius: 6).stroke(Ink.line, lineWidth: 1))
                    .accessibilityIdentifier("auto-update-prompt")
                HStack {
                    Text("Backend allowlist only; Swift app source is released separately.")
                        .font(.system(size: 10, design: .monospaced)).foregroundStyle(Ink.dim)
                    Spacer()
                    Word(text: chat.running ? "RUNNING" : "RUN UPDATE", id: "auto-update-run",
                         color: chat.running ? Ink.amber : Ink.accent,
                         help: "Review and run this update request") {
                        guard !chat.running, !prompt.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
                        showRunConfirmation = true
                    }
                    .font(.system(size: 12, weight: .bold, design: .monospaced))
                }
            }
            .padding(12)
        }
        .background(Ink.bg)
        .onAppear { Task { await chat.load() } }
        .confirmationDialog("Run this Queen update?", isPresented: $showRunConfirmation, titleVisibility: .visible) {
            Button("Run update", role: .destructive) {
                let text = prompt
                prompt = ""
                chat.requestRun(text)
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Depending on the route, this can modify allowlisted backend files, bump the version, push changes to GitHub, and sync the local backend. Swift app source uses the separate GitHub mac-app release workflow.")
        }
        .alert("Allow a paid API call?", isPresented: Binding(
            get: { chat.needsAPIConsent },
            set: { chat.needsAPIConsent = $0 }
        )) {
            Button("Allow for this update") { chat.continueWithAPIConsent() }
            Button("Cancel", role: .cancel) { chat.cancelAPIConsent() }
        } message: {
            Text("The local Claude route is unavailable for this request. Queen needs your explicit approval before using the selected paid API.")
        }
    }

    @ViewBuilder
    private func messageBubble(_ message: AutoUpdateMessage) -> some View {
        let mine = message.role == "user"
        let color = message.role == "error" ? Ink.red : (mine ? Ink.accent : Ink.text)
        Text(markdown(message.content))
            .font(.system(size: 14))
            .foregroundStyle(color)
            .textSelection(.enabled)
            .fixedSize(horizontal: false, vertical: true)
            .padding(12)
            .frame(maxWidth: .infinity, alignment: mine ? .trailing : .leading)
            .background(RoundedRectangle(cornerRadius: 8).fill(Ink.panel))
    }

    private func markdown(_ value: String) -> AttributedString {
        (try? AttributedString(markdown: value, options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)))
            ?? AttributedString(value)
    }
}
