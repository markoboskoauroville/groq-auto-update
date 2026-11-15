"""Seven operating hands (15.11.2026, training mode): local chat commands, no model, $0.
VPN (Mantra) / pre-show + stream on chromium-vm / Talk Mode / Voice to Text engines / testclean / G815 lights /
Meditation Room (Mac). Nothing here changes an app: each command calls the app's own CLI, URL or local API."""
import json, os, re, shutil, subprocess, sys, time
import urllib.request

ENV = dict(os.environ)
ENV["PATH"] = os.path.expanduser("~/.local/bin") + ":/usr/local/bin:" + ENV.get("PATH", "")
TS = "/Applications/Tailscale.app/Contents/MacOS/Tailscale"


def _sh(args, timeout=30, env=None):
    r = subprocess.run(args, capture_output=True, text=True, timeout=timeout, env=env or ENV, stdin=subprocess.DEVNULL)
    return (r.stdout + r.stderr).strip(), r.returncode


def _http(method, url, body=None, timeout=8):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode() or "{}")


def _norm(text):
    return re.sub(r"\s+", " ", (text or "").strip().lower().strip(" .!?,"))


# ---------------------------------------------------------------- 1. VPN (Mantra)
def _ts(*a):
    env = dict(ENV); env["TAILSCALE_BE_CLI"] = "1"
    return _sh([TS, *a], 30, env)


def _vpn_state():
    out, _ = _ts("status", "--json")
    d = json.loads(out)
    exit_id = (d.get("ExitNodeStatus") or {}).get("ID")
    node = None
    for p in (d.get("Peer") or {}).values():
        if p.get("ExitNodeOption") and "chromium-vm" in (p.get("HostName") or ""):
            node = p
    return d.get("BackendState"), exit_id, node


def _public_ip():
    try:
        with urllib.request.urlopen("https://ipinfo.io/json", timeout=8) as r:
            d = json.loads(r.read().decode())
        return f"{d.get('ip')} ({d.get('city')}, {d.get('country')}, {d.get('org')})"
    except Exception:
        return "public address not readable"


def vpn_status():
    st, exit_id, node = _vpn_state()
    if st != "Running":
        return f"Tailscale is {st or 'not running'}; the VPN cannot work until it is signed in and running."
    mode = "FRANKFURT (through chromium-vm)" if exit_id else "DIRECT"
    return f"VPN is {mode}. Public address {_public_ip()}."


def vpn_set(which):
    st, exit_id, node = _vpn_state()
    if st != "Running":
        return f"Tailscale is {st or 'not running'}, I did not switch."
    if which == "frankfurt":
        if not node:
            return "No exit node chromium-vm is offered in the tailnet, I did not switch."
        out, rc = _ts("set", f"--exit-node={node['TailscaleIPs'][0]}", "--exit-node-allow-lan-access=true")
    else:
        out, rc = _ts("set", "--exit-node=")
    if rc:
        return f"Tailscale refused: {out[-200:]}"
    time.sleep(3)
    return f"Done, read back: {vpn_status()}"


def chat_vpn(low):
    m = re.match(r"^(mantra )?vpn( status| state)?$|^which vpn$|^is the vpn on$|^vpn (frankfurt|direct)$|^(use|switch to) vpn (frankfurt|direct)$", low)
    if not m:
        return None
    w = re.search(r"(frankfurt|direct)", low)
    if w:
        return vpn_set(w.group(1))
    return vpn_status()


# ---------------------------------------------------------------- 2. pre-show / stream on the VM
def _mr(*a, timeout=60):
    return _sh(["ssh", "-o", "ConnectTimeout=8", "chromium-vm", "mrlinux", *a], timeout)


def _viewers():
    try:
        d = _http("GET", "http://100.102.86.30:8996/api/snapshot", timeout=6)
    except Exception as e:
        return f"The Streaming Dashboard on the VM does not answer ({type(e).__name__})."
    site = d.get("site") or {}
    paths = {p["name"]: p for p in ((d.get("relay") or {}).get("paths") or [])}
    sa = paths.get("santoshi") or {}
    readers = len(sa.get("readers") or [])
    live = "LIVE" if site.get("live") else "not live"
    return (f"The site is {live}; the relay path santoshi has {readers} reader(s) right now"
            f"{' (the site does not report its own viewer count)' if site.get('viewers') is None else ''}.")


def _hhmm(s):
    m = re.search(r"\b([01]?\d|2[0-3])[:.]([0-5]\d)\b", s)
    return f"{int(m.group(1)):02d}:{m.group(2)}" if m else None


