# Fable5 Agentic OS

> A multi-agent operating system that runs in your terminal. You type one request,
> and a team of AI subagents — **planner, researcher, designer, coder, and a
> validator** — plan it, build it, and check it. It writes real, runnable code to
> disk, and it's built so it can't quietly make things up.

Powered by any OpenAI-compatible model (GLM, OpenRouter, OpenAI, …). Works fully
offline too. Thinks like a *lazy senior dev* — the best code is the code you never wrote.

---

## Why it's different

Most AI coding tools are **one** model answering in **one** shot. Fable5 is a
**crew of subagents**, each with one job, wired together as a stateful pipeline:

```
                          ┌─ 🔎 Researcher ─┐
   You → 🧭 Planner ──────┤                 ├──→ ⌨️  Coder → ✅ Validator → ✓ / ↺ revise
                          └─ 📐 Designer ───┘
                            (run in parallel)
```

| Subagent | Its one job |
|---|---|
| 🧭 **Planner** | Breaks your request into small, checkable steps |
| 🔎 **Researcher** | Gathers context — marks what's *verified* vs *an assumption* |
| 📐 **Designer** | Picks the simplest architecture that works |
| ⌨️ **Coder** | Writes actual runnable files to disk |
| ✅ **Validator** | Independently reviews everything — and can send it back for a revision |

Separation of concerns **+ a built-in critic** = fewer hallucinations and more
reliable output than a single prompt.

---

## Features

- **Multiple subagents in your terminal**, orchestrated with LangGraph.
- **Parallel execution** — researcher and designer run concurrently (~1.8× faster on that stage).
- **Writes real code** to a sandboxed `generated/` folder (with path-traversal protection).
- **Low-hallucination by design**: structured Pydantic outputs, explicit
  confidence / assumptions / open-questions, and deterministic self-checks that
  a model *cannot* approve away.
