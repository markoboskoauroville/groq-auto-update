"""Google Photos album from local pictures, in Marko's own Firefox (16.11.2026).

Marko, 16.11.2026: "make gallery in my Google photos and then we're going to share it with Svemir".
Firefox is driven over WebDriver BiDi (firefoxctl's connection; port found by ffport): real pointer and key input
(input.performActions, inside Firefox only, never his real mouse), files given to the page's own file input with
input.setFiles (no macOS file dialog). The account is the one Firefox is signed in to (read and reported, never changed).

    python3 qwen_app/gphotos_album.py account
    python3 qwen_app/gphotos_album.py make --album "NAME" FILE... [--share]     -> prints ALBUM <url> and SHARE <link>
    python3 qwen_app/gphotos_album.py share --album-url URL                      -> prints SHARE <link>

Route (Queen): POST /api/gphotos/album {album, files:[paths], share:true}  -> {ok, account, album_url, share_link, log}
       files empty = only the share link of the existing album with that title (nothing uploaded).
The link is only created and printed: it is NEVER sent to anyone.
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def _firefoxctl():
    os.environ.setdefault("FIREFOXCTL_PORT", _port())
    path = os.path.expanduser("~/.local/bin/firefoxctl")
    loader = importlib.machinery.SourceFileLoader("firefoxctl_mod", path)
    spec = importlib.util.spec_from_loader("firefoxctl_mod", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def _port():
    try:
        from ffport import firefox_port
        return firefox_port("9222")
    except Exception:
        return "9222"


class GErr(Exception):
    pass


class Page:
    """One Firefox tab on photos.google.com with real input."""

    def __init__(self, log=print):
        self.log = log
        fc = _firefoxctl()
        fc.die = self._die
        self.fc = fc
        self.b = fc.Bidi()
        self.ctx = None
        self.own_tab = False

    @staticmethod
    def _die(msg, code=1):
        raise GErr(msg)

    def open(self, url, new=False):
        if new or self.ctx is None:
            self.ctx = self.b.call("browsingContext.create", {"type": "tab"})["context"]
            self.own_tab = True
        self.b.call("browsingContext.navigate", {"context": self.ctx, "url": url, "wait": "complete"})
        time.sleep(2.5)

    def js(self, expr):
        return self.b.js(self.ctx, expr)

    def node(self, css_or_js):
        """A shared reference to an element (for input.setFiles). css, or a JS expression returning the element."""
        expr = css_or_js if css_or_js.startswith("(") else f"document.querySelector({json.dumps(css_or_js)})"
        r = self.b.call("script.evaluate", {"expression": expr, "target": {"context": self.ctx},
                                            "awaitPromise": False, "resultOwnership": "root"})
        res = r.get("result", {})
        if res.get("type") != "node":
            raise GErr("no element for " + css_or_js)
        return {"sharedId": res["sharedId"]}

    def rect(self, finder):
        """finder: JS expression returning an element; returns its centre in CSS pixels (scrolled into view)."""
        return self.js(f"(() => {{ const e = {finder}; if (!e) return null; e.scrollIntoView({{block:'center'}});"
                       f" const r = e.getBoundingClientRect(); return [r.x + r.width/2, r.y + r.height/2, r.width, r.height]; }})()")

    def click(self, finder, what=""):
        r = self.rect(finder)
        if not r or r[2] == 0:
            raise GErr("not on the page: " + (what or finder))
        x, y = int(r[0]), int(r[1])
        self.b.call("input.performActions", {"context": self.ctx, "actions": [{
            "type": "pointer", "id": "mouse", "parameters": {"pointerType": "mouse"},
            "actions": [{"type": "pointerMove", "x": x, "y": y, "duration": 120},
                        {"type": "pointerDown", "button": 0}, {"type": "pause", "duration": 60},
                        {"type": "pointerUp", "button": 0}]}]})
        self.b.call("input.releaseActions", {"context": self.ctx})
        self.log(f"click {what or finder} at {x},{y}")
        time.sleep(1.2)

    def keys(self, text):
        acts = []
        for ch in text:
            acts += [{"type": "keyDown", "value": ch}, {"type": "keyUp", "value": ch}]
        self.b.call("input.performActions", {"context": self.ctx, "actions": [
            {"type": "key", "id": "kb", "actions": acts}]})
        self.b.call("input.releaseActions", {"context": self.ctx})

    def key(self, value):
        self.b.call("input.performActions", {"context": self.ctx, "actions": [
            {"type": "key", "id": "kb", "actions": [{"type": "keyDown", "value": value}, {"type": "keyUp", "value": value}]}]})
        self.b.call("input.releaseActions", {"context": self.ctx})

    def text(self):
        return self.js("document.body.innerText") or ""

    def wait_for(self, finder, seconds=20, what=""):
        t0 = time.time()
        while time.time() - t0 < seconds:
            if self.js(f"!!({finder})"):
                return True
            time.sleep(0.7)
        raise GErr("waited %ds for %s" % (seconds, what or finder))

    def close(self, close_tab=True):
        """Close the tab this tool opened, then ALWAYS end the BiDi session (a session left open blocks Firefox's
        remote control until Firefox restarts: "Maximum number of active sessions")."""
        try:
            if close_tab and self.own_tab and self.ctx:
                self.b.call("browsingContext.close", {"context": self.ctx})
        except Exception:
            pass
        finally:
            try:
                self.b.call("session.end")
            except BaseException:
                pass
            try:
                self.b.ws.close()
            except Exception:
                pass


def by_label(label, tag="*"):
    """JS: the first visible element whose aria-label or text equals/starts with label."""
    L = json.dumps(label.lower())
    return (f"[...document.querySelectorAll('{tag}')].find(e => {{ const r = e.getBoundingClientRect();"
            f" if (!r.width || !r.height) return false; const a = (e.getAttribute('aria-label') || '').toLowerCase().trim();"
            f" const t = (e.innerText || '').toLowerCase().trim(); return a === {L} || t === {L}; }})")


def account(p):
    lab = p.js("(document.querySelector('a[aria-label^=\"Google Account\"]')||{}).getAttribute?"
               " document.querySelector('a[aria-label^=\"Google Account\"]').getAttribute('aria-label') : ''")
    m = re.search(r"\(([^)]+@[^)]+)\)", lab or "")
    return m.group(1) if m else (lab or "?")


def find_album(p, title, wait=15):
    """URL of the user's own album with exactly this title, or None (the album grid loads lazily: retried for `wait` s)."""
    t0 = time.time()
    while True:
        url = _find_album_once(p, title)
        if url or time.time() - t0 > wait:
            return url
        time.sleep(1)


