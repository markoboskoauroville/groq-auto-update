"""Queen's hands in Gemini (free, Marko's Chrome, account marko.bosko@auroville.community), 12.11.2026.

Marko: "this photo is not good quality ... she needs to create a photo in Google Gemini for free ... The poster is vertical,
the photo is horizontal ... we are missing the parts of the photo. Let her take this inside Gemini and then make what is
missing to be extended." Then: "after generating the new, better image with AI, which fills the whole frame, she needs to
create English and Croatian posters, two versions."

The manifest's Gemini rules (MANTRA_MANIFEST modules/gemini-image-jobs.md) are kept:
  - only in Chrome, only signed in as marko.bosko@auroville.community: checked on the page before anything is sent;
  - the reference attached as a file (here through Chrome's own DevTools protocol: a file input filled with
    DOM.setFileInputFiles, then pasted into the prompt box, the way the manifest's §0 road does it);
  - the result taken as a SCREENSHOT of the image (Page.captureScreenshot, clipped to the picture, scaled to its real
    size), never through Gemini's download button;
  - one image at a time, one tab, the tab closed afterwards;
  - Marko, 12.11.2026: "When you exhaust one account from the Chrome browser, you just switch to another profile and then
    continue there." auroville.community first, then his other Google profiles (Local State), the band account last;
    a profile whose window is not open is opened (open -na "Google Chrome" --args --profile-directory=...).
Chrome must have remote debugging on (chrome://inspect/#remote-debugging; the port and path are in DevToolsActivePort).

    POST /api/gemini/image {prompt, image: path, out: path, account?}  -> {ok, out, width, height}
"""
import base64
import subprocess
import json
import os
import time
from pathlib import Path

from flask import jsonify, request

ACCOUNT = "marko.bosko@auroville.community"
PORT_FILE = Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / "DevToolsActivePort"


class GeminiError(Exception):
    pass


class Exhausted(GeminiError):
    """This account cannot make the image now (daily limit, or no image editing on it): try the next profile."""


LOCAL_STATE = Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / "Local State"
LIMIT_WORDS = r"limit|try again (later|tomorrow)|come back later|too many|quota|can't (edit|create|generate)|cannot (edit|create|generate)|not able to (edit|create)|unable to (edit|create)"


def profiles(first=ACCOUNT):
    """(email, profile directory) of every Chrome profile signed in to Google: `first`, then the rest, the band last."""
    try:
        cache = json.loads(LOCAL_STATE.read_text())["profile"]["info_cache"]
    except Exception:
        return [(first, None)]
    out = [(v["user_name"], k) for k, v in cache.items() if v.get("user_name")]
    # *Mantreshvar (mantreshvar.margii) fails to open its window ("Something went wrong when opening your profile",
    # 13.11.2026): it goes last, like the band account
    rank = lambda e: (0 if e[0] == first else 2 if ("santoshi" in e[0] or "mantreshvar" in e[0]) else 1, e[0])  # noqa: E731
    return sorted(out, key=rank)


class CDP:
    """Chrome's DevTools through the broker (cdp_broker.py, 127.0.0.1:9333): ONE permanent connection, so Chrome asks
    "Allow remote debugging?" once per Chrome session instead of once per picture, and Marko's pointer is not borrowed
    while he works (13.11.2026). The broker is started here when it is not running."""
    BROKER = "http://127.0.0.1:9333"

    def __init__(self):
        self.allow_log, self.after = [], 0
        if not PORT_FILE.exists():
            raise GeminiError("Chrome remote debugging is off: chrome://inspect/#remote-debugging")
        if not self._health():
            py = Path.home() / ".groq" / "venv" / "bin" / "python"
            subprocess.Popen([str(py), str(Path(__file__).with_name("cdp_broker.py"))],
                             stdout=open(Path.home() / ".groq" / "cdp_broker.log", "a"), stderr=subprocess.STDOUT,
                             start_new_session=True)
        end = time.time() + 630                 # Chrome's one question may wait for Marko up to 10 minutes
        while time.time() < end:
            h = self._health()
            if h and h.get("connected"):
                break
            time.sleep(1)
        else:
            raise GeminiError("cannot reach Chrome's DevTools: the broker got no connection (Allow not pressed?)")
        ev = self._get("/events?after=0").get("events", [])
        self.after = ev[-1]["n"] if ev else 0
        self.events = []

    def _get(self, path):
        import urllib.request  # noqa: PLC0415
        with urllib.request.urlopen(self.BROKER + path, timeout=10) as r:
            return json.load(r)

    def _health(self):
        try:
            return self._get("/health")
        except Exception:
            return None

    def send(self, method, params=None, session=None, timeout=60):
        import urllib.request  # noqa: PLC0415
        body = json.dumps({"method": method, "params": params or {}, "sessionId": session, "timeout": timeout}).encode()
        req = urllib.request.Request(self.BROKER + "/send", data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=timeout + 15) as r:
            m = json.load(r)
        if "error" in m:
            raise GeminiError(f"{method}: {m['error'].get('message')}")
        return m.get("result", {})

    def wait_event(self, method, timeout=10):
        end = time.time() + timeout
        while time.time() < end:
            for e in self._get(f"/events?after={self.after}").get("events", []):
                self.after = max(self.after, e["n"])
                if e.get("method") == method:
                    return e
            time.sleep(0.3)
        return None

    def js(self, session, expr, timeout=60):
        r = self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True},
                      session, timeout)
        if r.get("exceptionDetails"):
            raise GeminiError("page script: " + str(r["exceptionDetails"].get("exception", {}).get("description", ""))[:300])
        return r.get("result", {}).get("value")

    def close(self):
        pass                                     # the one connection is the broker's and stays open


