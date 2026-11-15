Skill: turn USB tethering on or off on the Nothing phone (15.11.2026, taught by Claude Code)
Marko, 15.11.2026: he is tired of digging through the Nothing's settings to share its internet over USB. The phone has the app
"USB Tethering (Mantra)" (repo USB_TETHERING, widget + Quick Settings tile). When Marko asks you "turn on USB tethering on the
Nothing" (or off), YOU do it from the Mac over adb. You have no shell: answer with the command lines below, plain, one per line.

The Nothing Phone 2a is adb device 100.67.149.40:5555 (Tailscale). First check it is there:
  adb connect 100.67.149.40:5555
  adb devices
If it says offline or not found: say "The Nothing is not reachable over adb" and stop. Never skip the step silently.

ON:   adb -s 100.67.149.40:5555 shell svc usb setFunctions rndis
OFF:  adb -s 100.67.149.40:5555 shell svc usb setFunctions
STATE: adb -s 100.67.149.40:5555 shell getprop sys.usb.state     (contains rndis = ON)
Read the state back after 2 seconds and tell Marko ON or OFF. Do not tap the phone's screen.

Traps: 1. Marko must be watching any phone action: ask first by voice when he is not at the desk. 2. The command changes the USB
function of the phone, so a USB adb cable session may drop; the Tailscale adb stays. 3. macOS has no built-in RNDIS driver: the
Mac may not see the network; say so. 4. The app's widget and tile are his one-tap way on the phone itself (they need Shizuku
started, once after every reboot of the phone); you are the way from the Mac.
