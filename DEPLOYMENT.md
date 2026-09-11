# Hosted Assignment Lab

Dashboard: https://frontend-topaz-iota-25.vercel.app
Backend: https://positive-tranquility-production-9fdc.up.railway.app
Health: https://positive-tranquility-production-9fdc.up.railway.app/api/health
Railway project: proud-transformation
Service: positive-tranquility

The backend is deployed with persistent storage and private provider credentials. The Browserbase project ID has been corrected to match the API key. MiniMax M3 uses the API ID minimax/minimax-m3.

## Open without typing a code

Double-click open-hosted.bat on this computer. It uses your existing Railway sign-in to create a private eight-hour access link and opens the hosted dashboard. Provider keys and access tokens are never printed. The link is also saved in data/hosted-access.html. After a backend restart, run the launcher again. Keep owner links private.

Public access is now enabled. Anyone loading the dashboard is issued their own guest identity by POST /api/guest, so no invite code is needed for browser runs. Invite links still work and are unaffected.

The ETH button in the top right arms browser control. Red means off and the session controls are disabled; clicking it turns it green and enables them. The choice is remembered per browser. It is a convenience switch that prevents an accidental paid session, not a security boundary -- the limits below are what actually bound usage.

Guardrails on public access:
- New guest identities: 10 per IP per 5 minutes, 200 globally.
- New sessions: 6 per IP per 10 minutes, 60 globally.
- Three concurrent browser sessions total, matching the Browserbase limit; one active session per visitor.
- Twenty-minute session ceiling, unchanged.
- Spend caps (MAX_CALLS_PER_INVITE, MAX_COST_PER_INVITE) apply to guests per network, not per token, so clearing storage for a new token does not reset the allowance.
- Private and internal addresses stay blocked, and plain http is refused.

## Deploy updates

The backend source-only upload directory is deploy-source. Refresh its application files before uploading; do not copy .env, data, logs or credentials into it. Railway's service start command is python app.py, its health check is /api/health, and /data is mounted for SQLite. Use one replica.

The frontend is deployed from frontend using vercel deploy --prod. Its config.js points to Railway and automatically uses the local backend on localhost.

## Validation

25 automated tests passed. A real Browserbase practice session completed four questions, verified all four entries, confirmed submission and closed. Simulation answers are fixtures, not an AI accuracy result.

### Hosted end-to-end run, 2026-09-10

The first real practice_ai run against the deployed stack succeeded. MiniMax M3 answered four questions through the hosted backend and a Browserbase cloud browser; every answer was entered and read back from the page. Total cost $0.00058, about 2 seconds per question. The session halted at review rather than submitting, which is correct with auto-submit off.

    Q1  2 + 2                     -> 4                 confidence 100
    Q2  demand shift D1 to D2      -> Price increases   confidence 98
    Q3  f(x) = x^2, f'(3)          -> 6                 confidence 100
    Q4  mean of 8, 10, 12          -> 10                confidence 100

Note that "verified" means the value was read back off the page, not that it is the right answer. Correctness above was checked by hand.

The Vercel to Railway wiring was confirmed from a real browser on the deployed dashboard: config.js resolves to the Railway host, the CORS preflight on /api/login returns the Vercel origin, and a cross-origin fetch of /api/health from the deployed page returns 200. No change was needed.

## Before a live coursework run

Two things still block mode=live. Neither is a deployment problem.

1. Resolved on 2026-09-10. ALLOWED_ASSIGNMENT_HOSTS is set to * on Railway, which permits any public https website. Verified: a live session against example.com is accepted, 127.0.0.1 is refused as a private address, and plain http is refused.
2. Still open. The default selectors in adapters.py target the practice fixture's data-agent-* attributes. A real assignment page needs its own question, choices, answer, next, submit and complete selectors. Use POST /api/sessions/{id}/inspect against the live page to capture them before running.

Live mode will now open any site, but it cannot read questions from one until its selectors are mapped.