def chat_stream(low):
    if re.match(r"^(stream viewers|viewers|how many viewers|who is watching|stream viewers now)$", low):
        return _viewers()
    if re.match(r"^(pre-?show( status)?|stream status|meditation room (stream|linux) status)$", low):
        out, rc = _mr("status")
        return "Meditation Room (Linux) on chromium-vm:\n" + out
    m = re.match(r"^(start|begin) (the )?pre-?show( stream)?( until| till| to)?\s*(.*)$", low)
    if m:
        t = _hhmm(m.group(5))
        if not t:
            return "Until when? Say 'start pre-show until 18:30' (Zagreb time)."
        out, rc = _mr("start", "--preshow-until", t)
        return f"{out}\nThe countdown runs to {t}, private test relay only, nothing public. Say 'stop pre-show' to end it."
    if re.match(r"^(stop|end|cancel) (the )?pre-?show( stream)?$|^stop (the )?(meditation room )?(stream|test stream)$", low):
        out, rc = _mr("stop")
        return out + " (test stream and private relay stopped; live, if it ran, was stopped first)"
    if re.match(r"^(go live|start (the )?live( stream)?)( \d+)?$", low):
        out, rc = _mr("checks")
        return (f"Go live check: {out}. Going live is public. Say 'yes go live' (5 minutes) or 'yes go live 15' "
                f"to go on. I only run the same mrlinux go-live, which refuses the noon window and a live site.")
    m = re.match(r"^yes,? go live( (\d+))?$", low)
    if m:
        mins = m.group(2) or "5"
        out, rc = _mr("go-live", mins, timeout=90)
        return out + ("" if rc == 0 else f"\n(mrlinux refused, exit {rc}; nothing went live)")
    if re.match(r"^stop live$|^stop (the )?live stream$", low):
        out, rc = _mr("stop-live")
        return out
    return None


# ---------------------------------------------------------------- 3. Talk Mode
TM_STATE = os.path.expanduser("~/Library/Application Support/Talk Mode (Mantra)/state.json")


def _tm():
    try:
        return json.load(open(TM_STATE))
    except Exception:
        return {}


def _tm_running():
    return subprocess.run(["pgrep", "-f", "Talk Mode \\(Mantra\\).app/Contents/MacOS/TalkMode"], capture_output=True).returncode == 0


def _tm_summary():
    s = _tm()
    if s.get("plain"):      # v12: Talk Mode's own plain sentence from Marko's side
        return (f"{s['plain']} (Talk Mode {'on' if s.get('on') else 'off'}, sends {s.get('mode', '?')}, talking to {s.get('target', '?')}"
                f" on {s.get('target_device', '?')}; Space Mode {'ON' if s.get('space_mode') else 'off'}.)")
    return (f"Talk Mode is {'ON' if s.get('on') else 'OFF (typing mode)'}, sends {s.get('mode', '?')}, "
            f"state {s.get('state', '?')}, talking to {s.get('target', '?')} ({s.get('target_device', '?')}); "
            f"Space Mode {'ON' if s.get('space_mode') else 'off'}.")


def _tm_press(label):
    out, rc = _sh(["macro", "ax-press", "Talk Mode (Mantra)", label], 40)
    time.sleep(1.5)
    return out


def chat_talkmode(low):
    if not re.search(r"talk mode|space mode|auto mode|manual mode|^(auto|manual)$", low):
        return None
    if not _tm_running():
        return "Talk Mode (Mantra) is not running. Say 'open Talk Mode' first; I do not start it by myself."
    if re.match(r"^(talk mode( status)?|talk mode state)$", low):
        return _tm_summary()
    if re.match(r"^(talk mode on|turn (on )?talk mode( on)?|talk mode start)$", low):
        _sh(["open", "-g", "talkmode://on"]); time.sleep(1.5)
        return "Asked Talk Mode to listen. " + _tm_summary()
    if re.match(r"^(talk mode off|turn talk mode off|typing mode)$", low):
        _sh(["open", "-g", "talkmode://off"]); time.sleep(1.5)
        return "Asked Talk Mode to stop listening (typing mode). " + _tm_summary()
    m = re.match(r"^(talk mode )?(auto|manual)( mode)?( on)?$|^(set |switch to )talk mode (auto|manual)$", low)
    if m:
        want = (m.group(2) or m.group(6)).upper()
        cur = _tm().get("mode")
        if cur == want:
            return f"Talk Mode already sends {want}. " + _tm_summary()
        out = _tm_press(cur or ("AUTO" if want == "MANUAL" else "MANUAL"))   # the checkbox's label is its CURRENT state
        for _ in range(8):
            if _tm().get("mode") == want:
                break
            time.sleep(0.7)
        if _tm().get("mode") != want:
            return f"I pressed the switch but Talk Mode still sends {_tm().get('mode')} ({out[:120]}). Not done."
        return f"Switched, read back: " + _tm_summary()
    if re.match(r"^(space mode test|test space mode)$", low):
        if not _tm().get("space_mode") is False:
            return "Space Mode is already on; say 'space mode off'."
        _sh(["open", "-g", "talkmode://space-test"]); time.sleep(2)
        on = _tm().get("space_mode")
        return ("Space Mode test started: keyboard and mouse are off for 10 seconds, then it ends by itself. "
                if on else "The test did not start (Space Mode needs Accessibility for Talk Mode; check PERMISSIONS in its window). ") + _tm_summary()
    if re.match(r"^(space mode off|exit space mode|stop space mode)$", low):
        _sh(["open", "-g", "talkmode://space-off"]); time.sleep(1.5)
        return "Asked Space Mode to end. " + _tm_summary()
    if re.match(r"^space mode on$", low):
        return ("I do not turn Space Mode on: it switches off your keyboard and mouse. Say 'space mode test' for the "
                "10 second test, or tell me plainly 'yes, space mode on, I know' ... then use the Talk Mode switch.")
    return None