def _context_of_account(cdp):
    """The browserContext (Chrome profile) whose pages are open; Gemini itself tells which account it is."""
    ts = cdp.send("Target.getTargets")["targetInfos"]
    return sorted({t.get("browserContextId") for t in ts if t["type"] == "page" and t.get("browserContextId")})


def make_image(prompt, image_path, out_path, account=ACCOUNT, wait=180, max_accounts=4):
    """Try the accounts in order; an exhausted one hands over to the next profile.
    image_path None = a new picture from the words alone (13.11.2026, the book's pencil sketches)."""
    if image_path:
        image_path = Path(image_path).expanduser()
        if not image_path.is_file():
            raise GeminiError(f"no image {image_path}")
    tried = []
    for email, pdir in profiles(account)[:max_accounts]:
        try:
            r = _make_with(prompt, image_path, out_path, email, pdir, wait)
            r["tried"] = tried + [email]
            return r
        except Exhausted as exc:
            tried.append(f"{email}: {str(exc)[:120]}")
            _account_tool("mark-exhausted", email)     # the in-tab switch (gemini-switch-account) learns it too
            continue
        except GeminiError as exc:
            # a Chrome box ("Something went wrong when opening your profile") stalls DevTools: Macro Recorder closes it,
            # checking after every press, before the next account is tried (13.11.2026)
            if "no answer in" in str(exc):
                subprocess.run(["python3", str(Path.home() / "Developer" / "MACRO_SKILLS" / "tools" / "chrome_profile_error_ok.py"),
                                "until"], capture_output=True, text=True, timeout=330)
            # Marko, 12.11.2026: "if images are not generating, if there is a timeout, or if they are not generating
            # after a few minutes, you need to go to the next profile." Only a closed DevTools port stops everything.
            if "remote debugging is off" in str(exc) or "cannot reach Chrome" in str(exc):
                raise
            tried.append(f"{email}: {str(exc)[:120]}")
            continue
    raise GeminiError("every account tried is exhausted: " + " | ".join(tried))


WHO_JS = ("(() => { const a=[...document.querySelectorAll('[aria-label]')].map(e=>e.getAttribute('aria-label'))"
          ".find(s=>/@/.test(s||'')); return a||''; })()")
PREVIEW_JS = ("(() => document.querySelectorAll('uploader-file-preview, file-preview, .file-preview-container, "
              "img[src^=\"blob:\"]').length)()")


def _default_ctx(cdp):
    return cdp.send("Target.getBrowserContexts").get("defaultBrowserContextId")


