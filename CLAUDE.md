# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Windows Automation Agent: An LLM-powered desktop automation system that interprets natural language commands and executes them using Windows system tools. Uses Groq's Llama models for near-instant response times.

**Core Architecture:** Atomic Router pattern
- **Brain** (`main_agent.py`): LLM Router - maps intent to single tool using Groq (8B fast or 70B smart)
- **Body** (`ToolRegistry`): Stateless tool executor with ~26 registered tools
- **Router**: Atomic executor (no loops, no retries, fail fast)
- **AgentContext**: State-focused HUD (last action, focused window, cwd) with 2-turn memory

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
python main_agent.py           # Default 8B model
python main_agent.py --smart   # Use 70B model for complex reasoning
```

## Environment Setup

Requires `GROQ_API_KEY` in `.env` file. Without it, the agent runs in mock mode with pattern-based responses.

## Key Files

- `main_agent.py`: Main entry point containing all core classes:
  - `AgentContext`: State-focused HUD (last_tool_output, focused_window_cache, 2-turn history)
  - `ToolRegistry`: Maps tool names to callable functions (~26 tools)
  - `Brain`: Builds prompts with HUD, calls Groq API, enforces atomic output
  - `Router`: Atomic executor - no loops, no retries, fail fast
  - `LocalAgent`: Public facade

- `tools/windows_tools.py`: Window management, virtual desktops, app launching with poll-and-focus, `type_text`
- `tools/system_tools.py`: File ops, processes, system info, clipboard
- `tools/hardware_tools.py`: Screen brightness, monitor power control

## Architecture Patterns

**Atomic Execution**: Each command = single tool call. No multi-step chaining. User orchestrates the sequence.

**HUD (Heads-Up Display)**: System prompt includes real-time state:
- Active Focus: Current window title and ID
- Last Action: What was just done (for "it/that" resolution)
- Working Dir: Current directory

**Two-Gear Model Strategy**: Default to Llama-3.1-8B (1200 tokens/sec). Switch to 70B with `--smart` flag. Both have 8K context limit.

**Enriched Tool Returns**: All tools return `{status, action, target, message}` format for HUD updates.

**Session-Scoped Window IDs**: Windows get integer IDs (1, 2, 3...) valid only for current session.

## Known Architectural Issues

See `docs/SOLID_REVIEW_AND_IMPLEMENTATION_PLAN.md` for detailed analysis. Key issues:
- All 6 classes in single 812-line file (violates SRP)
- No protocol/ABC definitions - tight coupling to Groq (violates DIP)
- Hardcoded tool registry - must edit source to add tools (violates OCP)
- Fat interfaces: `WindowManager` has 15+ methods mixing 4 domains

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

Tools like `close_window`, `delete_item` require user confirmation. The `DESTRUCTIVE_ACTIONS` dict in `main_agent.py` defines which tools need confirmation and their warning messages.
