# plan9-agent

A minimal LLM coding agent written in `rc`, the Plan 9 shell — running on
[9front](http://9front.org). It's small enough to read in one sitting, and it
exists to demonstrate one idea:

> On Plan 9, an agent is "just a loop," **and** the OS hands you the dangerous
> part — sandboxing — for free, via per-process namespaces. The thing Linux
> reinvented as containers is native here.

## How it works

The whole agent is the loop in [`agent.rc`](agent.rc):

1. The agent reads a task from stdin. The task plus a short system prompt and a
   Plan 9 cheat-sheet go to a chat-completions endpoint (any OpenAI-compatible
   API; developed against a local [Ollama](https://ollama.com) box, then Claude).
2. The model replies with brief reasoning and, to run something, **one** command
   inside a fenced block tagged `run` — a plain-text convention, no JSON tool-use
   needed. Ordinary code fences are treated as quoted text, so the model can show
   you code without it being executed.
3. The harness runs that command inside `@{ ... }` (an rc block with its **own
   copy of the namespace**) under a timeout, captures the output, and feeds the
   real result back.
4. Loop until the model replies with **no** `run` block — that message is its
   answer (or a question) to you, and control returns to stdin.

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

## Talking to a model

The agent speaks the OpenAI chat-completions shape to whatever endpoint you point
`url` at. There are two ways to reach one — and which you need depends entirely on
whether 9front can do the TLS.

**Direct (bridge-less) — pure Plan 9.** Set `direct=yes` and `url` to an endpoint
the VM can reach, and the agent POSTs straight from 9front with `hget` (the API
key, if any, read from `keyfile` — kept in `$home`, which the sandbox masks, so
the agent can't read its own key). Against a **local OpenAI-compatible server**
(Ollama, llama.cpp) over plain HTTP this needs *nothing else*: a completely
self-contained Plan 9 agent, no helper, no bridge.

**Via a TLS-terminating helper — for cloud providers.** 9front's TLS client is
older than the modern, CDN-fronted TLS that the big cloud APIs (OpenAI, Anthropic,
OpenRouter — all behind Cloudflare) require, so `hget` can't handshake them
directly *yet* (see Limitations). [`devserver.py`](devserver.py) bridges that gap:
the VM speaks plain HTTP to it, and it adds TLS + auth and forwards to any provider
(Anthropic-native, or any OpenAI-compatible endpoint with `PROVIDER=openai`). It's
a ~90-line stdlib Python script — written for a Mac during development, but run it
on **any** always-on box the VM can reach (VPS, Raspberry Pi, router). Handing the
modern-protocol work to a small service is idiomatic Plan 9, not a wart.

> **Local model → pure Plan 9, no helper. Cloud model → a small HTTP-to-TLS
> helper, until 9front's own TLS catches up.**

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

The knobs are plain rc variables. Set them on their own lines first — rc exports
its variables to the child process, so the agent inherits them (don't put the
assignment on the right of a pipe; rc rejects that). argv is left free because
stdin is the input:

```
direct=yes
url=http://10.0.0.5:11434/v1/chat/completions   # e.g. a local Ollama
model=qwen2.5:3b
rc /tmp/agent.rc <tasks
```

- `url` — chat endpoint (a helper, or an endpoint the VM can reach directly).
- `direct` — `yes` to POST straight to `url` over HTTP(S); `no` (default) to go
  via the helper.
- `keyfile` — file holding the API key for direct mode (default `$home/.llmkey`,
  which the sandbox masks from the agent).
- `model` — the model id your endpoint serves (an Anthropic id via the helper, a
  local model name against Ollama, etc.).
- `steps` — max model↔harness round-trips per task before it gives up (default 16).
- `maxtok` — max tokens per model reply (default 4096).
- `keep` — how many recent messages to send each turn (bounds request size).

## Files

- `agent.rc` — the agent loop.
- `devserver.py` — the provider-agnostic TLS-terminating helper described above:
  serves scripts to the VM, adds TLS + auth to its API calls, and catches output
  the VM posts back. Needed only for cloud providers 9front can't TLS to
  directly; a local-model, direct-mode setup skips it entirely.

## Status

Working. It's a stdin filter — interactive at a prompt, or fed by a pipe, a file,
or a fifo (a cron-able daemon with no daemon code). It runs each command in a
per-command namespace sandbox with a live-editable policy, composes its system
prompt from a `context/` directory, keeps conversation context across tasks, times
out hung commands, and launches graphical programs in their own window. It has
written, compiled, debugged, and run C programs from vague prompts, and can talk
to a model either directly (local/HTTP) or through the TLS helper (cloud).

## Limitations & future directions

Known limits and ideas left on the table (notes for later):

- **Cloud TLS is the real wall.** 9front's `tlsclient` can't yet handshake
  CDN-fronted cloud APIs (Cloudflare-grade TLS), so cloud providers need the
  HTTP-to-TLS helper; only local/HTTP endpoints run fully bridge-less. Closing
  this *in 9front's own TLS stack* (SNI, modern ciphers/curves) is the clean path
  to a self-contained cloud-capable agent — and it would benefit every 9front
  networking tool, not just this one.
- **`/mnt/agent` mount.** Expose the whole control surface — `context/`,
  `history`, the sandbox policy — as one mounted file tree via `ramfs` + `/srv`,
  so those live under a single namespace-served directory instead of scattered
  `/tmp` paths.
- **`window PROG` sandbox hole.** Graphical programs launched with `window`
  inherit rio's namespace, escaping the per-command mask.
- **Approval gate.** Optional y/n confirmation before each command runs.

## License

MIT
