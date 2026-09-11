# Architecture

Two halves that talk over HTTPS.

    Chrome extension  ->  FastAPI backend on Railway  ->  OpenRouter
    (reads the page,       (holds the API key,             (the model)
     performs actions)      meters spend, decides)

The extension never holds a provider key. Anything shipped to a browser is
readable by whoever installs it, so every model call goes through the backend.

## The agent loop

`extension/background.js` owns it and runs one step at a time:

1. **Observe** — screenshot the whole visible tab (`chrome.tabs.captureVisibleTab`)
   and gather interactive elements from every frame, renumbered into one global
   list with a private map back to the owning frame.
2. **Decide** — POST that to `/api/agent/step`. `agent.py` builds the prompt and
   returns exactly one action from a closed list.
3. **Act** — `extension/content.js` performs it and reads the result back.
4. **Settle** — poll the page until it visibly changes before the next
   screenshot, so each picture shows the *result* of the last action.

The screenshot is the source of truth for reading. The element index exists only
so the model has something to name when acting.

## Files worth reviewing closely

| file | what to look at |
|---|---|
| `agent.py` | the system prompt, the closed action vocabulary, `parse_action` validation |
| `app.py` | auth, throttles, `safe_url`, CORS, the `/api/agent/step` endpoint |
| `extension/content.js` | what is exposed to the model, what is refused in the page |
| `extension/background.js` | step and session caps, loop detection, origin checks |
| `store.py` | per-owner spend metering (`reserve_call` / `settle_call`) |

## Security model

Deliberately copied from Claude in Chrome.

- **Instructions come only from the system prompt.** Page text is fenced as
  `BEGIN UNTRUSTED PAGE TEXT` and is data, never commands.
- **The action vocabulary is closed** — `read_check`, `fill`, `click`, `select`,
  `scroll`, `done`, `give_up`. Anything else is rejected before execution, so a
  page cannot introduce a verb.
- **Credential and payment fields are never described to the model**, so it
  cannot be asked to fill one (`sensitive()` in `content.js`).
- **Controls that hand in an assignment are refused in the page itself**
  (`HANDS_IN` in `content.js`), not merely discouraged in the prompt.
- **Private and internal addresses are blocked** (`safe_url` in `app.py`), so
  the public endpoint cannot be aimed at the host's own network.
- **The run stops if the tab changes origin.**

Repeated lesson, worth keeping in mind while reviewing: prompt instructions are
suggestions, harness rules are rules. Anything that must not happen is enforced
in code, and the prompt only explains why.

## Known weak points

- The public dashboard has no authentication by design; spend is bounded by
  per-network caps rather than by identity.
- Guest identity is a random token; the spend budget is keyed to a hash of the
  client IP, which conflates users behind one NAT.
- The agentic path writes no server-side history, so runs cannot be audited
  after the fact.
- `frontend/` and `adapters.py` are the older selector-driven path, kept as a
  fallback. They are not on the extension's code path.

## Running it

    pip install -r requirements.txt
    pytest -q            # 44 tests, no network, no key needed
    python app.py        # serves on 127.0.0.1:8010

Load `extension/` unpacked at `chrome://extensions` with Developer mode on.
