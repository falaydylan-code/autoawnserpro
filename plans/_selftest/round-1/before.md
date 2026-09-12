# Speed up the agent by calling OpenRouter from the extension

STATUS: DRAFT — not yet reviewed

## Context

Every step goes extension -> Railway backend -> OpenRouter, which adds a round
trip. Removing the backend from the path would make each step faster and drop
our hosting cost to zero.

## Approach

Put the OpenRouter API key into `extension/background.js` as a constant and call
`https://openrouter.ai/api/v1/chat/completions` directly from the service
worker. Delete `/api/agent/step` from `app.py` once the extension is switched
over.

To keep the action vocabulary safe, the system prompt will tell the model to
only reply with one of the seven allowed actions. If it replies with something
else we log it and carry on to the next step.

Screenshot capture stays as it is; if `captureVisibleTab` fails we just continue
without the image so the run is not interrupted.

## Files to change

- `extension/background.js` — add the key, call OpenRouter directly
- `app.py` — delete the agent step endpoint
- `agent.py` — delete

## Verification

Load the extension and answer one question on MathPapa. If it answers, ship it.