# ---------------------------------------------------------------- 4. Voice to Text engines
VTT = "http://127.0.0.1:8865"


def _engines():
    return _http("GET", VTT + "/engines")["engines"]


def _vtt_up():
    try:
        _http("GET", VTT + "/status", timeout=3); return True
    except Exception:
        return False


def chat_engine(low):
    if not re.search(r"engine", low):
        return None
    if not _vtt_up():
        return "Voice to Text (Mantra) is not running (nothing on :8865). Say 'open Voice to Text'."
    lang = "hr" if re.search(r"\b(hr|croatian)\b", low) else "en"
    if re.match(r"^(which|what) engine( (is )?(on|in use|am i using|do i use|are we using))?( for (en|hr|english|croatian))?$|^engine( status)?$|^which engine is (on|selected)$", low):
        es = _engines()
        cur = [e for e in es if e.get("selected_" + lang)]
        c = cur[0]["label"] if cur else "none selected"
        other = "hr" if lang == "en" else "en"
        o = [e["label"] for e in es if e.get("selected_" + other)]
        return f"Voice to Text engine for {lang.upper()}: {c}. For {other.upper()}: {o[0] if o else 'none'}."
    if re.match(r"^(engine ranking|rank (the )?engines|engines ranking|best engines?|which engine is best)( for (en|hr|english|croatian))?$", low):
        es = [e for e in _engines() if e.get("available")]
        key = "stats_" + lang
        rated = [e for e in es if (e.get(key) or {}).get("quality_pct") is not None]
        rated.sort(key=lambda e: (-e[key]["quality_pct"], e[key].get("median_secs") or 99))
        unrated = [e for e in es if e not in rated]
        lines = [f"{i+1}. {e['label' if lang == 'en' else 'label_hr']} ({e[key]['quality_pct']}%)" for i, e in enumerate(rated)]
        lines += [f"-  {e['label']}" for e in unrated]
        return f"Engines for {lang.upper()}, best quality first, then speed:\n" + "\n".join(lines)
    m = re.match(r"^(use|select|switch to|change to|set) (the )?engine\s+(.+?)( for (en|hr|english|croatian))?$|^use (.+?) (engine|for (en|hr))$", low)
    if m:
        name = (m.group(3) or m.group(6) or "").strip()
        if m.group(5):
            lang = "hr" if m.group(5) in ("hr", "croatian") else "en"
        es = _engines()
        hits = [e for e in es if name == e["id"] or name == e["label"].split("·")[0].strip().lower()]
        if not hits:
            hits = [e for e in es if name in e["id"] or name in e["label"].lower()]
        if len(hits) != 1:
            top = ", ".join(e["id"] for e in (hits or es)[:5])
            return f"I do not find one engine called '{name}'. Closest: {top}."
        e = hits[0]
        if not e.get("available"):
            return f"{e['id']} is not available (no key or not installed)."
        _http("POST", VTT + "/engines/select", {"id": e["id"], "lang": lang})
        now = [x for x in _engines() if x.get("selected_" + lang)]
        return f"Voice to Text engine for {lang.upper()} is now {now[0]['label'] if now else '?'} (read back)."
    return None


