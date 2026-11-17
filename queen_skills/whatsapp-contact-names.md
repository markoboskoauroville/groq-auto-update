# whatsapp-contact-names: the contact is the spelling authority

Marko, 17.11.2026: "always write the name as it is in his contact. You misspell the name, but the contact always has the right spelling."

Use when Marko says "write to / message / tell <name>" on WhatsApp, or any greeting with a person's name. The name he dictates is only a HINT (dictation: Vasil for Vasyl).

Steps:
1. Do not trust the spelling. Find the contact: `python3 ~/Developer/MACRO_SKILLS/tools/wa_type.py --find "<name as dictated>"` (types nothing; searches the chat list and WhatsApp search, folds accents/case/Cyrillic, private chats above groups, same ranking as rank_names).
2. It prints `CONTACT: <exact saved name>` and `GREETING_NAME: <first name>`. One clear winner: use it. Otherwise it lists the top 5: show them to Marko and type nothing.
3. Write the greeting with the contact's own spelling, exactly: contact "Vasyl Ros" gives "Bok Vasyl," (never Vasil, never the Croatian vocative Vasile). In the text pass `{name}` and wa_type.py fills it.
4. Type unsent with `wa_type.py "<name as dictated>" "<text with {name}>"`; Marko presses Send.

Example: "Marko says write to Vasil" -> contact Vasyl Ros (the group "Healing Journey with Vasyl Ros" ranks lower) -> greeting "Vasyl".
Macro Recorder catalogue: `macroskill has "find whatsapp contact by similar name"` (id whatsapp-find-contact). Rule: MANTRA_MANIFEST modules/names-are-hints.md.
