"""Queen's hands in the VM's Gemini image worker (15.11.2026).

Marko, 15.11.2026: "poses for yoga create with Queen in this machine" (the chromium-vm). Pictures in a given style are made
by the Gemini worker of chromium-vm (skill chromium-vm; batch.json on Drive with per-item refs and prompt), never in the
Mac's Chrome, and nothing generated comes to the Mac except the final images asked for (Drive-hub rule).

    POST /api/vm-gemini/batch {name, folder, refs: [local paths], items: [{name, prompt, refs?: [file names]}],
                               accounts?: [...], fetch_to?: dir}   -> starts the batch
    GET  /api/vm-gemini/status?folder=Gemini/<folder>               -> files made so far + the worker's last log lines
    POST /api/vm-gemini/fetch {folder, names: [...], to: dir}       -> copies the finished pictures from Drive to a local folder
Runs on the Mac through ssh ubuntu@chromium-vm, or locally when Queen runs on the VM itself.
"""
import json
import os
import shlex
import socket
import subprocess
import tempfile

from flask import jsonify, request

VM = "ubuntu@chromium-vm"
DRIVE = "gdrive:Chromium Downloads"
ACCOUNTS = ["marko.bosko@auroville.community", "marko.bosko@gmail.com"]


def _sh(cmd, timeout=600):
    """run a shell command on the VM (locally when Queen is on the VM)"""
    if "chromium" in socket.gethostname():
        argv = ["bash", "-lc", cmd]
    else:
        argv = ["ssh", "-o", "ConnectTimeout=15", VM, cmd]
    p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout)
    return p.returncode, (p.stdout + p.stderr).strip()


def _put(local, remote_tmp):
    if "chromium" in socket.gethostname():
        subprocess.run(["cp", local, remote_tmp], check=True)
    else:
        subprocess.run(["scp", "-q", local, f"{VM}:{remote_tmp}"], check=True)


def start_batch(spec):
    folder = spec["folder"].strip("/")                         # e.g. Gemini/asana-guide
    refs_dir = f"{folder}/refs"
    _sh("mkdir -p /tmp/vmgem")
    for r in spec.get("refs", []):
        _put(r, f"/tmp/vmgem/{os.path.basename(r)}")
        _sh(f"rclone copyto /tmp/vmgem/{shlex.quote(os.path.basename(r))} {shlex.quote(DRIVE + '/' + refs_dir + '/' + os.path.basename(r))}")
    default_refs = [os.path.basename(r) for r in spec.get("refs", [])]
    batch = {"name": spec["name"], "accounts": spec.get("accounts") or ACCOUNTS, "folder": folder, "refs": refs_dir,
             "pause_seconds": [40, 80],
             "items": [{"name": i["name"], "refs": i.get("refs") or default_refs, "prompt": i["prompt"]} for i in spec["items"]]}
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(batch, f, indent=1)
    _put(f.name, "/tmp/vmgem/batch.json")
    os.remove(f.name)
    # keep the previous batch (another job may be in it), then the worker reads the new one
    _sh(f"rclone copyto {shlex.quote(DRIVE + '/Gemini/_batch/batch.json')} {shlex.quote(DRIVE + '/Gemini/_batch/batch-prev-before-' + spec['name'] + '.json')}")
    _sh(f"rclone copyto /tmp/vmgem/batch.json {shlex.quote(DRIVE + '/Gemini/_batch/batch.json')}")
    _sh(f"rclone copyto /tmp/vmgem/batch.json {shlex.quote(DRIVE + '/Gemini/_batch/batch-' + spec['name'] + '.json')}")
    _, out1 = _sh("vmctl start chrome")
    # both accounts need a Gemini window; the worker opens them only when the profile window exists
    _sh("export DISPLAY=:1; for p in Default 'Profile 1'; do nohup /opt/google/chrome/chrome --user-data-dir=$HOME/.config/chromium-vm-chrome "
        "--profile-directory=\"$p\" https://gemini.google.com/app >/dev/null 2>&1 & sleep 5; done", timeout=60)
    _sh("vmctl stop gemini; vmctl start gemini")
    return {"ok": True, "items": len(batch["items"]), "folder": folder}


def status(folder):
    _, files = _sh(f"rclone lsf {shlex.quote(DRIVE + '/' + folder)} | grep -v '^refs/'")
    _, log = _sh("tail -4 ~/.config/chromium-vm/workers/gemini/worker.log")
    return {"files": files.splitlines(), "log": log.splitlines()}


def fetch(folder, names, to):
    os.makedirs(to, exist_ok=True)
    got = []
    for n in names:
        fn = n if n.endswith(".png") else n + ".png"
        _sh(f"rclone copyto {shlex.quote(DRIVE + '/' + folder + '/' + fn)} /tmp/vmgem/{shlex.quote(fn)}")
        if "chromium" in socket.gethostname():
            subprocess.run(["cp", f"/tmp/vmgem/{fn}", os.path.join(to, fn)], check=True)
        else:
            subprocess.run(["scp", "-q", f"{VM}:/tmp/vmgem/{fn}", os.path.join(to, fn)], check=True)
        got.append(os.path.join(to, fn))
    return got


def register(app):
    @app.route("/api/vm-gemini/batch", methods=["POST"])
    def vm_gemini_batch():
        try:
            return jsonify(start_batch(request.get_json(force=True)))
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/api/vm-gemini/status")
    def vm_gemini_status():
        return jsonify(status(request.args.get("folder", "Gemini/asana-guide")))

    @app.route("/api/vm-gemini/fetch", methods=["POST"])
    def vm_gemini_fetch():
        d = request.get_json(force=True)
        try:
            return jsonify({"ok": True, "files": fetch(d["folder"], d["names"], d["to"])})
        except Exception as e:
            return jsonify({"ok": False, "error": str(e)}), 500
