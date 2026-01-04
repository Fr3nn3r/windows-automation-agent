# SOLID Principles Review & Implementation Plan

## Executive Summary

The **Windows Automation Agent** has a solid architectural foundation with the Brain/Body/Orchestrator pattern. However, several SOLID principle violations hinder testability, extensibility, and maintainability. This document identifies issues and provides a prioritized implementation plan.

---

## SOLID Principles Analysis

### S - Single Responsibility Principle (SRP)

> "A class should have only one reason to change."

#### Violations Found:

| Location | Issue | Impact |
|----------|-------|--------|
| `main_agent.py` (812 lines) | 6 classes in one file: `ConversationTurn`, `AgentContext`, `ToolRegistry`, `Brain`, `Orchestrator`, `LocalAgent` | Hard to navigate, test, and maintain |
| `Brain` class (lines 208-441) | Handles both LLM communication AND mock decision logic (200+ lines of mock patterns) | Mock logic should be separate strategy |
| `Orchestrator` class (lines 448-669) | 6 responsibilities: session lifecycle, history, error recovery, confirmation, sanitization, latency injection | Monolithic, hard to test individually |
| `WindowManager` (tools/windows_tools.py) | 15+ methods: window management, app launching, text input, virtual desktops, batch operations | Should be split by domain |
| `SystemTools` (tools/system_tools.py) | Mixes: file ops, process ops, system info, app launching, clipboard | Should be split by domain |

#### Code Examples:

**Orchestrator has too many responsibilities:**
```python
# main_agent.py:448-669
class Orchestrator:
    def start_session(self) ...        # Session lifecycle
    def end_session(self) ...          # Session lifecycle
    def _confirm_destructive_action()  # Safety gate
    def _sanitize_output()             # Output processing
    def _execute_single_action()       # Tool execution
    def process()                      # Main pipeline (retry loop)
    LATENCY_TOOLS = {...}              # Configuration
```

**WindowManager mixes concerns:**
```python
# tools/windows_tools.py - One class doing 4 different things:
class WindowManager:
    def list_open_windows()     # Window enumeration
    def launch_app()            # Process launching (not window management!)
    def type_text()             # Input automation (not window management!)
    def switch_desktop()        # Virtual desktop (separate subsystem)
```

---

### O - Open/Closed Principle (OCP)

> "Open for extension, closed for modification."

#### Violations Found:

| Location | Issue | Impact |
|----------|-------|--------|
| `ToolRegistry.__init__` (lines 157-193) | Hardcoded tool mapping - adding tools requires editing class | Every new tool = code modification |
| `Brain._build_system_prompt()` (lines 224-293) | Tool specs embedded as string literal | New tools need prompt edits |
| `DESTRUCTIVE_ACTIONS` (lines 133-144) | Module-level constant with no extension API | New destructive tools need file edit |
| `Brain._mock_decide()` (lines 330-441) | 100+ lines of hardcoded patterns | Impossible to extend for testing |

#### Code Examples:

**Closed ToolRegistry:**
```python
# main_agent.py:162-193 - Must edit this dict to add any tool
self._registry: Dict[str, Callable] = {
    "set_brightness": self.hardware.set_brightness,
    "turn_screen_off": self.hardware.turn_screen_off,
    # ... 18 more hardcoded entries
}
```

**Closed System Prompt:**
```python
# main_agent.py:226-260 - Tool specs as literal string
tools_spec = """
Tools and their EXACT argument names:
- set_brightness: args: {"level": <int 0-100>}
- turn_screen_off: args: {}
# ... must edit this string for every new tool
"""
```

---

### L - Liskov Substitution Principle (LSP)

> "Subtypes must be substitutable for their base types."

#### Current State:

- **No inheritance used** (except dataclasses)
- No abstract base classes or protocols defined
- Not technically violated, but **lack of abstractions prevents polymorphism**

#### Implication:

Without abstractions, we can't substitute:
- A `MockBrain` for `Brain` in tests
- A `RemoteToolRegistry` for `ToolRegistry`
- A `LinuxWindowManager` for `WindowManager`

---

### I - Interface Segregation Principle (ISP)

> "Clients should not depend on interfaces they don't use."

#### Violations Found:

| Location | Issue | Impact |
|----------|-------|--------|
| `WindowManager` | 15+ public methods - all or nothing | A clipboard-only client gets window methods |
| `SystemTools` | Mixes 5 domains: files, processes, system info, apps, clipboard | File-only clients get process methods |
| `AgentContext` | Carries retry info (`retry_count`, `last_error`) even when Brain doesn't need it | Unnecessary coupling |

#### Code Example:

```python
# tools/system_tools.py - One fat interface
class SystemTools:
    # Domain 1: Files
    def list_directory() ...
    def create_file() ...
    def delete_item() ...

    # Domain 2: Processes
    def list_processes() ...

    # Domain 3: System Info
    def get_system_info() ...
    def get_environment_variable() ...
    def list_usb_devices() ...

    # Domain 4: Apps
    def launch_app() ...
    def open_explorer() ...

    # Domain 5: Clipboard
    def get_clipboard() ...
    def set_clipboard() ...
```

---

### D - Dependency Inversion Principle (DIP)

> "Depend on abstractions, not concretions."

#### Violations Found:

| Location | Issue | Impact |
|----------|-------|--------|
| `LocalAgent.__init__` (lines 686-698) | Creates `Groq()` client directly | Can't swap for OpenAI, mock, etc. |
| `Orchestrator.__init__` (line 458) | Takes concrete `Brain` and `ToolRegistry` | No interface contract |
| `ToolRegistry.__init__` (lines 158-160) | Creates `HardwareController()`, `WindowManager()`, `SystemTools()` directly | No dependency injection |
| `SystemTools.__init__` (line 19) | Creates `wmi.WMI()` directly | Can't mock for Linux/tests |
| All tool classes | No ABC/Protocol definitions anywhere | Zero abstraction layer |

#### Code Example:

```python
# main_agent.py:686-698 - Direct instantiation = tight coupling
class LocalAgent:
    def __init__(self, use_smart_model: bool = False):
        api_key = os.environ.get("GROQ_API_KEY")
        if api_key:
            client = Groq(api_key=api_key)  # Concrete dependency!
        else:
            client = None

        self.body = ToolRegistry()  # Concrete dependency!
        self.brain = Brain(client, use_smart_model=use_smart_model)  # Concrete!
        self.orchestrator = Orchestrator(self.brain, self.body)  # Concrete!
```

---

## Severity Assessment

| Principle | Severity | Why |
|-----------|----------|-----|
| **DIP** | Critical | Blocks testability & multi-LLM support |
| **SRP** | High | 812-line monolith hurts maintainability |
| **OCP** | High | Every new tool requires code changes |
| **ISP** | Medium | Fat interfaces increase coupling |
| **LSP** | Low | No inheritance = no violation (but no polymorphism either) |

---

## Implementation Plan

### Phase 1: Establish Abstractions (DIP Foundation)

**Goal:** Define protocols/ABCs so components can be swapped.

#### Task 1.1: Create Protocol Definitions

Create `core/protocols.py`:

```python
from typing import Protocol, Dict, Any, Optional, Callable

class LLMClient(Protocol):
    """Abstraction for any LLM provider (Groq, OpenAI, Anthropic, Mock)."""
    def complete(self, messages: list, **kwargs) -> str: ...

class DecisionMaker(Protocol):
    """The Brain interface."""
    def decide(self, context: "AgentContext", user_input: str) -> Dict[str, Any]: ...

class ToolExecutor(Protocol):
    """The Body interface."""
    def get(self, tool_name: str) -> Optional[Callable]: ...
    def list_tools(self) -> list[str]: ...

class StateManager(Protocol):
    """The Orchestrator interface."""
    def process(self, user_input: str) -> Dict[str, Any]: ...
    def start_session(self) -> str: ...
    def end_session(self) -> None: ...
```

