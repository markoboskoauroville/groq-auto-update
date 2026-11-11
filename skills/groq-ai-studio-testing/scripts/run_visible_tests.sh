#!/usr/bin/env bash
# Visible Live Test Runner for Groq AI Studio ("Queen" / qwen)
# Opens macOS Terminal.app in front of the user's eyes so every command,
# server log, and test result is visible in real time, while capturing output
# to /tmp/queen_visible_test.log for the agent to verify synchronously.

set -euo pipefail

LOG_FILE="/tmp/queen_visible_test.log"
DONE_FILE="/tmp/queen_visible_test.done"
INNER_SCRIPT="/tmp/queen_visible_inner.sh"

rm -f "$LOG_FILE" "$DONE_FILE"

cat > "$INNER_SCRIPT" << 'EOF'
#!/usr/bin/env bash
LOG_FILE="/tmp/queen_visible_test.log"
DONE_FILE="/tmp/queen_visible_test.done"

exec > >(tee -a "$LOG_FILE") 2>&1

printf "\033[1;36m══════════════════════════════════════════════════════════════════════\033[0m\n"
printf "\033[1;32m  QUEEN (Groq AI Studio) — LIVE VISIBLE TERMINAL TEST RUN\033[0m\n"
printf "\033[1;36m══════════════════════════════════════════════════════════════════════\033[0m\n"

echo ""
printf "\033[1;33m$ cd ~/Developer/groq_ai_studio && ./install.sh\033[0m\n"
cd "$HOME/Developer/groq_ai_studio" && ./install.sh

echo ""
printf "\033[1;33m$ Restarting Queen server with latest code on port 8765...\033[0m\n"
pkill -f "qwen_app/app.py" 2>/dev/null || true
sleep 1
cd "$HOME/.groq"
nohup ./venv/bin/python -W ignore qwen_app/app.py 8765 < /dev/null > /tmp/qwen_server.log 2>&1 &
sleep 2

PORT=$(cat "$HOME/.groq/app_url" 2>/dev/null | grep -oE '[0-9]+$' || echo "8765")
BASE="http://127.0.0.1:${PORT}"

echo ""
printf "\033[1;36m$ curl -s %s/health\033[0m\n" "$BASE"
curl -s "$BASE/health"
echo ""

echo ""
printf "\033[1;36m$ curl -s -X POST %s/api/terminal/log (writing live banner to Queen server console)\033[0m\n" "$BASE"
curl -s -X POST "$BASE/api/terminal/log" \
  -H 'content-type: application/json' \
  -d '{"level":"cmd","message":"Running visible live test suite from macOS Terminal.app"}'
echo ""

echo ""
printf "\033[1;36m$ curl -s -X POST %s/api/test/live (executing Queen built-in live self-test backdoor)\033[0m\n" "$BASE"
LIVE_JSON=$(curl -s -X POST "$BASE/api/test/live")
echo "$LIVE_JSON" | python3 -c '
import sys, json
d = json.load(sys.stdin)
for r in d.get("results", []):
    mark = "\033[1;32m✓ PASS\033[0m" if r["ok"] else "\033[1;31m✗ FAIL\033[0m"
    cmd = r["command"]
    name = r["name"]
    detail = r["detail"]
    print(f"  {mark}  {cmd} -> {name} ({detail})")
print("")
color = "\033[1;32m" if d.get("ok") else "\033[1;31m"
passed = d.get("passed")
failed = d.get("failed")
ver = d.get("version")
print(f"{color}SUMMARY: {passed} passed, {failed} failed (version {ver})\033[0m")
sys.exit(0 if d.get("ok") else 1)
'
STATUS=$?

echo ""
printf "\033[1;36m$ curl -s -X POST %s/api/auto_update/keys/load-default (loading Dual-Kind APIs from ~/Downloads/API masked)\033[0m\n" "$BASE"
AU_LOAD=$(curl -s -X POST "$BASE/api/auto_update/keys/load-default")
echo "$AU_LOAD" | python3 -c '
import sys, json
d = json.load(sys.stdin)
f = d.get("found_totals", {})
au = d.get("auto_update", {})
provs = au.get("providers", {})
g_mask = (provs.get("google") or {}).get("active_key") or "none"
a_mask = (provs.get("anthropic") or {}).get("active_key") or "none"
scanned_n = len(d.get("scanned_files", []))
gq_n = f.get("groq", 0)
gg_n = f.get("google", 0)
an_n = f.get("anthropic", 0)
print(f"  \033[1;32m✓ Dual-Kind Loader:\033[0m Scanned {scanned_n} file(s) -> Groq={gq_n} | Google={gg_n} ({g_mask}) | Anthropic={an_n} ({a_mask})")
'

