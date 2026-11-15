# Skill: vpn-mantra (Mac; local, no model, $0)

Marko, 15.11.2026 (training mode). **When:** "VPN status", "VPN Frankfurt", "VPN direct" (also "switch to VPN direct", "is the VPN on").
**What:** VPN (Mantra) = Tailscale exit node chromium-vm in Frankfurt. FRANKFURT = all internet through the VM, DIRECT = straight (Zagreb).
**Steps (code: qwen_app/ops_hands.py `chat_vpn`):** the CLI is `/Applications/Tailscale.app/Contents/MacOS/Tailscale` with `TAILSCALE_BE_CLI=1`, stdin /dev/null
(without that variable the binary starts the GUI and prints "The Tailscale GUI failed to start"). Status = `status --json`: BackendState must be Running, the exit
node in use is `ExitNodeStatus.ID`; the peer is the one with `ExitNodeOption` and HostName chromium-vm. Frankfurt = `set --exit-node=<100.x> --exit-node-allow-lan-access=true`;
direct = `set --exit-node=`. After a switch wait 3 s and read back status plus the public address (https://ipinfo.io/json, no key).
**Say:** one sentence: "VPN is FRANKFURT (through chromium-vm). Public address 130.61.181.83 (Frankfurt am Main, DE, Oracle)." DIRECT shows a Croatian address (Telemach).
**Check before "done":** the read-back says the mode asked for. **Traps:** never ask the GUI app's buttons (v2 buttons have no AX names); never switch when Tailscale is not Running
(say so); --exit-node-allow-lan-access keeps the Pixel/adb reachable. The VPN (Mantra) window follows by itself within its 10 minute refresh or on its next press. Repo MANTRA_VPN TAKEOVER.
