# plan9-agent

A minimal LLM coding agent written in `rc`, the Plan 9 shell — running on
[9front](http://9front.org). It's small enough to read in one sitting, and it
exists to demonstrate one idea:

> On Plan 9, an agent is "just a loop," **and** the OS hands you the dangerous
> part — sandboxing — for free, via per-process namespaces. The thing Linux
> reinvented as containers is native here.

## How it works

The whole agent is the loop in [`agent.rc`](agent.rc):

1. Send the task + a short system prompt to a chat-completions API (any
   OpenAI-compatible endpoint; developed against a local
   [Ollama](https://ollama.com) box running `qwen2.5:3b`).
2. The model replies. To run a command it emits `<cmd>COMMAND</cmd>` and nothing
   else — a plain text convention, no JSON tool-use needed.
3. The harness runs that command inside `@{ ... }` (an rc block with its **own
   copy of the namespace**), captures the output, and feeds it back.
4. Loop until the model answers with no `<cmd>` tag.

The model only *decides*; the harness *acts* — by `fork`/`exec`, the same way a
shell has run programs since 1979. The only place JSON shows up is at the API
boundary, and even there we lean on a few lines of `awk`/`sed` instead of a
library.

## Why Plan 9

- **Everything is a file**, so the agent reaches the whole machine with one
  interface (`read`/`write`) — no per-capability API.
- **Namespaces are per-process and native.** `@{ ... }` gives a command a private
  view of the filesystem. Want the agent off the network? Don't bind `/net` into
  its namespace and it *cannot* reach it — enforced by the kernel, not by a
  permission prompt. (The sandboxing in this v1 is structural scaffolding;
  tightening the namespace is the next step.)

## Files

- `agent.rc` — the agent loop.
- `ask.rc` — a one-shot probe: send one prompt, print the raw response.
- `devserver.py` — a tiny Mac-side bridge used during development: serves scripts
  to the VM over HTTP and catches output the VM sends back (handy when your dev
  machine and your Plan 9 box are different computers).

## Status

Early. It runs commands and loops. Robust JSON handling, real namespace
restriction, and multi-tool support are all TODO.

## License

MIT