def _find_album_once(p, title):
    """The card's title is a leaf element; its link is /album/... or, once shared, /share/...?key=..."""
    return p.js(f"(() => {{ const e = [...document.querySelectorAll('div,span')].find(e => e.children.length === 0 &&"
                f" (e.textContent || '').trim() === {json.dumps(title)} && e.closest('a[href*=\"/album/\"], a[href*=\"/share/\"]'));"
                f" return e ? e.closest('a').href : null; }})()")


def make_album(p, title, files):
    p.open("https://photos.google.com/albums", new=True)
    acc = account(p)
    p.log("account " + acc)
    if "accounts.google.com" in (p.js("location.href") or ""):
        raise GErr("Firefox is not signed in to Google Photos: Marko signs in himself")
    have = find_album(p, title)
    if have:   # a run that stopped half-way: add to the same album, never a second one with the same name
        p.log("album exists, adding to it: " + have)
        p.open(have)
        upload(p, files)
        return acc, p.js("location.href")
    p.click(by_label("Create album", "button,[role=button],a"), "Create album")
    # the new album page: a title box, then "Select photos"
    title_box = "document.querySelector('textarea[aria-label=\"Edit album name\"], textarea[aria-label*=\"title\" i], textarea')"
    p.wait_for(title_box, 20, "the album title box")
    p.click(title_box, "album title")
    p.keys(title)
    time.sleep(0.6)
    got = p.js(f"({title_box}).value")
    p.log(f"title typed: {got!r}")
    upload(p, files)
    url = p.js("location.href")
    return acc, url