def _make_default(cdp, pdir, opened):
    """DevTools makes tabs only in Chrome's DEFAULT context, which follows the most recently opened profile window
    (tested 12.11.2026: createTarget with another profile's context id fails). So the wanted profile gets a window."""
    import subprocess  # noqa: PLC0415
    before = _default_ctx(cdp)
    # Chrome's own launcher hands the request to the running Chrome (no second instance, no stolen focus): 13.11.2026
    subprocess.run(["/Applications/Google Chrome.app/Contents/MacOS/Google Chrome", f"--profile-directory={pdir}",
                    "about:blank"], check=False, timeout=20,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(30):
        time.sleep(0.5)
        now = _default_ctx(cdp)
        if now and now != before:
            break
    # every tab that appeared in the profile just opened is Queen's to close afterwards: the blank one, and anything the
    # profile opens by itself at start (an extension's "Updated" page kept father.aya's window open on 12.11.2026)
    time.sleep(2)
    now = _default_ctx(cdp)
    for t in cdp.send("Target.getTargets")["targetInfos"]:
        if t["type"] == "page" and now and t.get("browserContextId") == now and now != before:
            opened.append(t["targetId"])


def _gemini_tab(cdp, account):
    t = cdp.send("Target.createTarget", {"url": "https://gemini.google.com/app", "background": True})
    tid = t["targetId"]
    sess = cdp.send("Target.attachToTarget", {"targetId": tid, "flatten": True})["sessionId"]
    for dom in ("Page.enable", "Runtime.enable", "DOM.enable"):
        cdp.send(dom, session=sess)
    # A background tab is not focused, and Gemini's upload menu then never opens (tested 12.11.2026). Focus emulation
    # makes the tab behave as focused without bringing it in front of Marko.
    cdp.send("Emulation.setFocusEmulationEnabled", {"enabled": True}, sess)
    who = ""
    for _ in range(40):
        time.sleep(0.5)
        who = cdp.js(sess, WHO_JS) or ""
        if who and cdp.js(sess, "!!document.querySelector('rich-textarea .ql-editor')"):
            break
    return tid, sess, who


def _trusted_click(cdp, sess, rect_js):
    """A real (trusted) click from DevTools at the element's centre: Gemini's upload menu ignores script clicks."""
    r = cdp.js(sess, rect_js)
    if not r:
        return None
    x, y = r["x"] + r["w"] / 2, r["y"] + r["h"] / 2
    for ty in ("mouseMoved", "mousePressed", "mouseReleased"):
        cdp.send("Input.dispatchMouseEvent", {"type": ty, "x": x, "y": y, "button": "left", "clickCount": 1}, sess)
    return r


def _attach(cdp, sess, image_path):
    """Gemini's own upload: '+' (Upload and tools) -> 'Upload files' -> Chrome's file chooser, answered by DevTools.
    A synthetic paste or drop is ignored by Gemini (both tested 12.11.2026)."""
    cdp.send("Page.setInterceptFileChooserDialog", {"enabled": True}, sess)
    cdp.events.clear()
    plus = _trusted_click(cdp, sess, "(() => { const b=[...document.querySelectorAll('button')].find(b=>/upload and tools|upload|attach/i"
                                     ".test(b.getAttribute('aria-label')||'')); if(!b) return null; const r=b.getBoundingClientRect();"
                                     " return {x:r.x,y:r.y,w:r.width,h:r.height}; })()")
    if not plus:
        raise GeminiError("no upload button on the Gemini page")
    item = None
    item_js = ("(() => { const e=[...document.querySelectorAll('[role=menuitem], button')].find(b=>{const t=(b.innerText||'')"
               ".trim(); return t.length<40 && /upload files?/i.test(t);}); if(!e) return null; const r=e.getBoundingClientRect();"
               " return r.width ? {x:r.x,y:r.y,w:r.width,h:r.height} : null; })()")
    for attempt in range(2):                 # the menu can take a moment, or the first click can land before the page is ready
        for _ in range(10):
            time.sleep(0.5)
            if cdp.js(sess, item_js):
                break
        item = _trusted_click(cdp, sess, item_js)
        if item:
            break
        _trusted_click(cdp, sess, "(() => { const b=[...document.querySelectorAll('button')].find(b=>/upload and tools|upload|attach/i"
                                  ".test(b.getAttribute('aria-label')||'')); if(!b) return null; const r=b.getBoundingClientRect();"
                                  " return {x:r.x,y:r.y,w:r.width,h:r.height}; })()")
    if not item:
        raise GeminiError("no 'Upload files' item in Gemini's menu")
    ev = cdp.wait_event("Page.fileChooserOpened", 10)
    if not ev:
        raise GeminiError("Gemini's file chooser did not open")
    cdp.send("DOM.setFileInputFiles", {"files": [str(image_path)], "backendNodeId": ev["params"]["backendNodeId"]}, sess)
    for _ in range(40):
        time.sleep(0.5)
        if cdp.js(sess, PREVIEW_JS):
            return True
    raise GeminiError("the photo did not attach in Gemini")


def _make_with(prompt, image_path, out_path, account, pdir, wait=180):
    cdp = CDP()
    tid, opened = None, []
    try:
        tid, sess, who = _gemini_tab(cdp, account)
        if account.lower() not in who.lower():
            cdp.send("Target.closeTarget", {"targetId": tid})
            tid = None
            if not pdir:
                raise Exhausted(f"Gemini is signed in as {who!r}, not {account}")
            _make_default(cdp, pdir, opened)
            tid, sess, who = _gemini_tab(cdp, account)
            if account.lower() not in who.lower():
                raise Exhausted(f"could not reach Gemini as {account} (got {who!r})")

        # 1. the reference, through Gemini's own upload (none for a picture made from words alone)
        if image_path:
            _attach(cdp, sess, image_path)

        # 2. the prompt, typed, then sent
        cdp.js(sess, "document.querySelector('rich-textarea .ql-editor').focus()")
        cdp.send("Input.insertText", {"text": prompt}, sess)
        time.sleep(0.8)
        sent = _trusted_click(cdp, sess, "(() => { const b=document.querySelector('button.send-button, button[aria-label*=\"Send\"]');"
                                         " if(!b || b.disabled) return null; const r=b.getBoundingClientRect();"
                                         " return {x:r.x,y:r.y,w:r.width,h:r.height}; })()")
        if not sent:
            raise GeminiError("the Send button was not ready")

        # 3. wait for the generated picture in the answer
        found = None
        end = time.time() + wait
        while time.time() < end:
            time.sleep(2)
            found = cdp.js(sess, "(() => { const im=[...document.querySelectorAll('model-response img, generated-image img, single-image img')]"
                                 ".filter(i=>i.naturalWidth>400 && i.complete); if(!im.length) return null; const i=im[im.length-1];"
                                 "i.scrollIntoView({block:'center'}); const r=i.getBoundingClientRect();"
                                 "return {x:r.x,y:r.y,w:r.width,h:r.height,nw:i.naturalWidth,nh:i.naturalHeight}; })()")
            if found:
                time.sleep(1.5)
                found = cdp.js(sess, "(() => { const im=[...document.querySelectorAll('model-response img, generated-image img, single-image img')]"
                                     ".filter(i=>i.naturalWidth>400 && i.complete); const i=im[im.length-1]; const r=i.getBoundingClientRect();"
                                     "return {x:r.x,y:r.y,w:r.width,h:r.height,nw:i.naturalWidth,nh:i.naturalHeight}; })()")
                break
            said = cdp.js(sess, "(() => { const m=[...document.querySelectorAll('model-response')]; if(!m.length) return '';"
                                " const last=m[m.length-1]; const done=!last.querySelector('.loading, [aria-busy=true]');"
                                " return done ? (last.innerText||'') : ''; })()") or ""
            import re  # noqa: PLC0415
            if said and re.search(LIMIT_WORDS, said, re.I) and len(said) < 1200:
                raise Exhausted("Gemini: " + said[:200])
        if not found:
            raise Exhausted(f"no image from Gemini in {wait}s")

        # 4a. the picture's own bytes from Chrome's memory (no overlays, full size): Page.getResourceContent of its URL
        out = Path(out_path).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        try:
            src = cdp.js(sess, "(() => { const im=[...document.querySelectorAll('model-response img, generated-image img, single-image img')]"
                               ".filter(i=>i.naturalWidth>400); return im[im.length-1].currentSrc; })()")
            frame = cdp.send("Page.getFrameTree", {}, sess)["frameTree"]["frame"]["id"]
            res = cdp.send("Page.getResourceContent", {"frameId": frame, "url": src}, sess, timeout=60)
            data = base64.b64decode(res["content"]) if res.get("base64Encoded") else res["content"].encode("latin-1")
            if len(data) > 20000:
                out.write_bytes(data)
                return {"out": str(out), "width": found["nw"], "height": found["nh"], "natural": [found["nw"], found["nh"]],
                        "account": account, "profile": pdir, "how": "resource"}
        except Exception as exc:
            print(f"[gemini] resource copy failed, screenshot instead: {exc}", flush=True)
        # Gemini's buttons and its input bar lie over the picture: hidden for the screenshot
        cdp.js(sess, "(() => { const st=document.createElement('style'); st.textContent='input-container, .input-area-container,"
                     " fieldset, .bottom-container, .generated-image-controls, .image-actions, button{visibility:hidden !important}';"
                     " document.head.appendChild(st); })()")
        # 4b. the screenshot of the picture, at its real size
        # 13.11.2026: captureBeyondViewport re-laid Gemini's page and the clip caught the dark page beside the picture.
        # Now: the picture centred in view, measured again right before the shot, captured from the visible viewport.
        cdp.js(sess, "(() => { const im=[...document.querySelectorAll('model-response img, generated-image img, single-image img')]"
                     ".filter(i=>i.naturalWidth>400); im[im.length-1].scrollIntoView({block:'center', inline:'center'}); })()")
        time.sleep(1.2)
        found.update(cdp.js(sess, "(() => { const im=[...document.querySelectorAll('model-response img, generated-image img, single-image img')]"
                                  ".filter(i=>i.naturalWidth>400); const r=im[im.length-1].getBoundingClientRect();"
                                  " return {x:r.x,y:r.y,w:r.width,h:r.height}; })()"))
        scale = max(1.0, found["nw"] / max(1, found["w"]))
        # the clip's own "scale" moved the frame off the picture (13.11.2026, seen in a full-view capture); instead the page
        # is rendered sharper (deviceScaleFactor, same CSS layout, same size) and the clip is taken at scale 1
        vw = cdp.js(sess, "[innerWidth, innerHeight]")
        cdp.send("Emulation.setDeviceMetricsOverride", {"width": vw[0], "height": vw[1], "deviceScaleFactor": scale,
                                                        "mobile": False}, sess)
        time.sleep(0.8)
        try:   # Gemini's page ignores the clip's position (it always came from 0,0): the whole view, cut out below
            shot = cdp.send("Page.captureScreenshot", {"format": "png", "captureBeyondViewport": False}, sess, timeout=90)
        finally:
            cdp.send("Emulation.clearDeviceMetricsOverride", {}, sess)
        out = Path(out_path).expanduser()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_bytes(base64.b64decode(shot["data"]))
        # the picture, cut out of the view on the Mac (sips): its CSS box times the render scale, 2 px inside the edge
        x, y = round((found["x"] + 2) * scale), round((found["y"] + 2) * scale)
        w, h = round((found["w"] - 4) * scale), round((found["h"] - 4) * scale)
        subprocess.run(["sips", "-c", str(h), str(w), "--cropOffset", str(y), str(x), str(out), "--out", str(out)],
                       capture_output=True, check=False)
        return {"out": str(out), "width": round(found["w"] * scale), "height": round(found["h"] * scale),
                "natural": [found["nw"], found["nh"]], "account": account, "profile": pdir}
    finally:
        for t in ([tid] if tid else []) + opened:          # close what was opened: the Gemini tab and any profile window
            try:
                cdp.send("Target.closeTarget", {"targetId": t})
            except Exception:
                pass
        cdp.close()


ACCOUNT_TOOL = Path.home() / "Developer" / "MACRO_SKILLS" / "tools" / "gemini_account.py"


def _account_tool(*args, timeout=90):
    """MACRO_SKILLS gemini_account.py (status / next / mark-exhausted / switch): returns (ok, output). Never raises."""
    try:
        r = subprocess.run(["python3", str(ACCOUNT_TOOL), *args], capture_output=True, text=True, timeout=timeout)
        return r.returncode == 0, (r.stdout + r.stderr).strip()
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


def register(app):
    @app.post("/api/gemini/account")
    def gemini_account():
        """{"do": "status" | "next" | "switch" | "mark-exhausted", "tab"?, "to"?, "email"?} - Gemini's Google account in Chrome."""
        d = request.get_json(silent=True) or {}
        act = d.get("do", "status")
        if act not in ("status", "next", "switch", "mark-exhausted"):
            return jsonify(ok=False, error="do = status | next | switch | mark-exhausted"), 400
        args = [act]
        for flag in ("tab", "to"):
            if d.get(flag):
                args += [f"--{flag}", str(d[flag])]
        if act == "mark-exhausted" and d.get("email"):
            args.append(str(d["email"]))
        ok, out = _account_tool(*args)
        return jsonify(ok=ok, output=out), (200 if ok else 409)

    @app.post("/api/gemini/image")
    def gemini_image():
        d = request.get_json(silent=True) or {}
        try:
            return jsonify(ok=True, **make_image(d.get("prompt", ""), d.get("image", ""), d.get("out", ""),
                                                 d.get("account") or ACCOUNT, int(d.get("wait") or 180)))
        except GeminiError as exc:
            return jsonify(ok=False, error=str(exc)), 400
        except Exception as exc:
            return jsonify(ok=False, error=f"{type(exc).__name__}: {exc}"), 500
    return app


if __name__ == "__main__":       # a manual test: python3 gemini_skill.py <image> <out> "<prompt>"
    import sys
    print(json.dumps(make_image(sys.argv[3], sys.argv[1], sys.argv[2]), indent=1))
    os._exit(0)
