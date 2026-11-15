"""Queen's hands for apps and repositories: open, rename an app, rename a repository, install the latest release (13.11.2026).

Marko, 13.11.2026: "You stop doing anything physically in this computer: moving things, renaming things. Mantra, Macro, and
Queen are doing everything." (MANTRA_MANIFEST modules/claude-teaches-only.md)

Chat commands, answered locally (no model, no cost). The long ones run as a task (its own chat) and every step that changes
something waits for the supervisor (`queen pending / approve`):

    open app <name>              quit app <name>         a star app, matched by its name (Star API :8863)
    rename app "<old>" to "<new>" in <REPO>
        every tracked text file of the repo (code, workflow, plist; in .md only README/TAKEOVER titles) gets the new name,
        the version goes up by one (Swift `let VERSION = N`, Android `appVersion=N`), diff -> approve -> commit + push to
        main -> the GitHub Actions run is watched to its colour; the run link and the release tag are reported.
    rename repo <OLD> to <NEW>   GitHub rename (outward: the approval note must say Marko asked) + the local remote URL.
    install latest <REPO> [replacing "<old app name>"]
        Mac: the release .zip into /Applications, re-signed "Mantra Apps", the old-named copy quit and removed, the star
        rows renamed; Android: the release .apk on every phone/emulator adb sees (adb install -r).
"""
import difflib
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path

DEV = Path.home() / "Developer"
STAR = "http://127.0.0.1:8863"
OWNER = "markoboskoauroville"
ADB = str(Path.home() / "Library/Android/sdk/platform-tools/adb")
TEXT_EXT = {".swift", ".kt", ".kts", ".java", ".xml", ".plist", ".sh", ".yml", ".yaml", ".json", ".properties", ".gradle",
            ".py", ".html", ".js", ".css", ".txt", ".toml", ".strings", ""}


class SkillError(Exception):
    pass


def _run(cmd, cwd=None, timeout=600):
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr)


def _today():
    t = time.localtime()
    return f"{t.tm_mday}.{t.tm_mon}.{t.tm_year}"


# ---------- star apps ----------

