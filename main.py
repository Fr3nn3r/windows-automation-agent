#!/usr/bin/env python3
"""
Windows Automation Agent - CLI Entry Point.

An LLM-powered desktop automation system that interprets natural language
commands and executes them using Windows system tools.

Usage:
    python main.py           # Default 8B model
    python main.py --smart   # Use 70B model for complex reasoning
"""

import sys

from core.agent import LocalAgent


# =============================================================================
# TEST COMMANDS
# =============================================================================

TEST_COMMANDS = [
    # Basic commands
    "Set brightness to 50",
    "List all open windows",
    "Focus Chrome",
    "Show system info",
    # App launching
    "Open Notepad",
    "Open Downloads folder",
    "Launch Calculator",
    # New tools
    "Wake up the screen",
    "Show USB devices",
    "Show PATH variable",
    "Change directory to Downloads",
    # Batch operations (smart tools)
    "Minimize all Chrome windows",
    "Minimize all windows",
    # Clipboard
    "Get clipboard content",
    "Copy 'test message' to clipboard",
    # Type (after opening app)
    "Type 'Hello World'",
]


def show_menu():
    """Display the test commands menu."""
    print("\n" + "="*50)
    print("TEST COMMANDS (enter number or type your own):")
    print("="*50)
    for i, cmd in enumerate(TEST_COMMANDS, 1):
        print(f"  {i:2}. {cmd}")
    print("="*50)
    print("  0. Exit")
    print("="*50)


def main():
    """Main entry point for the Windows Automation Agent."""
    # Setup readline for arrow key history navigation
    try:
        import readline
    except ImportError:
        try:
            import pyreadline3 as readline
        except ImportError:
            readline = None

    # Pre-populate history with test commands (reverse so first is most recent)
    if readline:
        for cmd in reversed(TEST_COMMANDS):
            readline.add_history(cmd)

    # Check for --smart flag to use 70B model
    use_smart = "--smart" in sys.argv or "-s" in sys.argv

    # Initialize agent
    agent = LocalAgent(use_smart_model=use_smart)

    print("[AGENT] Windows Automation Agent Initialized (Atomic Mode).")
    print(f"[AGENT] Session: {agent.session_id}")
    print(f"[AGENT] Working Directory: {agent.cwd}")
    print("Tip: Use UP/DOWN arrows to cycle through commands. '--smart' for 70B model.")
    show_menu()  # Show menu once at start

    # Main loop
    while True:
        try:
            req = input("\n> ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nGoodbye!")
            break

        if req.lower() in ["exit", "quit", "q", "0"]:
            print("Goodbye!")
            break

        if req.lower() == "help":
            show_menu()
            continue

        if not req:
            continue

        # Handle numbered commands
        if req.isdigit():
            idx = int(req)
            if 1 <= idx <= len(TEST_COMMANDS):
                req = TEST_COMMANDS[idx - 1]
                print(f"Running: {req}")

        agent.execute(req)


if __name__ == "__main__":
    main()