# ---------------------------------------------------------------- 5. clean-up
def chat_cleanup(low):
    if re.match(r"^(clean ?up( the)? tests?|test ?clean|what did the tests leave( behind)?|anything left (over )?from tests)$", low):
        out, rc = _sh(["testclean"], 120)
        return "testclean (list only, nothing stopped):\n" + out[-2500:] + "\nSay 'yes, clean up tests --kill' to stop headless browsers and phone overlays."
    if re.match(r"^yes,? clean ?up tests?( --kill)?$|^yes,? kill the test leftovers$", low):
        out, rc = _sh(["testclean", "--kill"], 180)
        return "testclean --kill:\n" + out[-2500:] + "\n(Recorders, emulators, repos and VM items I leave: check whose they are.)"
    return None


# ---------------------------------------------------------------- 6. G815 lights
G = "http://127.0.0.1:8877"


def chat_lights(low):
    if not re.search(r"light ?show|keyboard lights|g815", low):
        return None
    try:
        if re.match(r"^(light show now|start (the )?light show|start light show now)$", low):
            _http("POST", G + "/idle/start", {})
            return "The light show runs on the G815 now (any key stops it; it resumes after 5 minutes of no typing if idle is on)."
        if re.match(r"^(stop (the )?light show|light show off|stop lights)$", low):
            _http("POST", G + "/stop", {})
            return "Light show stopped, the keyboard shows Marko's own profile again."
        m = re.match(r"^idle light show (on|off)$|^(turn )?(on|off) (the )?idle light show$", low)
        if m:
            on = (m.group(1) or m.group(3)) == "on"
            _http("POST", G + "/idle", {"on": on, "minutes": 5, "show": "all"})
            s = _http("GET", G + "/idle")
            return f"Idle light show is {'ON (starts after 5 minutes without a key)' if s.get('on') else 'OFF'} (read back)."
        if re.match(r"^(light show status|g815 status|idle light show( status)?|keyboard lights status)$", low):
            s = _http("GET", G + "/status")
            i = s.get("idle_show") or {}
            return (f"G815 Lights v{s.get('version')}: show {'running' if s.get('active') else 'not running'}, "
                    f"idle light show {'ON' if i.get('on') else 'OFF'} after {i.get('minutes')} min.")
    except Exception as e:
        return f"G815 Lights does not answer on :8877 ({type(e).__name__}). It is a login agent: community.auroville.g815lights."
    return None


# ---------------------------------------------------------------- 7. Meditation Room (Mac)
MR = "http://127.0.0.1:8965"


def chat_meditation(low, orig=None):
    if not re.search(r"meditation room|pre-?show text", low):
        return None
    m = re.match(r"^(meditation room )?pre-?show text (.+)$", low)
    words = None
    if m:
        om = re.search(r"pre-?show text\s+(.+)$", orig or "", re.I)
        words = (om.group(1).strip() if om else m.group(2))
    try:
        _http("GET", MR + "/health", timeout=3)
    except Exception:
        if re.match(r"^(open|start|quit|close) meditation room", low):
            return None   # the app-open command is someone else's
        return "Meditation Room (Mantra) is not running (nothing on :8965). Say 'open Meditation Room' first."
    if words:
        _http("POST", MR + "/api/text", {"text": words})
        return f"Showing the words over the picture: {words}"
    mm = re.match(r"^meditation room ndi (on|off)$|^(turn )?ndi (on|off) (in |for )?meditation room$", low)
    if mm:
        on = (mm.group(1) or mm.group(3)) == "on"
        r = _http("POST", MR + "/api/ndi", {"on": on})
        s = _http("GET", MR + "/api/state")
        return f"Meditation Room NDI {'on' if on else 'off'} (read back: {'on' if s.get('ndi') else 'off'})."
    if re.match(r"^meditation room( status| state)?$", low):
        s = _http("GET", MR + "/api/state")
        return (f"Meditation Room: {'playing' if s.get('playing') else 'not playing'}, output {s.get('output')}, gain {s.get('gain_db')} dB, "
                f"NDI {'on' if s.get('ndi') else 'off'}, lights {'on' if (s.get('lights') or {}).get('on') else 'off'}, pre-show {'on' if s.get('preshow') else 'off'}.")
    return None


def chat_ops_command(text):
    t = (text or "").strip()
    if not t or len(t) > 160:
        return None
    low = _norm(t)
    for fn in (chat_vpn, chat_stream, chat_talkmode, chat_engine, chat_cleanup, chat_lights, chat_meditation):
        try:
            a = fn(low, t) if fn is chat_meditation else fn(low)
        except Exception as e:
            return f"The {fn.__name__[5:]} hand failed: {type(e).__name__}: {e}"
        if a:
            return a
    return None
