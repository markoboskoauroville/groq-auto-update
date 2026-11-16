# google-photos-album (Mac only): put local pictures into a Google Photos album and make its share link

Marko, 16.11.2026: "make gallery in my Google photos and then we're going to share it with Svemir". First used for the
wooden-mannequin Wyoga poses (album "Wyoga poses (wooden mannequin)", 16 stills from ~/Developer/SKELETON/docs/poses).
**When:** "make an album in my Google Photos with <these pictures / that folder>", "upload <folder> to Google Photos",
"make a gallery of <...> and give me the link", "share link for the album <name>".

**Call:** `POST /api/gphotos/album {"album": "<title>", "files": ["/abs/path.jpg", ...], "share": true}`
-> `{ok, account, album_url, share_link, log}`. With `"files": []` it only returns the share link of the existing album
with that title (nothing uploaded). Same from a terminal:
`python3 ~/.groq/qwen_app/gphotos_album.py make --album "<title>" <files...> --share` (prints ACCOUNT, ALBUM, SHARE);
`... gphotos_album.py share --album-url <url>` for the link of an existing album; `... account` reads the signed-in account.

**How it works:** Marko's own Firefox over WebDriver BiDi (port 9222 or 9223, whichever Firefox holds), a tab of its own:
Albums -> Create album -> title typed with real keys -> Add photos -> Select from computer. The page's file input is caught
by a hook (no macOS dialog); BiDi `input.setFiles` is REFUSED by Google Photos (InvalidStateError), so the files are built in
the page (base64 -> File -> DataTransfer -> input.files -> change). Then Share -> Create link -> the confirm dialog
"Create link to share" -> Create link; the link (https://photos.app.goo.gl/...) is read from the page. The tab is closed after.
If an album with the same title already exists, the pictures go into it (never a second album with the same name).

**Rules:** the account is whatever Firefox is signed in to (marko.bosko@gmail.com on 16.11.2026): report it, never sign in
or out. The link is only given back to Marko, NEVER sent to anyone (Claude writes, Marko sends). Over the 4G SIM keep the set
small (JPEG q90, say the total MB before). No duplicates in the upload. Check afterwards: the album page shows N photos.

**Traps met (16.11.2026):** a BiDi script that dies without `session.end` blocks Firefox's remote control ("Maximum number
of active sessions") until Firefox restarts: the tool ends its session in `finally`. A restart of Firefox needs Marko's yes.
Pressing "Create album" makes an empty untitled album at once: if a run stops there, delete that empty album
(More options -> Delete album -> Delete), only when it is untitled AND has no items.
