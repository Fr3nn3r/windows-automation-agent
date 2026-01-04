# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Windows Automation Agent: An LLM-powered desktop automation system that interprets natural language commands and executes them using Windows system tools. Uses Groq's Llama models for near-instant response times.

**Core Architecture:** Brain/Body/Orchestrator pattern
- **Brain** (`main_agent.py`): LLM decision maker using Groq (8B fast model or 70B smart model)
- **Body** (`ToolRegistry`): Stateless tool executor with ~22 registered tools
- **Orchestrator**: Coordinates Brain and Body, manages session state, error recovery, and safety confirmations

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

- `main_agent.py` (812 lines): Main entry point containing all core classes:
  - `AgentContext`: Session state (history, cwd, active window, retry tracking)
  - `ToolRegistry`: Maps tool names to callable functions
  - `Brain`: Builds prompts, calls Groq API, handles two-tier model switching
  - `Orchestrator`: Session lifecycle, error recovery loop (3 retries), destructive action confirmation
  - `LocalAgent`: Public facade

- `tools/windows_tools.py`: Window management, virtual desktops, app launching with poll-and-focus, `type_text`
- `tools/system_tools.py`: File ops, processes, system info, clipboard
- `tools/hardware_tools.py`: Screen brightness, monitor power control

## Architecture Patterns

**Two-Gear Model Strategy**: Default to Llama-3.1-8B (1200 tokens/sec) for simple commands. Switch to 70B with `--smart` flag for complex reasoning. Both have 8K context limit.

**Context Hygiene**: System prompt ~1.5K tokens, history last 10 turns. Outputs truncated to prevent context overflow. Large results (>50 items) are truncated with count.

**Session-Scoped Window IDs**: Windows get integer IDs (1, 2, 3...) valid only for current session for reliable targeting.

**Multi-Step Action Chaining**: Brain can return list of actions `[{tool, args}, ...]` executed sequentially with latency injection between UI-affecting tools.

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
**File System**: `list_files`, `delete_item`
**Applications**: `launch_app` (with poll-and-focus), `open_explorer`
**System**: `get_sys_info`, `check_processes`, `get_clipboard`, `set_clipboard`
**Hardware**: `set_brightness`, `turn_screen_off`

## Destructive Actions

Tools like `close_window`, `delete_item` require user confirmation. The `DESTRUCTIVE_ACTIONS` dict in `main_agent.py` defines which tools need confirmation and their warning messages.
