#!/usr/bin/env bash
# Installs Groq AI Studio into ~/.groq (the folder the code expects). No key is read or copied:
# keys are added later in the app (Key Manager) or put in ~/.groq/keys.txt by hand.
set -euo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
G="${HOME}/.groq"
# Queen's lessons as tests (13.11.2026): no install while one fails
python3 "${SRC}/qwen_app/test_rename_skill.py" >/dev/null || { echo "test_rename_skill.py FAILED: not installed" >&2; exit 1; }
python3 "${SRC}/qwen_app/test_triple_chat.py" >/dev/null || { echo "test_triple_chat.py FAILED: not installed" >&2; exit 1; }
python3 "${SRC}/qwen_app/test_training.py" >/dev/null || { echo "test_training.py FAILED: not installed" >&2; exit 1; }
mkdir -p "${G}/qwen_app"
[[ -x "${G}/venv/bin/python" ]] || python3 -m venv "${G}/venv"
"${G}/venv/bin/python" -m pip install --quiet --upgrade pip
"${G}/venv/bin/python" -m pip install --quiet -r "${SRC}/requirements.txt"
# every python file plus the page: naming them one by one meant brain.py and then model_router.py
# were written, imported, and silently missing from ~/.groq (12.11.2026, twice). Copy the lot.
cp "${SRC}"/qwen_app/*.py "${SRC}/qwen_app/index.html" "${G}/qwen_app/"
cp "${SRC}/groq_pool.py" "${SRC}/groq_cli.py" "${SRC}/qwen" "${SRC}/groq-chat" "${SRC}/groq-cli" "${SRC}/version.json" "${G}/"
mkdir -p "${G}/queen_skills" && cp "${SRC}"/queen_skills/*.md "${SRC}"/queen_skills/*.json "${G}/queen_skills/" 2>/dev/null || true   # Queen's skills (12.11.2026)
chmod +x "${G}/qwen" "${G}/groq-chat" "${G}/groq-cli" "${G}/groq_cli.py"
echo "Installed. Put ${G} on the PATH (export PATH=\"\$HOME/.groq:\$PATH\"), then run: qwen"
