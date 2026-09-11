> Hosted access is now deployed. See DEPLOYMENT.md for current URLs and double-click open-hosted.bat to open your private dashboard without entering a code. The earlier manual deployment guide below is retained for rebuilding the service; its initial invite-entry UI instructions are superseded by private links.

# Assignment Lab

Validation: 25 automated tests passed, including the full dashboard workflow. Live provider calls are pending credentials.

A local and hosted-ready browser-agent MVP: read text and graphs, ask MiniMax, enter its answer, verify the field, and click Next. Includes a dashboard, invite access, isolated browsers, records, CSV, and a practice assignment.

## Start here (Windows)

1. If setup has not been run, install Python 3.12+ from https://www.python.org/downloads/. Check Add Python to PATH in the installer. Double-click setup.bat and wait for Ready.
2. Double-click start.bat. Keep its window open.
3. Open http://127.0.0.1:8010 in Chrome.
4. Enter LOCAL-DEMO as the invite code. This only works in development mode with no configured invite codes.
5. Choose Practice - no AI. Optionally enable auto-submit. Click Open browser session, then Start / Resume.
6. Watch the separate browser complete four questions, including a graph. Download CSV records. Close the session when done.

Practice simulation uses predetermined answers. It measures browser operations, NOT model accuracy, and makes no model calls. Cloud browsers still incur Browserbase fees even in simulation mode.

## Add your OpenRouter key

Open .env with Notepad (copy .env.example if needed). Paste your key after OPENROUTER_API_KEY=. Save and restart start.bat. Never put the key in the dashboard or a public repository.

Choose Practice - MiniMax answers, click Refresh models, and select a MiniMax model marked vision. IDs come from OpenRouter's live registry. You may save the selected ID as OPENROUTER_MODEL in .env for convenience. Start a new session to make real calls and see real costs.

The app requests usage.include=true. Missing cost is unconfirmed, never silently zero. Invite limits count across sessions. A cost threshold can be exceeded by one call because its final tokens are unknown in advance. Use provider account spending limits for an absolute financial backstop. Browserbase and hosting fees are separate.

## Real assignment sites

No specific LMS has been validated yet. Choose one site first. This build supports one visible question at a time, native radio choices, role=radio choices, and a single text/numeric input. Interactive graph editors, drag/drop, and multiple-answer questions need additional adapters.

