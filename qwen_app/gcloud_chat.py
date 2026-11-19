"""Google Cloud provider of the CAPI tab (v24, 18.11.2026).

Marko: "One more radio button and a complete setup to get API enabled ... utilize these [Google Cloud free] credits" and
"a file picker for my chat box so I can send you images and files."  Pays from the GCP free credit ($254 on 18.11.2026,
expires about 9.12.2026), project antigravity-cloud-offload.

 * Gemini: Gemini API v1beta with the AIza... key read AT RUNTIME from ~/Downloads/API/CGP_free_credits_Google API.txt
   (a second AQ.... key in the same file is the failover). Keys are never printed, logged or stored anywhere else.
 * Claude on Vertex AI: publishers/anthropic/models/<id>:rawPredict, Anthropic Messages body with
   anthropic_version vertex-2023-10-16, OAuth bearer from Application Default Credentials (API keys are refused there:
   401 "API keys are not supported"). No ADC or 403/404 (access pending) -> the plain line
   "Claude on Google Cloud is not ready yet: <reason>".
 * Attachments: images (inline_data / image block), PDF (inline_data / document block), text and code inlined as text.
   20 MB per file.
"""
from __future__ import annotations

import base64
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path

KEY_FILE = Path.home() / "Downloads" / "API" / "CGP_free_credits_Google API.txt"
PROJECT = "antigravity-cloud-offload"
GEMINI = "https://generativelanguage.googleapis.com/v1beta"
LEDGER = Path.home() / ".cache" / "gcloud-ledger.jsonl"
START_FILE = Path.home() / ".groq" / "capi_gcloud_balance.json"
# THE ONE CONFIG VALUE for the free credit (update here, or write the same keys to START_FILE): the Billing -> Credits page
# read "GCP Free Credit $225.31 remaining (75%), expiring in 14 days" on 18.11.2026 about 16:10 (+0100; the brief said 16:30 but the Mac clock read 16:14 when applied); expiry 2.12.2026.
CREDIT = {"start_usd": 225.31, "at": 1795014607.0, "expires": "2026-12-02", "read": "18.11.2026 about 16:10"}
VERTEX_ENABLED = False                 # v25: Google Cloud is Gemini only (Claude there is a paid Marketplace product); code kept dormant
MAX_FILE = 20 * 1024 * 1024
VERTEX_MODELS = ["claude-opus-4-5@20251101", "claude-sonnet-4-5@20250929", "claude-haiku-4-5@20251001"]
def _load_retired():
    try:
        p = Path(__file__).parent / "retired_models.json"
        if p.is_file():
            with open(p, "r", encoding="utf-8") as f:
                return set(json.load(f))
    except Exception:
        pass
    return set()

RETIRED = {"gemini-2.5-pro"} | _load_retired()
FALLBACK_GEMINI = ["gemini-3.8-flash", "gemini-3.7-flash", "gemini-3.5-flash", "gemini-2.5-flash", "gemini-3.1-pro-preview"]
# USD per million tokens (input, output): list-price estimates, the credit counter is an estimate
RATES = [("opus", (5.0, 25.0)), ("sonnet", (3.0, 15.0)), ("haiku", (1.0, 5.0)),
         ("pro", (1.25, 10.0)), ("lite", (0.10, 0.40)), ("flash", (0.30, 2.50))]
TEXT_EXT = {".txt", ".md", ".py", ".js", ".ts", ".json", ".csv", ".html", ".css", ".swift", ".kt", ".java", ".c", ".h",
            ".cpp", ".sh", ".yml", ".yaml", ".xml", ".toml", ".ini", ".log", ".sql", ".rb", ".go", ".rs", ".tsx", ".jsx"}


class NotReady(Exception):
    pass


def is_vertex(model):
    return bool(model) and model.startswith("claude-")


