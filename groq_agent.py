import os
import re
import json
import time
import subprocess
from dotenv import load_dotenv
from groq import Groq

# 1. SETUP: Initialize the client
load_dotenv()
client = Groq(api_key=os.environ.get("GROQ_API_KEY"))

# 2. COMMAND REGISTRY: Pre-defined commands that actually work
COMMAND_PATTERNS = {
    # Brightness control (WMI - works on laptops)
    r"(dim|set|change|adjust).*(display|screen|bright).*?(\d+)":
        lambda m: f'(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{m.group(3)})',
    r"bright.*(max|full|100)":
        '(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,100)',

    # Lock screen
    r"lock.*(screen|computer|pc|workstation)":
        'rundll32.exe user32.dll,LockWorkStation',

    # Sleep/hibernate
    r"(sleep|hibernate).*(computer|pc|system)":
        'rundll32.exe powrprof.dll,SetSuspendState 0,1,0',

    # Open apps
    r"open.*(notepad)":
        'Start-Process notepad',
    r"open.*(calculator|calc)":
        'Start-Process calc',
    r"open.*(browser|chrome|edge)":
        'Start-Process msedge',
}

def check_command_registry(user_intent):
    """Check if user intent matches a pre-defined command."""
    intent_lower = user_intent.lower()
    for pattern, command in COMMAND_PATTERNS.items():
        match = re.search(pattern, intent_lower)
        if match:
            if callable(command):
                return command(match)
            return command
    return None

# 3. THE BRAIN: LLM-based command generation (fallback)
def generate_powershell_command(user_intent, retries=2):
    """
    First checks command registry, then falls back to LLM generation.
    """
    # Check registry first
    registry_cmd = check_command_registry(user_intent)
    if registry_cmd:
        print("[REGISTRY] Using pre-defined command")
        return registry_cmd

    start_time = time.time()

    system_prompt = (
        "You are a Windows PowerShell command generator. "
        "Output ONLY a valid JSON object: {\"command\": \"<powershell command>\"}\n"
        "Rules:\n"
        "- Use $env:USERPROFILE for user folders (Downloads, Documents, etc.)\n"
        "- Command must be a SIMPLE single line - no newlines, no here-strings\n"
        "- Use double quotes for strings\n"
        "- NO Add-Type, NO C# code, NO here-strings (@\" or @'), NO signatures\n"
        "- For queries: use Get-ChildItem, Get-Process, Get-Service, Get-Content, etc.\n"
        "- If a task cannot be done with simple PowerShell, respond with: {\"command\": null, \"reason\": \"explanation\"}\n"
        "- No explanations outside JSON, no markdown"
    )

    for attempt in range(retries + 1):
        try:
            completion = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Task: {user_intent}"}
                ],
                temperature=0.1,
                max_tokens=256
            )

            result_text = completion.choices[0].message.content.strip()

            # Try to parse as JSON
            try:
                data = json.loads(result_text)
                command = data.get("command")
                if command is None and "reason" in data:
                    print(f"[INFO] Cannot execute: {data['reason']}")
                    return None
            except json.JSONDecodeError:
                # Fallback: extract command from malformed response
                match = re.search(r'"command"\s*:\s*"(.+?)"', result_text, re.DOTALL)
                if match:
                    command = match.group(1).replace('\\n', ' ').strip()
                else:
                    raise ValueError("Could not parse command from response")

            if command:
                # Clean up escape sequences
                command = command.replace('\\\\', '\\')

                # Validate: reject blocking patterns
                blocking_patterns = ['@"', "@'", "Add-Type", "$signature", "<<", "Here-String"]
                for pattern in blocking_patterns:
                    if pattern.lower() in command.lower():
                        raise ValueError(f"Command contains blocking pattern: {pattern}")

                # Validate: check for balanced parentheses and quotes
                if command.count('(') != command.count(')'):
                    raise ValueError("Unbalanced parentheses")
                if command.count('"') % 2 != 0:
                    raise ValueError("Unbalanced quotes")

                latency = (time.time() - start_time) * 1000
                print(f"[LLM] Generated in {latency:.0f}ms")
                return command

        except Exception as e:
            if attempt < retries:
                print(f"[RETRY] Attempt {attempt + 1} failed, retrying...")
                continue
            print(f"Generation Error: {e}")
            return None

    return None

# 3. THE BODY: Shell Executor with timeout
class ShellExecutor:
    def __init__(self):
        print("[OK] PowerShell Engine Ready")

    def run(self, script, timeout=10):
        if not script:
            return ""

        print(f"Executing: {script}")

        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=timeout
            )
            output = result.stdout.strip() if result.stdout else ""
            if result.stderr:
                output += f"\n[Error]: {result.stderr.strip()}"
            return output
        except subprocess.TimeoutExpired:
            print("[TIMEOUT] Command took too long")
            return "[Command timed out]"
        except Exception as e:
            return f"[Error]: {e}"

# 4. MAIN LOOP
if __name__ == "__main__":
    executor = ShellExecutor()

    print("\nEnter your command (or /quit to exit):")

    while True:
        user_input = input("\n> ").strip()

        if user_input.lower() == "/quit":
            print("Goodbye!")
            break

        if not user_input:
            continue

        cmd = generate_powershell_command(user_input)
        if cmd:
            result = executor.run(cmd)
            # Handle encoding for Windows console
            safe_result = result.encode('ascii', errors='replace').decode('ascii')
            print(f"Result:\n{safe_result}")