Set ALLOWED_ASSIGNMENT_HOSTS to comma-separated assignment, login and resource domains (without https://). Only HTTPS public domains are allowed. Private-network targets are blocked.

Choose Real assignment and enter its URL. Under Website controls, a developer maps CSS selectors:

- question: exactly one visible region containing the full question, passage, graph, and answer controls.
- choices: radio controls inside the region; empty for free response.
- answer: one text/numeric field inside the region.
- next: the Next button in the question's frame.
- submit: the final Submit button, distinct from Next.
- complete: a visible submission-success marker.

Use Inspect question before Start to see the exact question text and graph screenshot without making a model call. Updating controls and inspecting again applies the mapping to the session.

Log in manually inside the opened browser. It does not inherit your existing Chrome cookies. If login opens a new tab, click Refresh tabs and select it. Only the selected question region and its screenshot go to the model when Start is pressed. Login fields are not automatically sent.

Stop cancels further actions, but already-sent requests may still be billed. Resume avoids re-solving verified questions in the current session. Field verification does NOT establish academic correctness. Failed/ambiguous actions pause visibly rather than silently skipping questions. Auto-submit is off by default; when enabled the app looks for an explicit completion marker. An unconfirmed submission must be inspected manually.

## Host for friends: Railway + Vercel + Browserbase

These files prepare the app for hosting; they do not create cloud accounts or automatically publish it. You need your own accounts and provider credentials.

### 1. Source repository

Create a private GitHub repository with these source files. Exclude .env, .venv, data, and caches; .gitignore already covers them.

### 2. Browserbase

Create a project at https://www.browserbase.com/. Obtain its API key and project ID. Put these in Railway's private Variables screen, never in frontend files. Each tester gets a fresh remote browser and an interactive live view. Treat live-view links as private session-access links.

### 3. Railway backend

At https://railway.com/ create a service from your repository. Set the root directory to this app if the repository contains other projects. railway.json installs requirements and runs python app.py. Use ONE service replica and ONE worker; browser objects and login tokens live in process memory.

Add a persistent volume mounted at /data. Set service variables:

```
APP_ENV=production
BROWSER_MODE=cloud
BROWSERBASE_API_KEY=<private key>
BROWSERBASE_PROJECT_ID=<project id>
OPENROUTER_API_KEY=<private key>
OPENROUTER_MODEL=<live vision-capable MiniMax id, optional if selected in UI>
INVITE_CODES=<random code for friend 1>,<different random code for friend 2>
DATA_DIR=/data
FRONTEND_ORIGIN=https://your-project.vercel.app
MAX_ACTIVE_SESSIONS=3
SESSION_MINUTES=20
MAX_CALLS_PER_INVITE=100
MAX_COST_PER_INVITE=2
ALLOWED_ASSIGNMENT_HOSTS=<assignment/login/resource domains>
```

Railway supplies PORT. Generate a Railway HTTPS domain. Visit its /api/health and check for ok:true. Local mode binds only 127.0.0.1; production binds the interface required by Railway. Chromium installation is not needed on Railway in cloud mode: Playwright connects to Browserbase remotely.

### 4. Vercel dashboard

Set window.AGENT_API_BASE in frontend/config.js to your Railway HTTPS URL, with no trailing slash. This public URL is not a credential.

Import the repository in https://vercel.com/:

- Root directory: frontend (or assignment-agent/frontend if nested).
- Framework: Other.
- Build command: empty.
- Output directory: .

The frontend/vercel.json file handles static asset paths. No npm build is needed. Set Railway FRONTEND_ORIGIN to the exact Vercel origin and redeploy after changing variables.

### 5. Validate before sharing

Run cloud Practice - no AI first. Check live view, all four answers, submit, CSV and Close. Then run Practice - MiniMax answers and confirm actual costs. Sign in as a second tester in another browser and verify histories are isolated. Test the first actual assignment website, including login, before inviting friends. Some school SSO systems may reject a cloud browser; that needs real-site testing.

A Vercel page cannot operate a friend's existing assignment tab. They use the separate cloud browser displayed inside your page.

## Tests

Double-click test.bat, or open a terminal in this folder and run:

```
.venv\Scripts\python.exe -m pytest -q
```

The tests use fake API responses, temporary databases, and real headless Chromium. They spend no API credits. setup.bat installs Chromium. Coverage includes parsing, retries, request cost wiring, key safety, invite isolation, usage limits, screenshots, entering answers, navigation, optional submission and cancellation. A mocked billing test is not proof of real provider billing; real OpenRouter and Browserbase checks need your credentials.

## Troubleshooting

- Missing key/model: set backend variables, restart, refresh models, choose image support.
- Backend unreachable: check start.bat, frontend/config.js, Railway health and exact FRONTEND_ORIGIN.
- Browser unavailable: run setup.bat locally; check Browserbase key, project, credits and concurrency in cloud mode.
- Unconfirmed cost: check OpenRouter usage. The invite pauses further model calls after an uncertain response or cancellation. Operator can reconcile with python manage.py reconcile, using provider evidence.
- Limit reached: operator can review usage with python manage.py usage. To grant a fresh allowance, issue a new private invite code after reviewing spend.
- No question or Next found: correct the site's adapter or log in. Unsupported work is not silently skipped.
- Browserbase release unconfirmed: end the session in Browserbase. Its provider timeout remains active.
- Restart/deploy: testers sign in and open a new browser. Records remain on the persistent volume; active browser sessions do not resume.

## Files

app.py: API, invite access, ownership and sessions.
browser.py: local/cloud browser lifecycle.
runner.py: workflow, progress, cancellation.
adapters.py: extraction and browser actions.
solver.py: MiniMax requests, parsing and actual usage.
store.py: records and per-invite usage ledger.
frontend/: dashboard, configuration and practice assignment.

This is an early friend-testing build. Payments, subscriptions and an extension are outside its scope.
