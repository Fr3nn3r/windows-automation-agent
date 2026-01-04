# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Windows Automation Agent: An LLM-powered desktop automation system that interprets natural language commands and executes them using Windows system tools. Uses Groq's Llama models for near-instant response times.

**Core Architecture:** SOLID-compliant modular design
- **core/**: Core abstractions and implementations
  - `protocols.py`: Protocol definitions (LLMClient, DecisionMaker, ToolExecutor)
  - `brain.py`: LLM Router - maps intent to single tool
  - `router.py`: Atomic executor (no loops, no retries, fail fast)
  - `registry.py`: Stateless tool executor with ~26 registered tools
  - `context.py`: State-focused HUD with 2-turn memory
  - `agent.py`: Public LocalAgent facade
- **llm/**: LLM adapters (GroqAdapter, MockLLMAdapter)
- **tools/**: Tool implementations (hardware, windows, system)

**Design Philosophy:** "Stateful Context, Atomic Action"
- User acts as the Orchestrator
- Agent acts as the Bionic Arm
- Short-term memory (2 turns) for "it/that" resolution

## Build & Development Commands

```bash
# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest tests/

# Lint code
ruff check .

# Format code
ruff format .

# Run the agent
python main.py           # Default 8B model
python main.py --smart   # Use 70B model for complex reasoning
```

## Environment Setup

Requires `GROQ_API_KEY` in `.env` file. Without it, the agent runs in mock mode with pattern-based responses.

## Project Structure

```
windows-automation-agent/
├── main.py                    # CLI entry point
├── core/
│   ├── __init__.py
│   ├── protocols.py           # ABCs/Protocols (LLMClient, DecisionMaker, etc.)
│   ├── context.py             # AgentContext, ConversationTurn
│   ├── brain.py               # Brain (LLM decision maker)
│   ├── router.py              # Router (atomic executor)
│   ├── registry.py            # ToolRegistry (tool mapping)
│   ├── agent.py               # LocalAgent (facade)
│   ├── constants.py           # LATENCY_TOOLS, model configs
│   ├── tool_decorator.py      # Tool registration with JSON Schema
│   └── prompt_builder.py      # Dynamic prompt generation from specs
├── llm/
│   ├── __init__.py
│   ├── groq_adapter.py        # Groq LLM implementation
│   └── mock_adapter.py        # Mock LLM for testing
├── tools/
│   ├── __init__.py
│   ├── tool_specs.py          # Declarative tool definitions (JSON Schema)
│   ├── hardware_tools.py      # Brightness, screen power
│   ├── windows_tools.py       # Window management, virtual desktops
│   └── system_tools.py        # File ops, processes, clipboard
└── tests/
```

## Key Modules

### core/protocols.py
Defines contracts between components:
- `LLMClient`: Abstraction for LLM providers (Groq, OpenAI, Mock)
- `DecisionMaker`: Brain interface for tool selection
- `ToolExecutor`: Body interface for tool execution
- `StateManager`: Router interface

### core/brain.py
LLM Router that builds system prompts with HUD and calls LLM to get tool decisions.

### core/router.py
Atomic executor: Input -> LLM -> Tool -> Result. No loops, no retries, fail fast.

### llm/groq_adapter.py & llm/mock_adapter.py
LLM implementations. GroqAdapter uses Groq API; MockLLMAdapter uses pattern matching for testing.

## Architecture Patterns

**Atomic Execution**: Each command = single tool call. No multi-step chaining. User orchestrates the sequence.

**HUD (Heads-Up Display)**: System prompt includes real-time state:
- Active Focus: Current window title and ID
- Last Action: What was just done (for "it/that" resolution)
- Working Dir: Current directory

**Two-Gear Model Strategy**: Default to Llama-3.1-8B (1200 tokens/sec). Switch to 70B with `--smart` flag. Both have 8K context limit.

**Enriched Tool Returns**: All tools return `{status, action, target, message}` format for HUD updates.

**Session-Scoped Window IDs**: Windows get integer IDs (1, 2, 3...) valid only for current session.

**Dependency Injection**: All core components depend on protocols, not concrete implementations. LLM client is injected into Brain.

## Tool Categories

**Window Management**: `list_windows`, `focus_window`, `minimize_window`, `close_window`, `move_window`
**Virtual Desktops**: `list_desktops`, `switch_desktop`
**Batch Operations**: `minimize_all`, `restore_all`, `maximize_all`
**Text Input**: `type_text` (uses clipboard for reliability)
**File System**: `list_files`, `delete_item`, `change_dir`
**Applications**: `launch_app` (with poll-and-focus), `open_explorer`
**System**: `get_sys_info`, `check_processes`, `get_clipboard`, `set_clipboard`, `get_env`, `list_usb`
**Hardware**: `set_brightness`, `turn_screen_off`, `turn_screen_on`

## Destructive Actions

Tools like `close_window`, `delete_item` require user confirmation. Destructive tools are defined declaratively in `tools/tool_specs.py` via `ToolSpec.destructive=True` and `ToolSpec.risk_level`. Use `core.tool_decorator.get_destructive_tools()` to retrieve them at runtime.

## Adding New Tools (OCP-Compliant)

To add a new tool, edit only `tools/tool_specs.py`:

```python
# 1. Define the spec using JSON Schema helpers
NEW_TOOL_SPEC = ToolSpec(
    name="new_tool",
    description="What the tool does",
    input_schema=make_schema(
        properties={
            "param": string_param("Parameter description"),
            "level": int_param("Level", minimum=0, maximum=100),
        },
        required=["param"]
    ),
    destructive=False,  # Set to True if needs confirmation
    risk_level="LOW",   # LOW, MEDIUM, HIGH
    returns_description="What it returns"
)

# 2. Register in register_all_tools()
register_tool("new_tool", some_class.new_tool_method, NEW_TOOL_SPEC)

# 3. Add to ALL_TOOL_SPECS list
```

No changes needed to brain.py, registry.py, or router.py - the prompt builder generates tool specs dynamically.

## Historical Reference

- `docs/SOLID_REVIEW_AND_IMPLEMENTATION_PLAN.md`: Original SOLID analysis and refactoring plan
