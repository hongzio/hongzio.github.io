# queue — Queued Questions

Per-agent-session queue of pending questions for herdr. While an agent is
busy working you often think of the *next* thing to ask; type it into the
composer, hit **prefix+u**, and it is whisked into that agent's queue and the
composer is cleared so the draft never gets accidentally submitted mid-turn.
Hit prefix+u again (empty composer) to open the queue popup and feed a
question back in.

## Keys

- `prefix+u` — capture the focused agent's composer draft into its queue
  (no-op capture if the composer is empty), then open the popup.

In the popup:

- `enter` — put the selected question into the agent's composer (**not**
  submitted; you still press enter yourself) and close. The item leaves the
  queue.
- `e` — edit the selected question inline (enter saves, esc cancels).
- `d` / `x` — delete the selected question.
- `esc` / `q` — close.
- `j`/`k` or arrows — move.

## Persistence

Queues live in the plugin state dir as `queue-<agent-session-id>.json`, keyed
by herdr's `agent_session.value` (the Claude session UUID). That id is stable
across herdr server restarts and `claude --resume`, so a resumed agent picks
its queue back up wherever it reopens.

## How capture works (and its limits)

herdr has no "read the composer" API, so the draft is scraped from the
detection buffer: the text between the composer's two full-width `─` rules,
`❯` prefix stripped. Verified against Claude Code idle and working states
(working renders `❯` + no-break space). Clearing sends backspaces with
deliberate overshoot — extra backspaces on an empty composer are a no-op, and
unlike `esc` they never interrupt a working agent.

Caveats:

- Soft wraps and hard newlines render identically, so a multi-row draft is
  saved with rows joined by single spaces.
- `[Pasted text #N +M lines]` placeholders are captured literally, not the
  pasted content.
- A draft long enough to scroll inside the composer captures only the visible
  rows.
- Capture is Claude-only for now (`agent == "claude"`); other agent kinds
  still get the popup, minus draft capture.
- Assumes the cursor sits at the end of the draft (where typing leaves it);
  backspace-clearing leaves anything right of the cursor.

## Tests

    /usr/bin/python3 -m unittest discover scripts/herdr-queue

(The system python — plugin hooks run under it, so the code stays
stdlib-only and 3.9-compatible.)
