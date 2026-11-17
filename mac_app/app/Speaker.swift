// Speaker.swift: the speaker icon at the end of every chat response (17.11.2026). Marko: "speaker icon at end of each chat
// response to play audio from chat text using speechify key beatrice voice". Click renders the text to an mp3 first
// (POST /api/speak/render: Speechify Beatrice, Croatian = Gabrijela, cached per text), then plays the file; click again
// stops. One component for every chat (Bubble shows it), no streamed speech.
import SwiftUI
import AVFoundation

final class Speaker: NSObject, ObservableObject, AVAudioPlayerDelegate {
    static let shared = Speaker()
    @Published var playing: UUID? = nil
    @Published var loading: UUID? = nil
    @Published var note = ""
    private var player: AVAudioPlayer?

    func toggle(_ m: Msg) {
        if playing == m.id || loading == m.id { stop(); return }
        stop()
        loading = m.id
        note = ""
        let id = m.id, text = m.content
        Task { @MainActor in
            let j = await Queen.shared.json("/api/speak/render", body: ["text": text], timeout: 300)
            guard self.loading == id else { return }            // stopped while rendering
            guard let f = j?["file"] as? String, let p = try? AVAudioPlayer(contentsOf: URL(fileURLWithPath: f)) else {
                self.loading = nil
                self.note = (j?["error"] as? String) ?? "No sound."
                return
            }
            p.delegate = self
            p.play()
            self.player = p
            self.loading = nil
            self.playing = id
        }
    }

    func stop() {
        player?.stop()
        player = nil
        playing = nil
        loading = nil
    }

    func audioPlayerDidFinishPlaying(_ p: AVAudioPlayer, successfully ok: Bool) {
        DispatchQueue.main.async { if self.player === p { self.player = nil; self.playing = nil } }
    }
}

struct SpeakerButton: View {
    let m: Msg
    @ObservedObject var sp = Speaker.shared
    var body: some View {
        let on = sp.playing == m.id
        let wait = sp.loading == m.id
        Image(systemName: on ? "stop.fill" : (wait ? "hourglass" : "speaker.wave.2.fill"))
            .font(.system(size: 13))
            .foregroundStyle(on ? Ink.amber : Ink.dim)
            .frame(width: 28, height: 24)
            .contentShape(Rectangle())
            .onTapGesture { sp.toggle(m) }
            .axButton(on ? "Stop speaking" : "Speak", id: "speak-" + String(m.id.uuidString.prefix(8)),
                      value: on ? "playing" : (wait ? "rendering" : "idle")) { sp.toggle(m) }
            .pressHover()
            .help(on ? "Stop" : "Read this answer aloud (Beatrice)")
    }
}
