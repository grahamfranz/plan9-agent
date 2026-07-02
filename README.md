# plan9-agent

A minimal LLM coding agent written in `rc`, the Plan 9 shell — running on
[9front](http://9front.org). It's small enough to read in one sitting, and it
exists to demonstrate one idea:

> On Plan 9, an agent is "just a loop," **and** the OS hands you the dangerous
> part — sandboxing — for free, via per-process namespaces. The thing Linux
> reinvented as containers is native here.

## How it works

The whole agent is the loop in [`agent.rc`](agent.rc):

1. You type a task at the `agent>` prompt. The task plus a short system prompt
   and a Plan 9 cheat-sheet go to a chat-completions API (any OpenAI-compatible
   endpoint; developed against a local [Ollama](https://ollama.com) box, then
   Claude Haiku through a dev proxy).
2. The model replies with brief reasoning and **one** command inside a markdown
   code fence — a plain-text convention, no JSON tool-use needed.
3. The harness runs that command inside `@{ ... }` (an rc block with its **own
   copy of the namespace**) under a timeout, captures the output, and feeds the
   real result back.
4. Loop until the model replies with **no** code fence — that message is its
   answer (or a question) to you, and the `agent>` prompt returns.

The model only *decides*; the harness *acts* — by `fork`/`exec`, the same way a
shell has run programs since 1979. The only place JSON shows up is at the API
boundary, and even there we lean on a few lines of `awk`/`sed` instead of a
library.

## Why Plan 9

- **Everything is a file**, so the agent reaches the whole machine with one
  interface (`read`/`write`) — no per-capability API.
- **Namespaces are per-process and native.** Every command runs in its own
  forked namespace (`@{ ... }`), so the sandbox is real, not scaffolding: the
  paths in the policy file are bound to an empty dir (your home, by default), the
  working dir is pinned to `/tmp`, and the whole thing resets every command —
  enforced by the kernel, not by a permission prompt or by us inspecting the
  command string. Add `/net` to the policy and the agent literally *cannot* open
  a network connection, because on Plan 9 the network **is** `/net`.

## The sandbox

The policy is a plain file (`/tmp/agent.hide` by default), re-read before every
command, so you can edit it **live** from any window — no restart:

```
cat /tmp/agent.hide              # what's masked right now
echo /net >>/tmp/agent.hide      # take the agent offline on its next command
echo /sys/src >>/tmp/agent.hide  # ...and hide the OS source too
>/tmp/agent.hide                 # clear it: full access
```

Because the namespace is forked per command, the change lands on the very next
command, and a command can never corrupt the harness's own view. The policy path
is a single variable (`hidefile`) — point it at `/mnt/agent/hide` later and
nothing else changes.

## Running it

The agent reads **one task per line from stdin**, so it composes like any unix
filter — the "where do tasks come from" question lives outside the agent, not in
it:

```
r agent.rc                 # interactive: type tasks, ctrl-D or 'quit' to exit
echo 'build hello.c' | rc /tmp/agent.rc     # one-shot: run one task, exit at EOF
rc /tmp/agent.rc <tasks.txt                 # batch: one full task per line
```

Because it exits on EOF, you get a **daemon for free** — no daemon code in the
agent. Point its stdin at a fifo and have anything (another window, `cron`, an
`ssh` session) drop tasks in:

```
mkfifo /tmp/agent.in
rc /tmp/agent.rc </tmp/agent.in &      # blocks on the fifo, waiting for work
echo 'summarize /sys/src/cmd/cat.c' >/tmp/agent.in   # queue a task from anywhere
```

The knobs are plain variables, overridable the unix way (rc imports the
environment, so an assignment before the command wins). argv is left free because
stdin is the input:

```
model=claude-opus-4-8 steps=24 maxtok=8192 rc /tmp/agent.rc <tasks
```

- `model` — which Claude the proxy calls (`haiku` cheap, `opus` for hard tasks).
- `steps` — max model↔harness round-trips per task before it gives up (default 16).
- `maxtok` — max tokens per model reply, passed through to the proxy (default 4096).
- `keep` — how many recent messages to send each turn (bounds request size).

## Files

- `agent.rc` — the agent loop.
- `ask.rc` — a one-shot probe: send one prompt, print the raw response.
- `devserver.py` — a tiny Mac-side bridge used during development: serves scripts
  to the VM, proxies its API calls (adding TLS + auth), and catches output the VM
  sends back. Throwaway — a real install skips it.

## Status

Working. It's a stdin filter — interactive at a prompt, or fed by a pipe, a
file, or a fifo (a cron-able daemon with no daemon code). It runs each command in
a per-command namespace sandbox with a live-editable policy, composes its system
prompt from a `context/` directory, keeps conversation context across tasks, times
out hung commands, and launches graphical programs in their own window. It has
written, compiled, debugged, and run C programs from vague prompts.

Rough edges / next: the dev proxy (`devserver.py`) is throwaway — a real install
talks to a model directly (9front has TLS); large conversations still strain the
request path; and exposing the agent's whole control surface as a mounted file
tree (`/mnt/agent/…` via `ramfs` + `/srv`) is the natural follow-on to the
policy file.

## License

MIT
