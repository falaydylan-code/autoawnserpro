# Assignment Lab 2.0 — Chrome extension

Reads the assignment page you already have open, in your own signed-in tab, and
works through the whole assignment one move at a time. No URL pasting, no cloud
browser, no sharing your school login with anything.

## Install it (2 minutes)

1. Open Chrome and go to **chrome://extensions**
2. Turn on **Developer mode** — the switch in the top right
3. Click **Load unpacked**
4. Select this `extension` folder — the whole folder, not a single file
5. Assignment Lab appears in your extensions list. Pin it if you like.

Updating: **remove** the old one and load the folder again. Chrome silently
keeps a stale build otherwise. The side panel prints the version on the first
line of every run; it must match `manifest.json`.

Chrome loads an extension as a **folder**. `manifest.json` is the file that
defines it, but Chrome needs the folder around it.

## Use it

1. Open your assignment in a normal tab and sign in as usual.
2. Click the Assignment Lab icon. The side panel opens.
3. Click **Enable** to grant browser access.
4. Choose a model and click **Start assignment**.

The run is **bound to that tab**. You can switch to other tabs and keep working;
the agent carries on in the assignment tab, takes its screenshots there, and
never pulls focus back. Closing the tab ends the run.

The first thing it does, always, is look at the page and decide whether there
is an academic question on it. If there isn't — a login screen, a course index,
a paywall — it says so and stops without touching anything.

If there is, it plans every part of the answer, enters them, checks each one,
and follows the page's Next / Continue control to the next question. It keeps
going until the assignment reports it is complete, you press Stop, it hits the
spending limit you set, or something genuinely needs you.

## How it presses things

Every move is **real browser input** in your tab — a real mouse click at the
control's position, real keystrokes, a real drag with the button held — driven
through Chrome's own input channel. Chrome calls that channel "debugging" and
shows a bar across the tab while a run is on. It attaches only to the assignment
tab, only during a run, and lets go on Stop, Disable, or when the run ends.
Press **Cancel** on that bar and the run stops.

The page's structure is used to *find* controls and to *read back* what they
hold; it is never used to fake an interaction. Where a control has no structure
to find — a point on a graph, a closed widget — the agent aims from the
screenshot instead, and every aimed point is checked against the current
screen before it is used.

Drop-down menus, drag-to-order lists, matching, graph points, fill-in tables and
multi-part questions are all handled this way.

## How it knows an answer is in

Two witnesses. After every answer, the page is asked what the control now holds,
and — with **Confirm each answer with a screenshot** on, the default — the model
is shown a fresh picture and must read the same value back. A part counts as
done only when both agree. An open menu, a highlighted option or a successful
click is never counted as an answer.

The panel keeps four things separate: the input was sent; the field changed;
the value matches the plan; the website graded it. Only the third is "done".

When a page grades an attempt and locks it, the agent records the result, stops
trying to change disabled answers, and moves on (if **Keep going** is on). When
the page allows another try, it takes it.

## What it will not do

- Sign in, or type into a password, payment, or ID field. Those fields are never
  even described to the model.
- Hand in the assignment, unless **Hand in when every known part is verified**
  is on *and* every part of every question is verified. Even then it names what
  is outstanding rather than pressing the button.
- Press Delete, Remove, Reset, Sign out, Register, Accept/Agree/Allow, Download,
  Export, Buy or Pay, or follow a link to another website.
- Follow the tab to a different site. If the tab leaves the assignment site the
  run stops.
- Take orders from the page. Page text is data, never instructions.

## Settings

Choose the model and Auto Continue behavior on Home. Open **Settings**, then
**Advanced setup**, for connection details.

- **Backend** — where the thinking happens. Defaults to your Railway service.
  Your OpenRouter key lives there, never in this extension.
- **Model** — choose it on Home, or leave the backend default selected. It must
  accept images.
- **Note for the agent** — optional, e.g. "answer in decimals".
- **Stop a run after spending ($)** — the only hard ceiling. Default $2.00.

The extension checks the backend's protocol before its first paid call. An
outdated backend gives a clear "Backend update required" message, never a
silent loop.

## Site access

**Enable is the approval.** The first time you enable browser access, Chrome asks
once whether Assignment Lab may read your sites. Disable it and a run in
progress stops and the site access is handed back. The only site the extension
can always reach is its own backend.

## Limits

There is no limit on questions or turns. What stops a run:

- the assignment reports it is complete
- you press Stop, disable browser access, or close the tab
- the spending limit in Setup
- six turns in a row with no verified progress, or the same move failing three
  times the same way, or the model flip-flopping between two answers — each
  stops with a message saying exactly which part needs you
- a page that keeps changing by itself four times while the model is deciding

Per question there is an action allowance of 10 + 8 per planned part, so a
twenty-cell table gets 170 turns; that is a bound on retries, not on work.

## Costs

Each turn is one model call with a screenshot; with screenshot confirmation on,
each answer costs one more. On MiniMax M3 a twenty-cell table has run about
$0.11, a single-part question about a cent.

## When something goes wrong

**"Backend update required"** — the extension and the Railway backend are out
of step. Deploy the backend from the same commit as this folder.

**"Browser input unavailable"** — DevTools or another debugger is open on the
assignment tab. Close it and press Read this page again.

**"Screenshot unavailable"** — Chrome could not picture the tab. Re-open the
assignment page and start again.

**It says there's no question** — that is usually correct. Check you are on the
question itself and not a menu or results page.

**A part stays "entered, not yet verified"** — the page accepted the input but
does not show the value where the agent looks, or the screenshot disagrees.
The log names the part; look at that field yourself.