def upload(p, files):
    """Add local files to the album that is open: 'Select photos' -> 'Select from computer' -> the file input."""
    files = [os.path.abspath(f) for f in files]
    for f in files:
        if not os.path.isfile(f):
            raise GErr("no such file: " + f)
    # hook: the page creates/clicks an <input type=file>; keep it instead of opening the macOS dialog
    p.js("(() => { if (window.__gpHook) return 1; window.__gpHook = 1; const o = HTMLInputElement.prototype.click;"
         " HTMLInputElement.prototype.click = function () { if (this.type === 'file') { window.__fi = this;"
         " if (!this.isConnected) { this.style.display = 'none'; document.body.appendChild(this); } return; } return o.apply(this, arguments); };"
         " return 1; })()")
    opened = False
    for lab in ("Select photos", "Add photos", "Add to album"):
        if p.js(f"!!({by_label(lab, 'button,[role=button],[role=menuitem],a')})"):
            p.click(by_label(lab, "button,[role=button],[role=menuitem],a"), lab)
            opened = True
            break
    if not opened:
        raise GErr("no 'Select photos' button on the album page")
    for lab in ("Select from computer", "From computer", "Upload from computer"):
        f = by_label(lab, "button,[role=button],[role=menuitem],[role=option],span,div")
        if p.js(f"!!({f})"):
            p.click(f, lab)
            break
    time.sleep(1.0)
    if not p.js("!!window.__fi"):
        # some layouts keep a permanent input in the page
        if not p.js("!!document.querySelector('input[type=file]')"):
            raise GErr("the page made no file input")
        p.js("(window.__fi = document.querySelector('input[type=file]'), 1)")
    try:
        el = p.node("(window.__fi)")
        p.b.call("input.setFiles", {"context": p.ctx, "element": el, "files": files})
        p.log(f"setFiles: {len(files)} files given to the page")
    except GErr as e:
        # Google Photos (like Gmail and WhatsApp) refuses BiDi setFiles (InvalidStateError): build the files IN the page
        p.log("setFiles refused (%s): building the files in the page" % str(e)[:60])
        p.js("(window.__files = [], 1)")
        import base64
        import mimetypes
        for f in files:
            b64 = base64.b64encode(open(f, "rb").read()).decode()
            typ = mimetypes.guess_type(f)[0] or "image/jpeg"
            p.js(f"(window.__files.push(new File([Uint8Array.from(atob({json.dumps(b64)}), c => c.charCodeAt(0))],"
                 f" {json.dumps(os.path.basename(f))}, {{type: {json.dumps(typ)}}})), window.__files.length)")
        n = p.js("(() => { const dt = new DataTransfer(); window.__files.forEach(f => dt.items.add(f));"
                 " window.__fi.files = dt.files; window.__fi.dispatchEvent(new Event('input', {bubbles: true}));"
                 " window.__fi.dispatchEvent(new Event('change', {bubbles: true})); return window.__fi.files.length; })()")
        p.log(f"{n} files handed to the page's file input")
    # wait until the uploads finish (the counter text disappears / items appear)
    t0 = time.time()
    last = ""
    while time.time() - t0 < 60 * 15:
        txt = p.text()
        m = re.search(r"(Uploading[^\n]*|\d+ of \d+[^\n]*)", txt)
        cur = m.group(1) if m else ""
        if cur != last and cur:
            p.log("upload: " + cur)
            last = cur
        if not cur and time.time() - t0 > 8:
            break
        time.sleep(2)
    # the album may show a "Done" button after adding (the new-album flow)
    done = by_label("Done", "button,[role=button]")
    if p.js(f"!!({done})"):
        p.click(done, "Done")
    time.sleep(2)


def share_link(p):
    """Share -> Create link -> the link text. Never sends it."""
    p.click(by_label("Share", "button,[role=button]"), "Share")
    time.sleep(1.5)
    first = ("[...document.querySelectorAll('[role=dialog] [role=button], [role=dialog] button')].find(e =>"
             " e.getBoundingClientRect().width && (e.innerText || '').trim().startsWith('Create link'))")
    if p.js(f"!!({first})"):
        p.click(first, "Create link")
        time.sleep(1.5)
    # second dialog "Create link to share ... Let anyone with the link see ...": its own Create link button confirms
    confirm = ("(() => { const d = [...document.querySelectorAll('[role=dialog]')].filter(d => /Create link to share/.test(d.innerText)).pop();"
               " return d ? [...d.querySelectorAll('button,[role=button]')].filter(e => e.getBoundingClientRect().width &&"
               " (e.innerText || '').trim() === 'Create link').pop() : null; })()")
    if p.js(f"!!({confirm})"):
        p.click(confirm, "Create link (confirm)")
    # an album that already has a link shows "Copy link" instead: the link then comes from the clipboard
    copy = ("[...document.querySelectorAll('[role=dialog] [role=button], [role=dialog] button')].find(e =>"
            " e.getBoundingClientRect().width && (e.innerText || '').trim() === 'Copy link')")
    if not p.js(f"!!({first})") and p.js(f"!!({copy})"):
        import subprocess
        before = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout
        p.click(copy, "Copy link")
        for _ in range(20):
            clip = subprocess.run(["pbpaste"], capture_output=True, text=True).stdout.strip()
            if clip != before.strip() and re.match(r"https://(photos\.app\.goo\.gl|photos\.google\.com/share)/", clip):
                p.key("\uE00C")
                return clip      # left on the clipboard, as "Copy link" means
            time.sleep(0.5)
    t0 = time.time()
    while time.time() - t0 < 30:
        link = p.js("(() => { const t = document.body.innerText.match(/https:\\/\\/(photos\\.app\\.goo\\.gl\\/[A-Za-z0-9]+|photos\\.google\\.com\\/share\\/[^\\s]+)/);"
                    " if (t) return t[0]; const i = [...document.querySelectorAll('input')].map(e => e.value)"
                    ".find(v => /photos\\.app\\.goo\\.gl|photos\\.google\\.com\\/share/.test(v)); return i || ''; })()")
        if link:
            p.key("")   # Escape closes the share sheet; nothing is sent
            return link
        time.sleep(1)
    raise GErr("no share link appeared")