#### Task 1.2: Create LLM Adapter Layer

Create `core/llm_adapters.py`:

```python
class GroqAdapter:
    """Wraps Groq client to match LLMClient protocol."""
    def __init__(self, api_key: str, model: str):
        self.client = Groq(api_key=api_key)
        self.model = model

    def complete(self, messages: list, **kwargs) -> str:
        response = self.client.chat.completions.create(
            model=self.model, messages=messages, **kwargs
        )
        return response.choices[0].message.content

class MockLLMAdapter:
    """For testing - returns predictable responses."""
    def complete(self, messages: list, **kwargs) -> str:
        # Move mock logic here from Brain._mock_decide()
        ...
```

**Files to create:**
- `core/__init__.py`
- `core/protocols.py`
- `core/llm_adapters.py`

---

### Phase 2: Break Up the Monolith (SRP)

**Goal:** Each file has one clear purpose.

#### Task 2.1: Split `main_agent.py` into modules

```
main_agent.py (812 lines)
    ↓ becomes ↓
core/
├── context.py      # AgentContext, ConversationTurn
├── brain.py        # Brain class
├── orchestrator.py # Orchestrator class
├── registry.py     # ToolRegistry class
├── agent.py        # LocalAgent facade
└── constants.py    # DESTRUCTIVE_ACTIONS, etc.
```

#### Task 2.2: Split `WindowManager` by domain

```
tools/windows_tools.py (669 lines)
    ↓ becomes ↓
tools/
├── window_manager.py   # list_windows, focus, minimize, maximize, close
├── desktop_manager.py  # list_desktops, switch_desktop, move_window
├── app_launcher.py     # launch_app (with poll-and-focus)
├── input_tools.py      # type_text
└── batch_operations.py # minimize_all, restore_all, maximize_all
```

#### Task 2.3: Split `SystemTools` by domain

```
tools/system_tools.py (303 lines)
    ↓ becomes ↓
tools/
├── file_tools.py      # list_directory, create_file, delete_item
├── process_tools.py   # list_processes
├── system_info.py     # get_system_info, get_environment_variable, list_usb_devices
├── clipboard_tools.py # get_clipboard, set_clipboard
└── explorer_tools.py  # open_explorer
```

---

### Phase 3: Make Tools Extensible (OCP)

**Goal:** Add new tools without modifying existing code.

#### Task 3.1: Create Tool Decorator/Registration System

```python
# core/tool_decorator.py
from dataclasses import dataclass
from typing import Callable, Dict, Any

@dataclass
class ToolSpec:
    name: str
    description: str
    args_schema: Dict[str, Any]
    destructive: bool = False
    risk_level: str = "LOW"

_tool_registry: Dict[str, tuple[Callable, ToolSpec]] = {}

def tool(spec: ToolSpec):
    """Decorator to auto-register tools."""
    def decorator(func: Callable):
        _tool_registry[spec.name] = (func, spec)
        return func
    return decorator

# Usage:
@tool(ToolSpec(
    name="set_brightness",
    description="Sets screen brightness 0-100",
    args_schema={"level": "int 0-100"},
))
def set_brightness(level: int) -> dict:
    ...
```

#### Task 3.2: Auto-Generate System Prompt from Registry

```python
# core/prompt_builder.py
def build_tools_prompt() -> str:
    """Dynamically generate tool specs from registry."""
    lines = ["Tools and their EXACT argument names:"]
    for name, (func, spec) in _tool_registry.items():
        args = ", ".join(f'"{k}": {v}' for k, v in spec.args_schema.items())
        lines.append(f"- {name}: args: {{{args}}}")
    return "\n".join(lines)
```

---

### Phase 4: Dependency Injection (DIP Completion)