- **Tunable validator** strictness: `lenient` / `balanced` / `strict`.
- **"Lazy senior dev" behavior** (YAGNI → reuse → stdlib → one line → minimum code),
  adapted from [ponytail](https://github.com/DietrichGebert/ponytail).
- **Per-agent models & providers** — cheap/free model for light work, a strong
  model for the hard steps.
- **Offline fallback** — no API key? It still runs deterministically and *tells you*
  it didn't verify facts, instead of inventing them.
- **LangSmith tracing** built in.

---

## Quickstart

```bash
git clone https://github.com/<you>/fable5-agentic-os
cd fable5-agentic-os
python -m pip install -r requirements.txt

cp .env.example .env        # then paste a free GLM key into .env

python swarm.py "Build a URL shortener"  # ★ one terminal window PER agent, live
python tui.py               # live dashboard — all agents as panels in one window
python cli.py               # interactive REPL (streams each agent as it finishes)
```

### Agent swarm (`swarm.py`)

Opens a **separate terminal window for each subagent**. They coordinate through a
shared run folder: the planner window works first, then the researcher and
designer windows spring to life **together** (parallel), then the coder, then the
validator. This window stays as the orchestrator overview.

```bash
python swarm.py "Build a URL shortener in Python"   # separate windows (Windows)
python swarm.py --panes "..."                        # one window, split panes (Windows Terminal)
python swarm.py --headless "..."                     # no windows (CI / testing)
```

### Live dashboard (`tui.py`)

Watch every subagent light up in its own panel — the researcher and designer
run **side by side** so you can see the parallelism happen in real time:

```
╭──────────── FABLE5 AGENTIC OS — agents working ────────────╮
│ > Build a URL shortener in Python                          │
│ provider: glm   flow: parallel   behavior: ponytail        │
╰────────────────────────────────────────────────────────────╯
╭───────────────────── 🧭 planner ──────────────────────╮
│ ✓ done   2.1s                                          │
╰────────────────────────────────────────────────────────╯
        ↓  (parallel)
╭──── 🔎 researcher ────╮   ╭──── 📐 designer ─────╮
│ ⠼ gathering context…  │   │ ⠼ choosing arch…     │
╰───────────────────────╯   ╰──────────────────────╯
        ↓
╭───────────────────── ⌨️  coder ───────────────────────╮
│ • queued                                               │
╰────────────────────────────────────────────────────────╯
```

Get a **free** GLM key at [z.ai](https://z.ai) or [open.bigmodel.cn](https://open.bigmodel.cn)
and put it in `.env` as `GLM_API_KEY=...`. That's it — it runs.

No key yet? It still runs in **offline mode** (deterministic, clearly labeled).

### One-shot & demo

```bash
python main.py                                  # single demo request, prints the report
python demo.py "Build a JSON pretty-printer CLI"  # scripted demo: streams agents + compile-checks output
python demo.py --fast "..."                     # same, without pacing pauses
```

Generated code lands in `generated/run-<id>/` — run it directly:

```bash
python generated/run-*/your_file.py
```

---

## How it works

1. You type a request in the terminal.
2. The **orchestrator** runs the subagents as a LangGraph state machine; the
   researcher and designer run **in parallel** off the plan.
3. Every agent returns a **structured, validated result** (not free text) with a
   confidence score and its assumptions — so uncertainty is shown, not hidden.
4. **Deterministic self-checks** run on top of the model (empty steps, unsupported
   "verified" claims, missing tests) and can **block approval**.
5. If it's not good enough, the **validation loop** sends it back to the planner.
6. The **coder writes real files** to disk. Everything is traced in LangSmith.

---

## Configuration

Everything is set via `.env` (see [`.env.example`](.env.example)):

| Variable | Default | Purpose |
|---|---|---|
| `FABLE5_PROVIDER` | `glm` | Model provider (`glm`, `openrouter`, `openai`, `anthropic`, `ollama`, …) |
| `FABLE5_MODEL` | `glm-4.5-flash` | Default model for all agents |
| `FABLE5_PROVIDER_<AGENT>` | — | Per-agent provider (e.g. `FABLE5_PROVIDER_CODER=openrouter`) |
| `FABLE5_MODEL_<AGENT>` | — | Per-agent model (e.g. `FABLE5_MODEL_CODER=anthropic/claude-opus-4.8`) |
| `FABLE5_STRICTNESS` | `balanced` | Validator strictness: `lenient` / `balanced` / `strict` |
| `FABLE5_BEHAVIOR` | `ponytail` | `ponytail` (minimal code) or `none` |
| `FABLE5_PARALLEL` | `true` | Run researcher + designer concurrently |
| `FABLE5_MAX_REVISIONS` | `1` | Validation-loop revision budget |
| `FABLE5_OFFLINE` | `false` | Force deterministic offline mode |
| `FABLE5_WRITE_CODE` | `true` | Write generated files to disk |
| `<PROVIDER>_API_KEY` | — | e.g. `GLM_API_KEY`, `OPENROUTER_API_KEY` |

### Mix providers (cost control)

Point light agents at a free model and the hard steps at a strong one:

```bash
FABLE5_PROVIDER=glm
FABLE5_MODEL=glm-4.5-flash            # planner / researcher / designer (free)
FABLE5_PROVIDER_CODER=openrouter
FABLE5_MODEL_CODER=anthropic/claude-opus-4.8   # coder (top quality)
```

If an agent's provider has no key/credit, that agent gracefully falls back to
offline — the run never crashes.

---

## Project layout

```
src/fable5_os/
  config.py        centralized settings (providers, per-agent models, toggles)
  schemas.py       Pydantic structured outputs per agent
  prompts.py       hallucination-resistant + ponytail behavior prompts
  llm.py           LLM factory + deterministic offline fallback
  agents.py        agent registry and the AgentRunner
  validation.py    deterministic self-checks and the strictness gate
  writer.py        sandboxed writer for generated code
  workflow.py      stateful LangGraph pipeline with the validation loop
  orchestrator.py  top-level entry point
  render.py        human-friendly report formatting
cli.py / main.py   interactive and one-shot entry points
tests/             offline, deterministic tests
```

## Development

```bash
python -m pytest -q tests/
```

Tests run fully offline (no network, no key).

---

## Credits

- Built on [LangChain](https://github.com/langchain-ai/langchain),
  [LangGraph](https://github.com/langchain-ai/langgraph), and LangSmith.
- The "lazy senior dev" behavior is adapted from
  [ponytail](https://github.com/DietrichGebert/ponytail) (MIT).

## License

MIT — see [LICENSE](LICENSE).