def run(album, files, share=True, log=print):
    p = Page(log)
    try:
        if not files:   # no pictures: only the link of the existing album with this title
            p.open("https://photos.google.com/albums", new=True)
            acc = account(p)
            url = find_album(p, album)
            if not url:
                raise GErr("no album titled " + album)
            p.open(url)
            return {"ok": True, "account": acc, "album_url": url, "share_link": share_link(p) if share else ""}
        acc, url = make_album(p, album, files)
        link = share_link(p) if share else ""
        return {"ok": True, "account": acc, "album_url": url, "share_link": link}
    finally:
        p.close()


def register(app):
    from flask import jsonify, request

    @app.route("/api/gphotos/album", methods=["POST"])
    def _gphotos_album():
        d = request.get_json(force=True, silent=True) or {}
        lines = []
        try:
            res = run(d.get("album") or "Album", d.get("files") or [], bool(d.get("share", True)), lines.append)
            res["log"] = lines
            return jsonify(res)
        except Exception as e:
            return jsonify({"ok": False, "error": str(e), "log": lines}), 500


def main(argv):
    if not argv or argv[0] in ("-h", "--help"):
        print(__doc__)
        return 0
    cmd = argv[0]
    if cmd == "account":
        p = Page()
        try:
            p.open("https://photos.google.com/", new=True)
            print("ACCOUNT " + account(p))
            p.b.call("browsingContext.close", {"context": p.ctx})
        finally:
            p.close()
        return 0
    if cmd == "make":
        album = argv[argv.index("--album") + 1]
        rest = [a for i, a in enumerate(argv[1:], 1) if a not in ("--album", "--share") and argv[i - 1] != "--album"]
        res = run(album, rest, "--share" in argv)
        print("ACCOUNT " + res["account"])
        print("ALBUM " + res["album_url"])
        if res["share_link"]:
            print("SHARE " + res["share_link"])
        return 0
    if cmd == "share":
        url = argv[argv.index("--album-url") + 1]
        p = Page()
        try:
            p.open(url, new=True)
            print("SHARE " + share_link(p))
        finally:
            p.close()
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except GErr as e:
        print("ERROR " + str(e))
        sys.exit(1)


def chat_gphotos_command(text):
    """Local chat command ($0, no model). None when the sentence is not about a Google Photos album.
    "share link of my Google Photos album "Title""                      -> the link of the existing album
    "make a Google Photos album "Title" from ~/folder" (or with files)  -> album + upload + link
    The link is only answered here, never sent to anyone."""
    if sys.platform != "darwin":
        return None
    t = (text or "").strip()
    low = t.lower()
    if "google photo" not in low or "album" not in low:
        return None
    m = re.search(r"[\"“”']([^\"“”']{2,120})[\"“”']", t)
    if not m:
        return "Which album? Put its title in quotes, e.g. make a Google Photos album \"Title\" from ~/Pictures/folder."
    title = m.group(1).strip()
    rest = t[m.end():]
    paths = re.findall(r"(~?/[^\s\"']+)", rest)
    files = []
    for pth in paths:
        pth = os.path.expanduser(pth)
        if os.path.isdir(pth):
            files += sorted(os.path.join(pth, f) for f in os.listdir(pth)
                            if f.lower().endswith((".jpg", ".jpeg", ".png", ".heic", ".webp")))
        elif os.path.isfile(pth):
            files.append(pth)
    wants_upload = re.search(r"\b(make|create|upload|add|new)\b", low) and files
    if not wants_upload and not re.search(r"\blink\b|\bshare\b", low):
        return None
    lines = []
    try:
        res = run(title, files if wants_upload else [], True, lines.append)
    except Exception as e:
        return f"Google Photos album \"{title}\": FAILED, {e}. Steps: " + "; ".join(lines[-6:])
    mb = sum(os.path.getsize(f) for f in files) / 1e6 if wants_upload else 0
    head = (f"Album \"{title}\" in Google Photos ({res['account']}): {len(files)} pictures uploaded ({mb:.1f} MB)."
            if wants_upload else f"Album \"{title}\" ({res['account']}).")
    return (head + f"\nAlbum: {res['album_url']}\nShare link: {res['share_link']}\n"
            "The link is not sent to anyone; Marko shares it himself.")