def _keys():
    try:
        t = KEY_FILE.read_text(errors="ignore")
    except Exception:
        return []
    a = re.findall(r"AIza[0-9A-Za-z_-]{30,}", t)
    b = re.findall(r"\bAQ\.[0-9A-Za-z_.-]{20,}", t)
    return a + b


def has_key():
    return bool(_keys())


def _scrub(s, keys=None):
    s = str(s)
    for k in keys or _keys():
        s = s.replace(k, "***")
    return re.sub(r"(AIza|AQ\.)[0-9A-Za-z_.-]{8,}", "***", s)


def _rate(model):
    m = (model or "").lower()
    for k, r in RATES:
        if k in m:
            return r
    return (0.30, 2.50)


def _cost(model, tin, tout):
    r = _rate(model)
    return round((tin * r[0] + tout * r[1]) / 1e6, 6)


# ------------------------------------------------------------------ credit
def config():
    c = dict(CREDIT)
    try:
        c.update({k: v for k, v in json.loads(START_FILE.read_text()).items() if k in c})
    except Exception:
        pass
    return c


def expiry_text():
    y, m, d = config()["expires"].split("-")
    return f"{int(d)}.{int(m)}.{y}"


def spent():
    t0 = float(config().get("at") or 0)
    s = 0.0
    try:
        for line in open(LEDGER):
            try:
                r = json.loads(line)
                if r.get("at", 0) >= t0:
                    s += float(r.get("cost") or 0)
            except Exception:
                pass
    except Exception:
        pass
    return s


def left():
    return round(max(0.0, float(config()["start_usd"]) - spent()), 4)


def set_balance(usd):
    START_FILE.parent.mkdir(parents=True, exist_ok=True)
    START_FILE.write_text(json.dumps({"start_usd": float(usd), "at": time.time(), "expires": config()["expires"]}))


def ledger(cost, prompt, model):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(LEDGER, "a") as f:
        f.write(json.dumps({"at": time.time(), "ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "cost": cost, "model": model,
                            "prompt": prompt[:70]}) + "\n")


# ------------------------------------------------------------------ models
def _vkey(name):
    n = re.findall(r"\d+(?:\.\d+)?", name)
    return float(n[0]) if n else 0.0


def gemini_models():
    """Live from /models: gemini text models (generateContent), not image / tts / audio / robotics / computer-use."""
    keys = _keys()
    bad = ("image", "tts", "transcribe", "robotics", "computer-use", "omni", "nano", "customtools", "embedding", "live", "audio")
    for k in keys[:1]:
        try:
            req = urllib.request.Request(GEMINI + "/models?pageSize=200", headers={"x-goog-api-key": k})
            with urllib.request.urlopen(req, timeout=20) as x:
                j = json.loads(x.read().decode())
            out = []
            for m in j.get("models", []):
                n = m.get("name", "").replace("models/", "")
                if (n.startswith("gemini") and "generateContent" in m.get("supportedGenerationMethods", [])
                        and not any(b in n for b in bad) and "latest" not in n):
                    out.append(n)
            if out:
                filtered = [m for m in out if m not in RETIRED]
                return sorted(set(filtered), key=lambda n: (-_vkey(n), "lite" in n, "pro" in n, n))
        except Exception:
            pass
    return [m for m in FALLBACK_GEMINI if m not in RETIRED]


def default_gemini(models):
    flash = [m for m in models if "flash" in m and "lite" not in m and "preview" not in m]
    return (flash or models or FALLBACK_GEMINI)[0]


def models_info():
    g = gemini_models()
    return {"gemini": g, "claude": VERTEX_MODELS if VERTEX_ENABLED else [], "default": default_gemini(g), "has_key": has_key()}


