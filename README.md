# Queen

This repository contains Queen's macOS app and local Python runtime. The app owns
`127.0.0.1:8765`; it starts the Python API/skills backend on `127.0.0.1:8766` and
proxies CAPI and Auto Update routes to it.

## Runtime model

- Recognized commands run as deterministic Python skills in
  `qwen_app/queen_python_skills/`, without a model call. The provider-independent
  Ableton skill controls Live through guarded AbletonOSC actions.
- Unmatched CAPI prompts use the selected external provider. The runtime has no
  internal Groq chat or key manager.
- The standalone runtime exposes CAPI, the Python skill catalog, and the
  supervised Auto Update flow. Unconverted legacy routes are not registered.
- State is stored under `~/.queen`. On first runtime start, selected CAPI and
  Google/Anthropic updater state is copied from `~/.groq`; legacy model keys and
  the old directory are not copied or deleted.

The current Python skill catalog contains `list-skills`, `current-folder`, and
`ableton-control`. Ableton actions are available through `GET /api/ableton/capabilities`,
`POST /api/ableton/action`, or explicit `ABLETON:`
commands in CAPI. Android-emulator actions, including timestamp-named audio
recording, have not yet been converted into Python skills.

## Build and validate

The macOS app is built and packaged by GitHub Actions. Local offline checks:

```sh
python3 qwen_app/test_queen_backend.py
python3 qwen_app/test_capi_features.py
python3 qwen_app/test_pair_chat.py
mac_app/test.sh
```

Install the Python runtime with `./install.sh`. The app release installer is
`mac_app/install.sh vN`.

See [TAKEOVER.md](./TAKEOVER.md) for runtime details and outstanding work,
[LESSONS.md](./LESSONS.md) for operational lessons, and
[CAPI_PYTHON_API.md](./CAPI_PYTHON_API.md) for the CAPI interface.