echo ""
printf "\033[1;36m$ curl -s -X POST %s/api/auto_update/run (live dry-run surgical patch + CI gate + USD cost receipt)\033[0m\n" "$BASE"
AU_RUN=$(curl -s -X POST "$BASE/api/auto_update/run" \
  -H 'content-type: application/json' \
  -d '{"instruction":"Add a subtle tooltip title attribute \"Flask Server Live\" on the .live-dot element inside #status-bar in index.html.","dry_run":true,"target_files":["index.html"]}')
echo "$AU_RUN" | python3 -c '
import sys, json
d = json.load(sys.stdin)
if d.get("ok"):
    c = d.get("cost", {})
    prov = d.get("provider")
    mod = d.get("model")
    el = d.get("elapsed_sec")
    summ = d.get("summary")
    f_usd = c.get("formatted_usd")
    in_t = c.get("input_tokens")
    out_t = c.get("output_tokens")
    print(f"  \033[1;32m✓ SURGICAL DRY-RUN PASSED\033[0m [{prov}/{mod}] in {el}s")
    print(f"  \033[1;37mSummary:\033[0m {summ}")
    print(f"  \033[1;33m💵 UPDATE COST IN USD: {f_usd} USD\033[0m ({in_t} in / {out_t} out tokens)")
else:
    err = d.get("error")
    print(f"  \033[1;33m⚠ Auto-update dry-run response:\033[0m {err}")
'

echo ""
printf "\033[1;36m$ curl -s -X POST %s/api/remote/send (asking Queen in live browser & terminal about her v4 Dual-Kind Auto-Update & Split-Screen Studio)\033[0m\n" "$BASE"
REMOTE_JSON=$(curl -s -X POST "$BASE/api/remote/send" \
  -H 'content-type: application/json' \
  -d '{"prompt":"In 2 concise sentences, confirm your v4 Dual-Kind API Loader (Groq vs Google/Anthropic) and your Learning-by-Watching Split-Screen Surgical Auto-Update pipeline with USD cost receipts."}')
echo "$REMOTE_JSON" | python3 -c '
import sys, json
d = json.load(sys.stdin)
if d.get("ok"):
    tele = d.get("telemetry", {})
    cost = tele.get("cost", 0)
    pt = tele.get("prompt_tokens", 0)
    ct = tele.get("completion_tokens", 0)
    print("\033[1;32mQueen replied:\033[0m")
    print(d.get("reply", ""))
    print(f"\033[90m  [Groq LPU Chat Cost: ${cost:.6f} USD | {pt} in / {ct} out]\033[0m")
else:
    print("\033[1;31mRemote send error:\033[0m", d.get("error"))
'

echo ""
printf "\033[1;35m─── Queen Server Console Output (/tmp/qwen_server.log) ───\033[0m\n"
tail -n 35 /tmp/qwen_server.log || true

echo "$STATUS" > "$DONE_FILE"
printf "\n\033[90m[Live test finished with exit code %s — window left open for your inspection]\033[0m\n" "$STATUS"
EOF

chmod +x "$INNER_SCRIPT"

if osascript -e 'tell application "Terminal"
    activate
    do script "bash /tmp/queen_visible_inner.sh"
end tell' >/dev/null 2>&1; then
  echo "Opened macOS Terminal.app visibly — waiting for live test completion..."
  for _ in $(seq 1 60); do
    if [[ -f "$DONE_FILE" ]]; then
      cat "$LOG_FILE"
      exit "$(cat "$DONE_FILE")"
    fi
    sleep 0.5
  done
  echo "Timed out waiting for visible Terminal run; partial log:"
  cat "$LOG_FILE" 2>/dev/null || true
  exit 1
else
  echo "Terminal.app AppleEvents unavailable; running directly via Queen live server backdoor..."
  bash "$INNER_SCRIPT"
  exit "$(cat "$DONE_FILE")"
fi