# ------------------------------------------------------------------ attachments
def prepare_files(files):
    """[{name, mime, b64}] -> ([{kind,name,mime,b64|text}], error line or ''). One short plain line on any problem."""
    out = []
    for f in files or []:
        name = str(f.get("name") or "file")[:120]
        try:
            raw = base64.b64decode(f.get("b64") or "", validate=False)
        except Exception:
            return [], f"{name}: the file could not be read."
        if len(raw) > MAX_FILE:
            return [], f"{name} is {len(raw) / 1048576:.1f} MB: the limit is 20 MB per file."
        mime = (f.get("mime") or "").lower()
        ext = Path(name).suffix.lower()
        if mime.startswith("image/"):
            out.append({"kind": "image", "name": name, "mime": mime, "b64": base64.b64encode(raw).decode()})
        elif mime == "application/pdf" or ext == ".pdf":
            out.append({"kind": "pdf", "name": name, "mime": "application/pdf", "b64": base64.b64encode(raw).decode()})
        elif mime.startswith("text/") or ext in TEXT_EXT or mime in ("application/json", "application/xml"):
            out.append({"kind": "text", "name": name, "text": raw.decode("utf-8", "replace")})
        else:
            try:
                out.append({"kind": "text", "name": name, "text": raw.decode("utf-8")})
            except Exception:
                return [], f"{name}: this kind of file is not supported (images, PDF, text and code are)."
    return out, ""


def _gemini_parts(text, files):
    parts = []
    for f in files:
        if f["kind"] in ("image", "pdf"):
            parts.append({"inline_data": {"mime_type": f["mime"], "data": f["b64"]}})
        else:
            parts.append({"text": f"[file {f['name']}]\n{f['text']}\n[end of {f['name']}]"})
    parts.append({"text": text})
    return parts


def _claude_content(text, files):
    blocks = []
    for f in files:
        if f["kind"] == "image":
            blocks.append({"type": "image", "source": {"type": "base64", "media_type": f["mime"], "data": f["b64"]}})
        elif f["kind"] == "pdf":
            blocks.append({"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": f["b64"]}})
        else:
            blocks.append({"type": "text", "text": f"[file {f['name']}]\n{f['text']}\n[end of {f['name']}]"})
    blocks.append({"type": "text", "text": text})
    return blocks


# ------------------------------------------------------------------ calls
def _post(url, payload, headers, timeout=120):
    req = urllib.request.Request(url, method="POST", data=json.dumps(payload).encode(),
                                 headers={"content-type": "application/json", "user-agent": "queen/24", **headers})
    with urllib.request.urlopen(req, timeout=timeout) as x:
        return json.loads(x.read().decode())


def _http_err(exc):
    body = ""
    try:
        body = exc.read().decode(errors="ignore")
        j = json.loads(body)
        body = (j.get("error") or {}).get("message") or body
    except Exception:
        pass
    return exc.code, _scrub(body)[:220]


def gemini_turn(model, history, text, files):
    """history: [(role marko|claude, text)] before this turn. -> (answer, tokens_in, tokens_out). Raises RuntimeError(line)."""
    contents = [{"role": "user" if r == "marko" else "model", "parts": [{"text": t}]} for r, t in history if t.strip()]
    contents.append({"role": "user", "parts": _gemini_parts(text, files)})
    keys = _keys()
    if not keys:
        raise RuntimeError("no Google Cloud key found in the CGP_free_credits file")
    last = ""
    for k in keys:                                   # AIza first, the AQ. backup when the first is refused
        try:
            j = _post(f"{GEMINI}/models/{model}:generateContent", {"contents": contents}, {"x-goog-api-key": k})
            cand = (j.get("candidates") or [{}])[0]
            ans = "".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
            u = j.get("usageMetadata") or {}
            if not ans.strip():
                raise RuntimeError("Gemini gave no text (" + str(cand.get("finishReason") or j.get("promptFeedback") or "empty") + ")")
            return ans.strip(), int(u.get("promptTokenCount") or 0), int(u.get("candidatesTokenCount") or 0) + int(u.get("thoughtsTokenCount") or 0)
        except urllib.error.HTTPError as exc:
            code, msg = _http_err(exc)
            last = f"Gemini {code}: {msg}"
            if code in (400, 404):
                break                                # the request itself is wrong: another key will not help
        except RuntimeError:
            raise
        except Exception as exc:
            last = _scrub(f"Gemini did not answer: {exc}")[:200]
    raise RuntimeError(last or "Gemini did not answer")


