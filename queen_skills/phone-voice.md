When: Marko says "say on the pixel <text>", "speak on the pixel <text>", "send to the pixel <text>" (same for "nothing" = the Nothing Phone), or "phone status".
Rule (Marko, 13.11.2026 and 15.11.2026): a reply to Marko that goes to his phone is spoken by the phone's own Voice Engine, never a silent notification. Replies to Marko today go to the Pixel with `phonesay pixel en "<text>"`.
Steps: the local chat command (qwen_app/phone_say.py, $0, no model) runs `phonesay pixel en "<text>"` with the text as one argument (no shell). Write the text for listening: plain sentences, no paths or symbols.
"phone status" runs `phonesay status` (which phones answer on their daemon port 8840).
Check before saying "done": the answer starts "Spoken on the pixel:" and the phone's own line says it played. A "no answer" from phonesay means the phone's voice daemon is down: say so, do not fake it.
Never: speak on a phone without the words Marko asked to say; never play sound on the phone when Marko is testing with his Pixel at maximum volume (set by pixel-volume-during-tests).
Tested 15.11.2026: "phone status" answered by Queen in her chat; the speaking route was checked with the phone call mocked (no sound at the test).
