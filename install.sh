#!/usr/bin/env bash
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOME_DIR="${HOME}/.queen"
BACKEND_DIR="${HOME_DIR}/backend"
VENV="${HOME_DIR}/venv"

mkdir -p "${BACKEND_DIR}/queen_python_skills"
[[ -x "${VENV}/bin/python" ]] || python3 -m venv "${VENV}"
"${VENV}/bin/python" -m pip install --quiet --upgrade pip
"${VENV}/bin/python" -m pip install --quiet -r "${SRC}/requirements.txt"

"${VENV}/bin/python" "${SRC}/qwen_app/test_capi_features.py"
"${VENV}/bin/python" "${SRC}/qwen_app/test_ableton_skill.py"
"${VENV}/bin/python" "${SRC}/qwen_app/test_pair_chat.py"
"${VENV}/bin/python" "${SRC}/qwen_app/test_queen_backend.py"

for file in queen_backend.py auto_updater.py capi_chat.py capi_model_router.py \
            pair_chat.py gcloud_chat.py gemini_hands.py state_paths.py claude_link.py \
            training_log.py api_credit.py cost_gate.py app.py; do
    cp "${SRC}/qwen_app/${file}" "${BACKEND_DIR}/${file}"
done
cp "${SRC}"/qwen_app/queen_python_skills/*.py "${BACKEND_DIR}/queen_python_skills/"
cp "${SRC}/version.json" "${HOME_DIR}/version.json"
cp "${SRC}/queen-backend" "${HOME_DIR}/queen-backend"
chmod +x "${HOME_DIR}/queen-backend"

echo "Queen's Python runtime is installed in ${HOME_DIR}."
