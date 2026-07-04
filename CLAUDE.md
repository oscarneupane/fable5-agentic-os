# Fable5 Agentic OS

This project is a Python-based multi-agent operating system concept built with LangChain, LangGraph, and LangSmith.

## Purpose
Build a reliable, low-hallucination multi-agent system where:
- Fable5 is the main orchestrator
- Planner, Researcher, Designer, and Coder are specialized agents
- The system should be practical, user-friendly, and efficient
- The architecture should favor correctness, traceability, and maintainability

## Current state
- Modular package under src/fable5_os with real LangGraph orchestration
- Agents call LangChain models (via init_chat_model) with forced structured output,
  and fall back to a deterministic, non-fabricating offline generator when no API
  key/provider is available — the system always runs and reports its mode
- Provider is configurable; GLM/Zhipu and OpenRouter are supported via the
  OpenAI-compatible path. Verified live against glm-4.5-flash.
- Per-agent provider AND model: light agents (planner/researcher/designer) and
  heavy agents (coder/validator) can each use a different provider+model via
  FABLE5_PROVIDER_<AGENT> / FABLE5_MODEL_<AGENT>. Enables cost mixing (e.g. GLM
  free for light work, OpenRouter/Opus for the hard steps). Missing keys/credit
  degrade that agent to offline, not a crash.
- Hallucination controls: grounding prompts, Pydantic schemas with explicit
  confidence/assumptions/open_questions, deterministic self-checks, and a
  validation loop that can request revisions
- The Coder generates REAL runnable files; they are written to a sandboxed
  output dir (generated/run-<id>/) with path-traversal protection
- Validator strictness is tunable (FABLE5_STRICTNESS = lenient|balanced|strict);
  balanced (default) only revises on high-severity/blocking issues
- Agent behavior layer (FABLE5_BEHAVIOR = ponytail|none): the "lazy senior dev"
  ladder (YAGNI -> reuse -> stdlib -> one line -> minimum code) is injected into
  the planner/designer/coder/validator prompts. Adapted from
  https://github.com/DietrichGebert/ponytail (MIT).
- Stateful workflow with a MemorySaver checkpointer and LangSmith tracing hook
- User-friendly CLI + one-shot main.py with a formatted report (UTF-8 safe)
- 11 tests passing (offline, deterministic — no network)

## Key files
- src/fable5_os/config.py: centralized settings (provider, model, offline, tracing)
- src/fable5_os/schemas.py: Pydantic output schemas per agent
- src/fable5_os/prompts.py: hallucination-resistant system prompts
- src/fable5_os/llm.py: LLM factory + deterministic offline fallback
- src/fable5_os/agents.py: agent registry and AgentRunner (live/offline execution)
- src/fable5_os/validation.py: deterministic self-checks, invariants, strictness gate
- src/fable5_os/writer.py: sandboxed writer for generated code files
- src/fable5_os/workflow.py: stateful LangGraph workflow with validation loop
- src/fable5_os/orchestrator.py: main orchestration logic / entry point
- src/fable5_os/render.py: human-friendly report formatting
- src/fable5_os/langchain_bridge.py: backwards-compatible adapter (delegates to llm/config)
- cli.py / main.py: interactive and one-shot entry points
- tests/: regression and smoke tests

## Next priorities
1. Add a real provider package to requirements and verify a live end-to-end run
2. Give the Researcher real tools (web/file search) so findings can be truly verified
3. Persist checkpoints to disk (SqliteSaver) so runs survive process restarts
4. Add streaming/step-by-step progress output to the CLI
5. Add a simple web or desktop UI later if needed

## Guidance for implementation
- Prefer small, clear steps over overly clever code
- Keep agent responsibilities distinct
- Validate outputs before finalizing them
- Make the system explain its reasoning and decisions
- Favor reliability over speed when the two conflict

## Run locally
- python -m pip install -r requirements.txt
- python cli.py
- python -m pytest -q tests/test_smoke.py tests/test_workflow.py