def _star(path, method="GET"):
    req = urllib.request.Request(STAR + path, method=method, data=b"{}" if method == "POST" else None,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.load(r)


_FILLER = {"app", "the", "mac", "a", "my", "(mantra)", "mantra", "application"}


def _words(s):
    return {w for w in re.findall(r"[a-z0-9]+", s.lower()) if w not in _FILLER}


def _word_score(h, words):
    """How well one hint word matches a name: equal 1, prefix 0.9, inside 0.7, close spelling by ratio."""
    best = 0.0
    for w in words:
        if h == w:
            return 1.0
        if w.startswith(h) and len(h) >= 2:
            best = max(best, 0.9)
        elif h in w and len(h) >= 3:
            best = max(best, 0.7)
        else:
            best = max(best, difflib.SequenceMatcher(None, h, w).ratio() * 0.8)
    return best


def rank_names(hint, names):
    """Every name scored against the hint, most probable first: words, prefixes, abbreviations (mrv, vmv), spelling.
    Marko, 13.11.2026: "The name can be an approximation ... even an abbreviation ... what she thinks makes the most
    sense needs to be at the top." """
    want = [w for w in re.findall(r"[a-z0-9]+", hint.lower()) if w not in _FILLER] or re.findall(r"[a-z0-9]+", hint.lower())
    out = []
    for n in names:
        words = [w for w in re.findall(r"[a-z0-9]+", n.lower()) if w not in _FILLER] or re.findall(r"[a-z0-9]+", n.lower())
        if n.lower().strip() in (hint.lower().strip(), f"{hint.lower().strip()} (mantra)"):
            out.append((2.0, n)); continue
        cover = sum(_word_score(h, words) for h in want) / max(1, len(want))
        joined = "".join(want)
        for initials in {"".join(w[0] for w in words),
                         "".join(w[0] for w in re.findall(r"[a-z0-9]+", n.lower()) if w != "mantra"),
                         "".join(w[0] for w in re.findall(r"[a-z0-9]+", n.lower()))}:
            if len(want) == 1 and len(joined) >= 2 and (joined == initials or (initials.startswith(joined) and len(joined) >= 3)):
                cover = max(cover, 0.95 if joined == initials else 0.85)
        extra = max(0, len(words) - len(want))
        out.append((round(cover - 0.03 * extra, 3), n))      # fewer unasked words = more probable
    return sorted(out, key=lambda x: (-x[0], len(x[1])))


class Ambiguous(SkillError):
    pass


def best_name(hint, names):
    """The one most probable name, or Ambiguous with the top 5 (most probable first) for Marko to choose."""
    ranked = [r for r in rank_names(hint, names) if r[0] > 0.3]
    if ranked and ranked[0][0] >= 0.75 and (len(ranked) == 1 or ranked[0][0] - ranked[1][0] >= 0.12):
        return ranked[0][1]
    if not ranked:
        raise SkillError(f"nothing matches '{hint}'")
    top = "\n".join(f"  {i}. {n}  ({int(min(sc, 1) * 100)}%)" for i, (sc, n) in enumerate(ranked[:5], 1))
    raise Ambiguous(f"'{hint}' is not one clear match. Most probable first:\n{top}\nSay the number.")


def star_find(name):
    return best_name(name, [a["name"] for a in _star("/apps").get("apps", [])])


def star_open(name, action="open"):
    app = star_find(name)
    res = _star(f"/apps/{urllib.parse.quote(app, safe='')}/{action}", "POST")
    time.sleep(2.5)
    state = _star(f"/apps/{urllib.parse.quote(app, safe='')}")
    running = state.get("ok") is not False and "not running" not in str(state.get("message", ""))
    return app, res, running


# ---------- repositories ----------

def repo_dir(repo):
    """The local clone whose origin is <repo> (the folder name may differ from the repo name)."""
    want = repo.split("/")[-1].lower()
    for d in sorted(DEV.iterdir()):
        cfg = d / ".git" / "config"
        if cfg.is_file():
            m = re.search(r"url = .*[/:][^/]+/([^/\s]+?)(\.git)?\s*$", cfg.read_text(), re.M)
            if m and m.group(1).lower() == want:
                return d
    raise SkillError(f"no local clone of {repo} in ~/Developer")


def _bump(text, path):
    for pat, fmt in ((r"^(let VERSION = )(\d+)", "{}{}"), (r"^(appVersion=)(\d+)", "{}{}")):
        m = re.search(pat, text, re.M)
        if m:
            n = int(m.group(2)) + 1
            return text[:m.start()] + fmt.format(m.group(1), n) + text[m.end():], n
    return text, None


def plan_rename(d, old, new):
    """{path: (before, after)} and the new version number."""
    _, files = _run(["git", "ls-files"], cwd=d)
    changes, version = {}, None
    for rel in files.split("\n"):
        p = d / rel
        if not rel or not p.is_file() or p.stat().st_size > 2_000_000:
            continue
        name = p.name
        if p.suffix == ".md" and name not in ("README.md", "TAKEOVER.md"):
            continue
        if p.suffix not in TEXT_EXT and p.suffix != ".md" and name != "Makefile":
            continue
        try:
            before = p.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        after = before
        if p.suffix == ".md":       # docs keep their history: only the title line, plus one dated line in TAKEOVER
            lines = after.split("\n")
            if lines and lines[0].startswith("#"):
                lines[0] = lines[0].replace(old, new)
            if name == "TAKEOVER.md" and f"is now **{new}**" not in after:
                lines.insert(1, f"\n**Renamed {_today()}:** {old} is now **{new}** (Marko). Done by Queen.")
            after = "\n".join(lines)
        else:   # Marko's quoted words stay as he said them (13.11.2026: a comment quoting him was rewritten)
            # every spelling of the name: as written, UPPER CASE, lower case (round 6: the Android title was
            # "MANTRA REMOTE VNC ▊" in capitals and stayed after the rename)
            # each place keeps its own letter case (round 7: "MANTRA REMOTE VNC" would have become "Mantra Remote Viewing")
            pat = re.compile(re.escape(old), re.I)

            def _case(m):
                t = m.group(0)
                return new.upper() if t.isupper() else new.lower() if t.islower() else new

            # and the file-name forms: mantra-remote-vnc / mantra_remote_vnc (round 8: the APK kept "mantra-remote-vnc")
            ow, nw = re.findall(r"[A-Za-z0-9]+", old.lower()), re.findall(r"[A-Za-z0-9]+", new.lower())
            slugs = [("-".join(ow), "-".join(nw)), ("_".join(ow), "_".join(nw))] if len(ow) > 1 else []

            def _forms(part):
                for a, b in slugs:
                    part = re.sub(re.escape(a), lambda m: b.upper() if m.group(0).isupper() else b, part, flags=re.I)
                return part

            def _swap(l):
                # web addresses change only when the old name IS an address part (owner/repo); round 8b: the name
                # MANTRA_REMOTE_VNC matched inside github.com/.../MANTRA_REMOTE_VNC_TAILSCALE
                if "/" in old:
                    return pat.sub(_case, l)
                parts = re.split(r"(https?://\S+)", l)
                return "".join(p if p.startswith("http") else _forms(pat.sub(_case, p)) for p in parts)

            after = "".join(l if re.search(r"Marko[^\n]{0,40}[\"“]", l) else _swap(l) for l in after.splitlines(True))
        if version is None and (name == "gradle.properties" or (p.suffix == ".swift" and old in before)):
            bumped, n = _bump(after, p)
            if n:
                after, version = bumped, n
        if after != before:
            changes[rel] = (before, after)
    return changes, version


_NAME_SOURCES = (r'^NAME="([^"]+)"', r'^\s*APP:\s*"([^"]+)"', r'android:label="([^"@][^"]*)"', r'^let APP_NAME = "([^"]+)"')


def resolve_old(d, hint):
    """The name the app really carries in its code (Marko says "Mantra Remote", the label is "Mantra Remote VNC")."""
    _, out = _run(["git", "grep", "-l", "-i", "-F", hint], cwd=d)
    names = set()
    _, files = _run(["git", "ls-files", "*.sh", "*.yml", "*.swift", "*AndroidManifest.xml"], cwd=d)
    for rel in files.split():
        try:
            t = (d / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for pat in _NAME_SOURCES:
            names.update(re.findall(pat, t, re.M))
    if hint in names or out.strip():   # the words as given are really in the code (any case): that is the name
        return hint
    return best_name(hint, sorted(names)) if names else (hint if out.strip() else best_name(hint, []))


def _diff(changes):
    out = []
    for rel, (a, b) in changes.items():
        out.append("".join(difflib.unified_diff(a.splitlines(True), b.splitlines(True), rel, rel, n=0)))
    return "\n".join(out)


def _slug(d):
    _, url = _run(["git", "remote", "get-url", "origin"], cwd=d)
    m = re.search(r"[/:]([^/]+/[^/\s]+?)(\.git)?\s*$", url.strip())
    return m.group(1) if m else ""


def watch_run(slug, sha, chat, minutes=30):
    """The Actions run of this commit, to its end: (conclusion, url)."""
    end = time.time() + minutes * 60
    url = ""
    while time.time() < end:
        code, out = _run(["gh", "run", "list", "-R", slug, "--commit", sha, "--json", "url,status,conclusion,name"])
        try:
            runs = json.loads(out) if code == 0 else []
        except ValueError:
            runs = []
        if runs:
            url = runs[0]["url"]
            if all(r["status"] == "completed" for r in runs):
                bad = [r for r in runs if r["conclusion"] != "success"]
                if bad:   # a job GitHub never started says why in its annotation (13.11.2026: billing = private repo)
                    rid = url.rstrip("/").split("/")[-1]
                    _, jobs = _run(["gh", "api", f"repos/{slug}/actions/runs/{rid}/jobs", "-q", ".jobs[0].id"])
                    _, why = _run(["gh", "api", f"repos/{slug}/check-runs/{jobs.strip()}/annotations", "-q", ".[0].message"])
                    if "payments have failed" in why or "spending limit" in why:
                        return ("failure: GitHub did not start the job because the repository is PRIVATE. Code repos are "
                                "public (MANTRA_MANIFEST building-repos-public.md): run the three secret checks, make it "
                                "public, run the build again. Never send Marko to billing."), url
                return ("failure" if bad else "success"), url
        time.sleep(20)
    return "not finished", url


def rename_app(old, new, repo, chat):
    import supervisor  # noqa: PLC0415
    d = repo_dir(repo)
    title = chat.title
    _, st = _run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=d)
    if st.strip():
        chat.say(f"Stopped: {d.name} has uncommitted changes; I do not mix my work into them:\n{st[:500]}")
        raise SkillError("uncommitted changes in the repository")
    code, out = _run(["git", "pull", "--ff-only", "-q", "origin", "main"], cwd=d)
    if code:
        raise SkillError(f"git pull failed: {out[-300:]}")
    real = resolve_old(d, old)
    if real != old:
        chat.say(f"'{old}' is what was asked; the app's real name in its code is '{real}'. I rename that.")
        old = real
    changes, version = plan_rename(d, old, new)
    # a TAKEOVER line or a version bump alone is not a rename (round 9: a plan that only bumped the version)
    if not [r for r in changes if not r.endswith(".md") and r not in ("android/gradle.properties", "gradle.properties")
            and not (r.endswith(".swift") and changes[r][1].replace(f"VERSION = {version}", f"VERSION = {(version or 1) - 1}") == changes[r][0])]:
        chat.say(f"'{old}' is nowhere in the code of {d.name}; nothing to rename.")
        raise SkillError(f"'{old}' not found in {repo}")
    diff = _diff(changes)
    chat.say(f"Plan: {len(changes)} files in {d.name} ({_slug(d)}), version -> v{version or '?'}.\n" + diff[:6000])
    supervisor.propose_and_wait(title, "change", f"{len(changes)} files, '{old}' -> '{new}', v{version}", diff[:20000])
    for rel, (_, after) in changes.items():
        (d / rel).write_text(after, encoding="utf-8")
    chat.say("Change approved and written.")
    msg = f"Renamed to {new} (was {old}), v{version}" if version else f"Renamed to {new} (was {old})"
    supervisor.propose_and_wait(title, "push", msg, f"commit and push to main = the GitHub Actions build:\n{msg}\n"
                                + "\n".join(changes))
    _run(["git", "add", "--"] + list(changes), cwd=d)
    code, out = _run(["git", "commit", "-q", "-m", msg + "\n\nMade by Queen (Groq AI Studio), each step approved by the supervisor."], cwd=d)
    if code:
        raise SkillError(f"commit failed: {out[-300:]}")
    code, out = _run(["git", "push", "-q", "origin", "main"], cwd=d)
    if code:
        raise SkillError(f"push failed: {out[-300:]}")
    _, sha = _run(["git", "rev-parse", "HEAD"], cwd=d)
    slug = _slug(d)
    if not list((d / ".github" / "workflows").glob("*.y*ml")):   # nothing builds on GitHub: do not wait 30 min for it
        chat.say(f"Pushed {sha.strip()[:7]} to main. This repository has no GitHub build (it goes live with its own "
                 f"deploy.sh, if it has one).\nTask finished.")
        return {"repo": slug, "files": files, "build": "success", "built_on_github": False, "run": ""}
    chat.say(f"Pushed {sha.strip()[:7]} to main. Watching the GitHub Actions run.")
    colour, url = watch_run(slug, sha.strip(), chat)
    _, rel = _run(["gh", "release", "view", "-R", slug, "--json", "tagName,name,assets",
                   "-q", '.tagName + " | " + .name + " | " + ([.assets[].name] | join(","))'])
    chat.say(f"Build: {colour.upper()} {url}\nLatest release: {rel.strip()}\nTask finished." if colour == "success" else
             f"Build: {colour.upper()} {url}\nThe rename is pushed but the build did not pass: look at the run.")
    return {"repo": slug, "version": version, "files": list(changes), "build": colour, "run": url, "release": rel.strip()}


def rename_repo(old, new, chat):
    import supervisor  # noqa: PLC0415
    d = repo_dir(old)
    slug = _slug(d)
    owner = slug.split("/")[0] or OWNER
    note = supervisor.propose_and_wait(chat.title, "github rename", f"{slug} -> {owner}/{new}",
                                       "OUTWARD: renames the repository on GitHub (old links redirect). "
                                       "Approve only with a note saying Marko asked for it.")
    if "marko" not in (note or "").lower():
        chat.say("Not done: a GitHub rename needs Marko's word in the approval note.")
        raise SkillError("the approval note does not say Marko asked")
    code, out = _run(["gh", "repo", "rename", new, "-R", slug, "--yes"])
    if code:
        raise SkillError(f"gh repo rename failed: {out[-300:]}")
    _run(["git", "remote", "set-url", "origin", f"https://github.com/{owner}/{new}.git"], cwd=d)
    code, out = _run(["gh", "repo", "view", f"{owner}/{new}", "--json", "name,url", "-q", ".url"])
    _, remote = _run(["git", "remote", "get-url", "origin"], cwd=d)
    chat.say(f"GitHub: {out.strip()} ({'found' if code == 0 else 'NOT found'}). Local {d.name} origin: {remote.strip()}."
             " The folder keeps its name.")
    old_name = old.split("/")[-1]
    _, refs = _run(["git", "grep", "-l", "-F", f"{owner}/{old_name}"], cwd=d)
    if refs.strip():   # links in the code (the update button) point at the new address, in a new version
        chat.say(f"The code still links to {owner}/{old_name} in: {', '.join(refs.split())}. Renaming those links.")
        return rename_app(f"{owner}/{old_name}", f"{owner}/{new}", f"{owner}/{new}", chat)
    chat.say("Task finished.")
    return {"repo": f"{owner}/{new}", "url": out.strip(), "local": str(d), "verified": code == 0}


def install_latest(repo, chat, replacing=None):
    import supervisor  # noqa: PLC0415
    try:
        slug = _slug(repo_dir(repo))
    except SkillError:   # round 11 (13.11.2026): installing needs only the release, not a clone (TTT has none here)
        slug = repo if "/" in repo else f"markoboskoauroville/{repo}"
    _, info = _run(["gh", "release", "view", "-R", slug, "--json", "tagName,assets"])
    rel = json.loads(info)
    assets = [a["name"] for a in rel["assets"]]
    apk = [a for a in assets if a.endswith(".apk")]
    zips = [a for a in assets if a.endswith(".zip")]
    if not apk and not zips:
        raise SkillError(f"release {rel['tagName']} of {slug} has no .zip or .apk")
    devices = []
    if apk:
        _, out = _run([ADB, "devices"])
        devices = [l.split()[0] for l in out.splitlines()[1:] if l.strip().endswith("device")]
        if not devices:   # "There is always a phone: the Pixel 7 emulator" (Marko, 26.9.2026)
            chat.say("No phone on adb: starting the Pixel 7 emulator (Pixel_7_API_35).")
            subprocess.Popen([str(Path.home() / "Library/Android/sdk/emulator/emulator"), "-avd", "Pixel_7_API_35",
                              "-no-snapshot-save"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            _run([ADB, "wait-for-device"], timeout=300)
            for _ in range(60):
                _, boot = _run([ADB, "shell", "getprop", "sys.boot_completed"])
                if boot.strip() == "1":
                    break
                time.sleep(5)
            _, out = _run([ADB, "devices"])
            devices = [l.split()[0] for l in out.splitlines()[1:] if l.strip().endswith("device")]
    plan = (f"Release {rel['tagName']} of {slug}: " + (f"{zips[0]} into /Applications" if zips else "")
            + (f"{apk[0]} on {devices or 'no device (start the Pixel 7 emulator first)'}" if apk else "")
            + (f"; the old '{replacing}' quit and removed, the star rows renamed" if replacing else ""))
    chat.say("Plan: " + plan)
    tmp = Path(tempfile.mkdtemp(prefix="queen-install-"))
    if replacing and zips:   # the old app's real name, by probability over /Applications (round 5: a short name was given)
        installed = [p.stem for p in Path("/Applications").glob("*.app")]
        replacing = best_name(replacing, installed)
        plan = plan.split("; the old")[0] + f"; the old '{replacing}' quit and removed, the star rows renamed"
        chat.say("Plan with the real old name: " + plan)
    supervisor.propose_and_wait(chat.title, "install", plan, plan)
    asset = (zips or apk)[0]
    code, out = _run(["gh", "release", "download", rel["tagName"], "-R", slug, "-p", asset, "-D", str(tmp)])
    if code:
        raise SkillError(f"download failed: {out[-300:]}")
    result = {"release": rel["tagName"], "asset": asset}
    if zips:
        _run(["ditto", "-x", "-k", str(tmp / asset), str(tmp)])
        apps = list(tmp.glob("*.app"))
        if not apps:
            raise SkillError("no .app inside the zip")
        app = apps[0]
        target = Path("/Applications") / app.name
        for name in {replacing, app.stem} - {None}:
            _run(["osascript", "-e", f'tell application "{name}" to quit'])
        time.sleep(2)
        if replacing and (Path("/Applications") / f"{replacing}.app").exists():
            shutil.rmtree(Path("/Applications") / f"{replacing}.app")
        if target.exists():
            shutil.rmtree(target)
        _run(["ditto", str(app), str(target)])
        code, out = _run(["codesign", "--force", "--deep", "--sign", "Mantra Apps", str(target)])
        signed = code == 0
        if replacing:
            for rows in (DEV / "STAR_SWIFT" / "rows.json", Path.home() / ".config" / "star-rows.json"):
                if rows.is_file():
                    t = rows.read_text(encoding="utf-8")
                    if replacing in t:
                        rows.write_text(t.replace(replacing, app.stem), encoding="utf-8")
            sd = DEV / "STAR_SWIFT"
            _, st = _run(["git", "status", "--porcelain", "rows.json"], cwd=sd)
            if st.strip():
                _run(["git", "commit", "-q", "-m", f"Star: {replacing} is now {app.stem}\n\nMade by Queen.", "rows.json"], cwd=sd)
                _run(["git", "pull", "-q", "--rebase", "origin", "main"], cwd=sd)
                _run(["git", "push", "-q", "origin", "main"], cwd=sd)
        _run(["open", "-g", str(target)])
        time.sleep(3)
        _, ver = _run(["/usr/libexec/PlistBuddy", "-c", "Print CFBundleShortVersionString", str(target / "Contents/Info.plist")])
        _, ps = _run(["pgrep", "-f", f"{target}/Contents/MacOS"])
        result.update(app=str(target), version=ver.strip(), signed=signed, running=bool(ps.strip()),
                      old_gone=not (replacing and (Path("/Applications") / f"{replacing}.app").exists()))
    else:
        done = {}
        for dev in devices:
            code, out = _run([ADB, "-s", dev, "install", "-r", str(tmp / asset)], timeout=300)
            done[dev] = "Success" in out
        # the package from the APK itself (round 9: it was fixed to com.mantra.remote, wrong for any other app)
        tools = sorted((Path.home() / "Library/Android/sdk/build-tools").glob("*/aapt2"))
        _, pk = _run([str(tools[-1]), "dump", "packagename", str(tmp / asset)]) if tools else (1, "")
        pkg = pk.strip().splitlines()[-1] if pk.strip() else "com.mantra.remote"
        for dev in [d for d, ok in done.items() if ok]:
            _, v = _run([ADB, "-s", dev, "shell", "dumpsys", "package", pkg])
            m = re.search(r"versionName=(\S+)", v)
            done[dev] = f"Success, versionName {m.group(1) if m else '?'}"
        result.update(devices=done)
    shutil.rmtree(tmp, ignore_errors=True)
    chat.say("Self-check: " + json.dumps(result, ensure_ascii=False) + "\nTask finished.")
    return result


def ship(repo, message, chat):
    """Ship a change Claude Code prepared in the repo (13.11.2026: Claude writes the code, Queen ships it): the diff of the
    tracked changes -> approve -> commit -> push to main -> the GitHub Actions run watched to its colour."""
    import supervisor  # noqa: PLC0415
    d = repo_dir(repo)
    _, st = _run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=d)
    files = [l[3:] for l in st.splitlines() if l.strip()]
    # new files too (13.11.2026: a book's chapters, plates and page were all new and ship left them out); .gitignore holds
    _, new = _run(["git", "ls-files", "--others", "--exclude-standard"], cwd=d)
    added = [f for f in new.splitlines() if f.strip()]
    files += added
    if not files:
        chat.say(f"Nothing to ship in {d.name}: no changed or new files.")
        raise SkillError("nothing to ship")
    _, diff = _run(["git", "diff", "--", *files], cwd=d)
    if added:
        diff = "NEW FILES:\n" + "\n".join(f"  {f} ({(d / f).stat().st_size // 1024} KB)" for f in added) + "\n\n" + diff
    chat.say(f"Plan: ship {len(files)} files of {d.name} ({_slug(d)}): {message}\n" + diff[:6000])
    supervisor.propose_and_wait(chat.title, "push", f"{len(files)} files: {message}", diff[:20000])
    _run(["git", "add", "--", *files], cwd=d)
    code, out = _run(["git", "commit", "-q", "-m", message + "\n\nShipped by Queen (Groq AI Studio), approved by the supervisor."], cwd=d)
    if code:
        raise SkillError(f"commit failed: {out[-300:]}")
    code, out = _run(["git", "pull", "-q", "--rebase", "origin", "main"], cwd=d)
    code, out = _run(["git", "push", "-q", "origin", "main"], cwd=d)
    if code:
        raise SkillError(f"push failed: {out[-300:]}")
    _, sha = _run(["git", "rev-parse", "HEAD"], cwd=d)
    slug = _slug(d)
    if not list((d / ".github" / "workflows").glob("*.y*ml")):   # nothing builds on GitHub: do not wait for it
        chat.say(f"Pushed {sha.strip()[:7]} to main. This repository has no GitHub build (it goes live with its own "
                 f"deploy.sh, if it has one).\nTask finished.")
        return {"repo": slug, "files": files, "build": "success", "built_on_github": False, "run": ""}
    chat.say(f"Pushed {sha.strip()[:7]} to main. Watching the GitHub Actions run.")
    colour, url = watch_run(slug, sha.strip(), chat)
    if colour.startswith("failure: GitHub did not start") and _deploy_script(d):
        # a private DATA repo (students, personal records) stays private (Marko, 13.11.2026): its own deploy.sh deploys it
        # never call it SUCCESS: the run was refused (13.11.2026, Queen's report said "Build: SUCCESS" for a refused run)
        chat.say(f"Pushed. GitHub did NOT build it (private data repository, the run was refused: {url}); it stays private "
                 f"and goes live with: deploy {d.name}\nTask finished.")
        return {"repo": slug, "files": files, "build": "success", "built_on_github": False, "run": url}
    _, rel = _run(["gh", "release", "view", "-R", slug, "--json", "tagName,name", "-q", '.tagName + " | " + .name'])
    chat.say(f"Build: {colour.upper()} {url}\nLatest release: {rel.strip() or 'none'}\n" + ("Task finished." if colour == "success" else
             "The change is pushed but the build did not pass: look at the run."))
    return {"repo": slug, "files": files, "build": colour, "run": url, "release": rel.strip()}


def _deploy_script(d):
    for c in (d / "deploy.sh", d / "website" / "deploy.sh"):
        if c.is_file():
            return c
    return None


def deploy(repo, chat):
    """Run the repository's own deploy.sh (13.11.2026: MPA, a private data repo, goes live through it). Site only when the
    script offers --site-only. The output's last lines are the self-check; keys are never printed (the scripts filter them)."""
    import supervisor  # noqa: PLC0415
    d = repo_dir(repo)
    script = _deploy_script(d)
    if not script:
        raise SkillError(f"{d.name} has no deploy.sh")
    site_only = "--site-only" in script.read_text(errors="ignore")
    cmd = ["bash", str(script)] + (["--site-only"] if site_only else [])
    _, st = _run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=d)
    plan = f"deploy {d.name} with {script.relative_to(d)}{' --site-only' if site_only else ''}" + \
        (f" (NOT committed: {st.strip()[:200]})" if st.strip() else " (everything committed)")
    chat.say("Plan: " + plan)
    supervisor.propose_and_wait(chat.title, "deploy", plan, plan)
    code, out = _run(cmd, cwd=script.parent, timeout=900)
    tail = "\n".join(l for l in out.strip().splitlines()[-6:] if not re.search(r"(?i)token|account_id|secret", l))
    urls = re.findall(r"https://[\w.-]+\.pages\.dev\S*|https://[\w.-]+\.workers\.dev\S*", out)
    chat.say(f"Deploy {'OK' if code == 0 else 'FAILED'} (exit {code}).\n{tail}" + (f"\nLive: {urls[-1]}" if urls else "")
             + "\nTask finished.")
    if code:
        raise SkillError("the deploy script failed")
    return {"repo": d.name, "deployed": True, "live": urls[-1] if urls else None}


PHONES = {"pixel": "100.70.23.53", "nothing": "100.67.149.40"}   # Tailscale addresses; the voice daemon listens on :8840


def say_on_phone(phone, text):
    """Marko, 13.11.2026: "I don't want silent notification. I want voice engine." Since 15.11.2026 the ONE voice engine on the
    phones is TERMUX_VOICE (repo TERMUX_VOICE, voiced.py in Termux, port 8840); the old Android app Voice Engine (:8720) is
    retired. Only TEXT travels: POST /say {text, lang, from}; the phone renders (Speechify) and speaks it, one voice at a time,
    and its top notification names the sender. Same as the Mac command `phonesay <phone> "text"`."""
    phone = best_name(phone, list(PHONES))
    ip = PHONES[phone]
    req = urllib.request.Request(f"http://{ip}:8840/say", data=json.dumps({"text": text, "lang": "en", "from": "Mac \u00b7 Queen"}).encode(),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            d = json.load(r)
    except Exception as exc:
        raise SkillError(f"the {phone}'s voice daemon (voiced :8840 in Termux) does not answer: {exc}. Termux must be open or Termux:Boot armed.")
    if not d.get("ok"):
        raise SkillError(f"the phone's voice daemon said: {d}")
    return f"Spoken on the {phone} by its voice daemon (TERMUX_VOICE, queued {d.get('queued')})."


# ---------- chat ----------

_OPEN = re.compile(r"^\s*(open|quit)\s+app\s+(?P<name>.+?)\s*$", re.I)
_RENAME_APP = re.compile(r'^\s*rename\s+app\s+"(?P<old>[^"]+)"\s+to\s+"(?P<new>[^"]+)"\s+in\s+(?P<repo>[\w./-]+)\s*$', re.I)
_RENAME_REPO = re.compile(r"^\s*rename\s+repo\s+(?P<old>[\w./-]+)\s+to\s+(?P<new>[\w.-]+)\s*$", re.I)
_SHIP = re.compile(r'^\s*ship\s+(?P<repo>[\w./-]+)\s+"(?P<msg>[^"]+)"\s*$', re.I)
_SAY = re.compile(r'^\s*say\s+on\s+(?P<phone>\w+)\s+"(?P<text>[^"]+)"\s*$', re.I)
_DEPLOY = re.compile(r"^\s*deploy\s+(?P<repo>[\w./-]+)\s*$", re.I)
_INSTALL = re.compile(r'^\s*install\s+latest\s+(?P<repo>[\w./-]+)(\s+replacing\s+"(?P<old>[^"]+)")?\s*$', re.I)


_QUEUES = {}          # repo -> {"lock": Lock, "failed": title or None}


def _task(title, fn, repo=None):
    """Run a long skill as a task: its own chat, steps approved by the supervisor; the chat line answers at once.
    Tasks on the same repository run one after another in the order written, and a task after a failed or stopped one
    does not run (13.11.2026: rename, install and repo rename were fired at once; install would have put the old v42)."""
    import supervisor  # noqa: PLC0415
    from task_chat import TaskChat  # noqa: PLC0415
    chat = TaskChat(title)
    q = _QUEUES.setdefault((repo or title).split("/")[-1].lower(), {"lock": threading.Lock(), "failed": None, "n": 0})
    q["n"] += 1
    try:
        import training_log  # noqa: PLC0415
        turn = getattr(training_log.TURN, "id", None)   # the chat turn that wrote this command (training data)
    except Exception:
        training_log, turn = None, None
    if q["n"] > 1:
        chat.say("Queued: it starts when the task before it on this repository has finished well.")

    def go():
        if training_log:
            training_log.TURN.id = turn
        with q["lock"]:
            try:
                if q["failed"]:
                    chat.say(f"Not started: the task before it ({q['failed']}) did not finish well.")
                    return
                r = fn(chat)
                if isinstance(r, dict) and str(r.get("build", "success")) != "success":
                    q["failed"] = title
            except supervisor.Rejected as exc:
                q["failed"] = title
                chat.say(f"Stopped, nothing more was changed: {exc}")
            except Exception as exc:  # a failed hand says so, with the reason (never pretends)
                q["failed"] = title
                chat.say(f"FAILED: {type(exc).__name__}: {exc}")
            finally:
                q["n"] -= 1
                if q["n"] == 0:
                    q["failed"] = None      # a new request starts clean
    threading.Thread(target=go, daemon=True).start()
    return (f"Task started: {title} (chat {chat.id}). Every change waits for the supervisor's approval "
            "(queen pending); the result and its self-check are written in that chat.")


def chat_rename_command(text):
    t = (text or "").strip()
    if re.match(r"^(open|quit|rename|install|make|ship|deploy|say|book|add)\s", t, re.I) and re.search(r"<[^>]*>", t):
        return ("Not run: the command still has a placeholder in angle brackets. Write the real name (a hint is enough: "
                "the skill finds the exact name itself).")
    m = _OPEN.match(t)
    if m:
        try:
            app, res, running = star_open(m.group("name"), m.group(1).lower())
        except Exception as exc:
            return f"Could not {m.group(1).lower()} '{m.group('name')}': {exc}"
        if m.group(1).lower() == "open":
            return f"{app}: {'running, checked' if running else 'NOT running after the open call'} ({res.get('message', res)})"
        return f"{app}: {'still running' if running else 'quit, checked'}"
    m = _RENAME_APP.match(t)
    if m:
        old, new, repo = m.group("old"), m.group("new"), m.group("repo")
        return _task(f"Rename app {old} -> {new} ({repo.split('/')[-1]})", lambda c: rename_app(old, new, repo, c), repo)
    m = _RENAME_REPO.match(t)
    if m:
        old, new = m.group("old"), m.group("new")
        return _task(f"Rename repo {old.split('/')[-1]} -> {new}", lambda c: rename_repo(old, new, c), old)
    m = _SAY.match(t)
    if m:
        try:
            return say_on_phone(m.group("phone"), m.group("text"))
        except Exception as exc:
            return f"Not spoken: {exc}"
    m = _DEPLOY.match(t)
    if m:
        repo = m.group("repo")
        return _task(f"Deploy {repo.split('/')[-1]}", lambda c: deploy(repo, c), repo)
    m = _SHIP.match(t)
    if m:
        repo, msg = m.group("repo"), m.group("msg")
        return _task(f"Ship {repo.split('/')[-1]}: {msg[:50]}", lambda c: ship(repo, msg, c), repo)
    m = _INSTALL.match(t)
    if m:
        repo, old = m.group("repo"), m.group("old")
        return _task(f"Install latest {repo.split('/')[-1]}", lambda c: install_latest(repo, c, old), repo)
    from publish_skill import chat_publish_command  # noqa: PLC0415
    r = chat_publish_command(t)
    if r:
        return r
    from book_skill import chat_book_command  # noqa: PLC0415
    return chat_book_command(t)
