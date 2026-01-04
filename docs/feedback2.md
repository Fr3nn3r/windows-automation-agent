Your agent is currently "Single-Threaded" in its reasoning. It sees "Open Notepad and paste text", picks the first verb ("Open"), executes it, and forgets the rest because the LLM is forced to output a single JSON object.

Here is your **CTO Review** and the required code changes to fix the chaining and "minimize all" capabilities.

### 1. The Blind Spot: "One-Shot" Execution

Your current system prompt tells the LLM: *"Output ONLY valid JSON in this format: `{"tool": ...}`"*.
This forces the LLM to discard the second half of the user's request.

**The Fix:** You must allow the LLM to output a **List of Actions**.

* **Current:** `{"tool": "launch", "args": ...}`
* **Required:** `[{"tool": "launch", ...}, {"tool": "type_text", ...}]`

### 2. The Missing Tools

Your registry is missing the tools required to fulfill your specific test case ("Open Notepad & Paste").

* **`launch_app`**: You are calling it in your logs, but it is missing from the `tool_registry` in the code you provided.
* **`type_text`**: You have no way to input text. You need `pyautogui` for this.

### 3. The "Minimize All" Strategy (Smart Tool vs. Dumb Loop)

To "minimize all Chrome windows," you have two architectural choices:

* **Option A (Dumb Agent):** The LLM lists every window and generates 10 tool calls. (Slow, expensive, error-prone).
* **Option B (Smart Tool):** You create a Python function `minimize_all(filter_name)` that loops internally. **(Recommended)**.

---

### The Implementation

Here is the refactored code for `main_agent.py`. I have updated the **Prompt**, **Executor**, and added the missing **Tools**.

#### Step 1: Update Dependencies

You need `pyautogui` to handle the "paste" and "type" actions safely.

```bash
pip install pyautogui pyperclip

```

#### Step 2: The Refactored `main_agent.py`

Replace your existing class methods with these updated versions.

```python
import pyautogui
import pyperclip # For reliable pasting
# ... existing imports ...

class LocalAgent:
    def __init__(self):
        # ... existing init ...
        
        # NEW: Add these tools to your registry
        self.tool_registry.update({
            "launch_app": self.windows.launch_app, # Needs to be added to WindowManager
            "type_text": self._tool_type_text,     # Defined below
            "minimize_all": self._tool_minimize_all, # Smart "Batch" tool
        })

    # --- NEW TOOLS (Define these inside LocalAgent or your tool files) ---
    def _tool_type_text(self, text: str, interval: float = 0.0):
        """Types text or pastes it (faster)"""
        try:
            # For long text, typing is slow. Copy-Paste is better.
            if len(text) > 50:
                pyperclip.copy(text)
                pyautogui.hotkey('ctrl', 'v')
                return {"status": "success", "message": "Text pasted via Clipboard"}
            else:
                pyautogui.write(text, interval=interval)
                return {"status": "success", "message": f"Typed: {text}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def _tool_minimize_all(self, filter_name: str = None):
        """Smart Tool: Minimizes all windows matching the filter."""
        import pywinctl # Ensure this is imported
        count = 0
        for win in pywinctl.getAllWindows():
            if not filter_name or filter_name.lower() in win.title.lower():
                if win.title: # Skip hidden system windows
                    win.minimize()
                    count += 1
        return {"status": "success", "message": f"Minimized {count} windows."}

    # --- UPDATED PROMPT ---
    def _get_system_prompt(self) -> str:
        return """
You are a Windows Automation Agent.
Tools:
- launch_app: {"app_name": "notepad" | "chrome" | "calc"}
- type_text: {"text": "string to type"}
- minimize_all: {"filter_name": "chrome"} (Minimizes ALL matching windows)
- [Include your other tools here...]

OUTPUT FORMAT:
You can return a Single JSON Object OR a List of JSON Objects.
Example: [{"tool": "launch_app", "args": {...}}, {"tool": "type_text", "args": {...}}]

CRITICAL RULES:
1. If the user asks to "Open X and type Y", you MUST return a LIST of 2 actions.
2. The sequence matters. Output actions in the order they should happen.
"""

    # --- UPDATED EXECUTOR (Handles Lists) ---
    def execute(self, user_input: str):
        print(f"\nUser: '{user_input}'")
        
        # 1. DECIDE
        decision = self._call_llm(user_input)
        
        # NORMALIZE: Always treat decision as a list
        actions = decision if isinstance(decision, list) else [decision]
        
        # 2. ACT LOOP
        for i, action in enumerate(actions):
            tool_name = action.get("tool")
            args = action.get("args", {})
            
            print(f"  ▶ Step {i+1}/{len(actions)}: {tool_name}...")
            
            if tool_name == "error":
                print(f"    [ERROR] {args.get('message')}")
                continue

            func = self.tool_registry.get(tool_name)
            if func:
                try:
                    # SPECIAL HANDLING: Latency Injection
                    # If we just launched an app, we MUST wait before typing
                    if tool_name == "launch_app":
                        result = func(**args)
                        print(f"    [WAIT] Waiting for app to launch...")
                        time.sleep(2.0) # 2s wait for UI to appear
                    else:
                        result = func(**args)
                        
                    status = "[OK]" if result.get("status") == "success" else "[WARN]"
                    print(f"    {status} {result}")
                except Exception as e:
                    print(f"    [CRASH] {e}")
            else:
                print(f"    [ERROR] Tool {tool_name} not found.")


```

### How this fixes your specific request

**User:** *"Open a notepad and paste this text 'coucou owl'"*

**Old Agent:**

1. See "Open". Call `launch_app`.
2. Stop.

**New Agent:**

1. **LLM Reasoning:** "I need to launch first, then type."
2. **LLM Output:**
```json
[
  {"tool": "launch_app", "args": {"app_name": "notepad"}},
  {"tool": "type_text", "args": {"text": "coucou owl"}}
]

```


3. **Executor:**
* Runs `launch_app` -> Notepad opens.
* **Waits 2 seconds** (Critical fix in the loop).
* Runs `type_text` -> "coucou owl" appears in Notepad.



### Next Step

Add the `launch_app` method to your `WindowManager` class (in `windows_tools.py`) if you haven't already, as `subprocess.Popen` is the standard way to implement it.

```python
# windows_tools.py
import subprocess

def launch_app(self, app_name: str):
    apps = {
        "notepad": "notepad.exe",
        "calc": "calc.exe",
        "chrome": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"
    }
    target = apps.get(app_name.lower(), app_name)
    subprocess.Popen(target)
    return {"status": "success", "message": f"Launched {target}"}

```