def _adc_token():
    try:
        import google.auth
        import google.auth.transport.requests as gr
        creds, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
        creds.refresh(gr.Request())
        return creds.token
    except ImportError as exc:
        raise NotReady("the google-auth library cannot be loaded (" + _scrub(exc)[:80] + ")")
    except Exception as exc:
        m = str(exc).lower()
        if "could not automatically determine credentials" in m or "default credentials" in m:
            raise NotReady("no sign-in yet (gcloud auth application-default login)")
        raise NotReady("sign-in not usable: " + _scrub(str(exc))[:100])


def claude_turn(model, history, text, files):
    """Claude on Vertex AI. -> (answer, tin, tout). Raises NotReady(short reason) when it cannot be used yet."""
    token = _adc_token()
    msgs = [{"role": "user" if r == "marko" else "assistant", "content": t} for r, t in history if t.strip()]
    # Anthropic wants alternating roles, starting with user
    clean = []
    for m in msgs:
        if clean and clean[-1]["role"] == m["role"]:
            clean[-1]["content"] += "\n\n" + m["content"]
        else:
            clean.append(m)
    while clean and clean[0]["role"] != "user":
        clean.pop(0)
    if clean and clean[-1]["role"] == "user":
        clean.pop()
    clean.append({"role": "user", "content": _claude_content(text, files)})
    payload = {"anthropic_version": "vertex-2023-10-16", "messages": clean, "max_tokens": 4096}
    reason = ""
    for host, loc in (("aiplatform.googleapis.com", "global"), ("us-east5-aiplatform.googleapis.com", "us-east5")):
        url = (f"https://{host}/v1/projects/{PROJECT}/locations/{loc}/publishers/anthropic/models/{model}:rawPredict")
        try:
            j = _post(url, payload, {"authorization": "Bearer " + token})
            ans = "".join(b.get("text", "") for b in j.get("content") or [] if b.get("type") == "text")
            u = j.get("usage") or {}
            return ans.strip(), int(u.get("input_tokens") or 0), int(u.get("output_tokens") or 0)
        except urllib.error.HTTPError as exc:
            code, msg = _http_err(exc)
            if code in (401, 403):
                raise NotReady("access pending, Google answered %d: %s" % (code, msg[:110]))
            reason = f"Google answered {code}: {msg[:110]}"
            if code not in (404, 400):
                break
        except Exception as exc:
            reason = _scrub(f"no answer ({exc})")[:110]
            break
    if "404" in reason:
        raise NotReady("access pending, " + reason)
    raise RuntimeError("Claude on Google Cloud: " + reason)


def run(model, history, text, files):
    """One turn on Google Cloud. -> dict {text, cost, tin, tout} or {error}. Never raises; never carries a key."""
    try:
        if is_vertex(model) and not VERTEX_ENABLED:
            return {"error": "Google Cloud here is Gemini only: pick a Gemini model."}
        if is_vertex(model):
            ans, tin, tout = claude_turn(model, history, text, files)
        else:
            ans, tin, tout = gemini_turn(model, history, text, files)
    except NotReady as exc:
        return {"error": "Claude on Google Cloud is not ready yet: " + str(exc)}
    except RuntimeError as exc:
        return {"error": _scrub(exc)[:260]}
    except Exception as exc:
        return {"error": _scrub(f"Google Cloud did not answer: {exc}")[:260]}
    cost = _cost(model, tin, tout)
    ledger(cost, text, model)
    return {"text": ans, "cost": cost, "tin": tin, "tout": tout}