**Goal:** All dependencies are injected, not created internally.

#### Task 4.1: Refactor LocalAgent to Use Injection

```python
# core/agent.py
class LocalAgent:
    def __init__(
        self,
        llm_client: LLMClient,       # Injected!
        tool_registry: ToolExecutor,  # Injected!
        orchestrator: StateManager,   # Injected!
    ):
        self.brain = Brain(llm_client)
        self.body = tool_registry
        self.orchestrator = orchestrator
```

#### Task 4.2: Create Factory Functions

```python
# core/factory.py
def create_agent(
    llm_provider: str = "groq",
    model: str = None,
    tools: list[str] = None,
) -> LocalAgent:
    """Factory that wires up dependencies."""

    # 1. Create LLM client based on provider
    if llm_provider == "groq":
        client = GroqAdapter(os.environ["GROQ_API_KEY"], model or "llama-3.1-8b-instant")
    elif llm_provider == "mock":
        client = MockLLMAdapter()
    else:
        raise ValueError(f"Unknown provider: {llm_provider}")

    # 2. Create tool registry (optionally filtered)
    registry = ToolRegistry(enabled_tools=tools)

    # 3. Wire up
    brain = Brain(client)
    orchestrator = Orchestrator(brain, registry)

    return LocalAgent(client, registry, orchestrator)
```

---

### Phase 5: Split Orchestrator Responsibilities (SRP)

**Goal:** Extract single-purpose components from Orchestrator.

#### Task 5.1: Extract Confirmation Handler

```python
# core/safety_gate.py
class SafetyGate:
    """Handles destructive action confirmation."""

    def __init__(self, destructive_actions: dict):
        self.actions = destructive_actions

    def requires_confirmation(self, tool_name: str) -> bool:
        return tool_name in self.actions

    def confirm(self, tool_name: str, args: dict) -> bool:
        # Prompt user and return True/False
        ...
```

#### Task 5.2: Extract Output Sanitizer

```python
# core/sanitizer.py
class OutputSanitizer:
    """Truncates large outputs to prevent context flooding."""

    def __init__(self, max_items: int = 50):
        self.max_items = max_items

    def sanitize(self, result: dict) -> dict:
        # Truncation logic moved here
        ...
```

#### Task 5.3: Extract Retry Handler

```python
# core/retry_handler.py
class RetryHandler:
    """Manages retry logic with exponential backoff."""

    def __init__(self, max_retries: int = 3):
        self.max_retries = max_retries

    def should_retry(self, error: str, attempt: int) -> bool:
        return attempt < self.max_retries

    def record_error(self, context: AgentContext, error: str):
        context.last_error = error
        context.retry_count += 1
```

#### Final Orchestrator (thin coordinator):

```python
# core/orchestrator.py
class Orchestrator:
    def __init__(
        self,
        brain: DecisionMaker,
        body: ToolExecutor,
        safety_gate: SafetyGate,
        sanitizer: OutputSanitizer,
        retry_handler: RetryHandler,
    ):
        self.brain = brain
        self.body = body
        self.safety_gate = safety_gate
        self.sanitizer = sanitizer
        self.retry_handler = retry_handler

    def process(self, user_input: str) -> dict:
        # Now just coordinates, doesn't implement everything
        decision = self.brain.decide(...)

        if self.safety_gate.requires_confirmation(decision["tool"]):
            if not self.safety_gate.confirm(...):
                return {"status": "cancelled"}

        result = self.body.get(decision["tool"])(**decision["args"])
        return self.sanitizer.sanitize(result)
```

---

## Proposed Final Directory Structure

```
windows-automation-agent/
├── main.py                    # CLI entry point (slim)
├── core/
│   ├── __init__.py
│   ├── protocols.py           # ABCs/Protocols
│   ├── context.py             # AgentContext, ConversationTurn
│   ├── brain.py               # Brain (decision maker)
│   ├── orchestrator.py        # Orchestrator (coordinator)
│   ├── registry.py            # ToolRegistry (dynamic)
│   ├── agent.py               # LocalAgent (facade)
│   ├── factory.py             # Dependency wiring
│   ├── constants.py           # Configuration
│   ├── tool_decorator.py      # @tool registration
│   ├── prompt_builder.py      # Dynamic prompt generation
│   ├── safety_gate.py         # Confirmation handler
│   ├── sanitizer.py           # Output truncation
│   └── retry_handler.py       # Retry logic
├── llm/
│   ├── __init__.py
│   ├── base.py                # LLMClient protocol
│   ├── groq_adapter.py        # Groq implementation
│   ├── mock_adapter.py        # Mock for testing
│   └── openai_adapter.py      # Future: OpenAI support
├── tools/
│   ├── __init__.py
│   ├── window_manager.py      # Window operations
│   ├── desktop_manager.py     # Virtual desktops
│   ├── app_launcher.py        # Application launching
│   ├── input_tools.py         # Keyboard/text input
│   ├── batch_operations.py    # Bulk window ops
│   ├── file_tools.py          # File operations
│   ├── process_tools.py       # Process management
│   ├── system_info.py         # System information
│   ├── clipboard_tools.py     # Clipboard
│   ├── hardware_tools.py      # Brightness, screen power
│   └── explorer_tools.py      # File Explorer
├── tests/
│   ├── __init__.py
│   ├── test_brain.py
│   ├── test_orchestrator.py
│   ├── test_tools/
│   │   ├── test_window_manager.py
│   │   ├── test_file_tools.py
│   │   └── ...
│   └── fixtures/
│       └── mock_llm_responses.py
├── pyproject.toml
├── requirements.txt
└── README.md
```

---

## Implementation Priority Matrix

| Phase | Effort | Impact | Priority |
|-------|--------|--------|----------|
| Phase 1: Abstractions (DIP) | Medium | High | 1 (Do First) |
| Phase 2: Split Monolith (SRP) | High | High | 2 |
| Phase 3: Tool Extension (OCP) | Medium | Medium | 3 |
| Phase 4: Dependency Injection | Low | High | 4 |
| Phase 5: Extract from Orchestrator | Medium | Medium | 5 |

---

## Migration Strategy

### Step-by-Step Approach:

1. **Create new structure alongside old code** - Don't break existing functionality
2. **Add protocols first** - They have no dependencies
3. **Migrate one class at a time** - Test after each migration
4. **Update imports in `main_agent.py`** - Keep facade working
5. **Delete old code last** - Only when all tests pass

### Backward Compatibility:

Keep `main_agent.py` as a facade that imports from new locations:

```python
# main_agent.py (temporary shim during migration)
from core.agent import LocalAgent
from core.context import AgentContext, ConversationTurn
from core.brain import Brain
from core.orchestrator import Orchestrator
from core.registry import ToolRegistry

# Re-export for backward compatibility
__all__ = ["LocalAgent", "AgentContext", "Brain", "Orchestrator", "ToolRegistry"]
```

---

## Success Metrics

After implementation:

| Metric | Before | Target |
|--------|--------|--------|
| Lines in largest file | 812 | <200 |
| Number of classes per file | 6 | 1-2 |
| Test coverage | ~20% | >80% |
| Time to add new tool | Edit 3 files | Add 1 decorated function |
| Time to swap LLM provider | Major refactor | Change 1 config line |

---

## Conclusion

The Windows Automation Agent has good foundational design (Brain/Body/Orchestrator) but needs refactoring to achieve proper SOLID compliance. The implementation plan prioritizes:

1. **Testability** (DIP) - Most critical for CI/CD
2. **Maintainability** (SRP) - Enable team scaling
3. **Extensibility** (OCP) - Future-proof for new tools/LLMs

Estimated effort: **2-3 weeks** for full implementation with tests.
