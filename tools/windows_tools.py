# tools/window_tools.py
import pyvda
import pywinctl

def switch_desktop(desktop_index: int):
    """Safely switches to the target virtual desktop."""
    try:
        desktops = pyvda.get_virtual_desktops()
        if 1 <= desktop_index <= len(desktops):
            pyvda.VirtualDesktop(desktop_index).go()
            return {"status": "success", "message": f"Switched to Desktop {desktop_index}"}
        else:
            return {"status": "error", "message": f"Desktop {desktop_index} does not exist."}
    except Exception as e:
        return {"status": "error", "message": str(e)}

def minimize_window(app_name: str):
    """Finds a window by name and minimizes it."""
    # Logic to find window using pywinctl and minimize
    pass


import ctypes
import pywinctl
import pyvda
import pyautogui
import pyperclip
import re
import time
from typing import Dict, List, Union, Optional

class WindowManager:
    """
    Manages application windows and virtual desktops.
    Includes 'Smart Search' to find windows by partial names (e.g., 'Code' -> 'VS Code').
    """

    # --- HELPER: Smart Search ---
    # Windows to skip (helper/legacy windows that don't work with desktop APIs)
    SKIP_WINDOWS = ['legacy window', 'helper', 'notification', 'widget']

    def _find_window(self, query: str) -> Optional[pywinctl.Window]:
        """
        Private helper: Finds the best matching window object.
        Priority:
        1. Exact Match (Title)
        2. Case-insensitive Substring (Title) - prefers real windows over helper windows
        """
        all_windows = pywinctl.getAllWindows()
        query_lower = query.lower()

        # 1. Exact Match
        for win in all_windows:
            if win.title == query:
                return win

        # 2. Substring Match (Case Insensitive)
        matches = [w for w in all_windows if query_lower in w.title.lower()]
        if matches:
            # Filter out helper/legacy windows
            real_windows = [
                w for w in matches
                if not any(skip in w.title.lower() for skip in self.SKIP_WINDOWS)
            ]

            # Prefer real windows, fall back to all matches
            candidates = real_windows if real_windows else matches

            # Sort by title length (longer titles usually mean main windows with page titles)
            # e.g., "Google Gemini - Google Chrome" > "Chrome"
            candidates.sort(key=lambda x: len(x.title), reverse=True)
            return candidates[0]

        return None

    # --- WINDOW COMMANDS ---
    
    def list_open_windows(self) -> Dict[str, List[str]]:
        """Returns a list of all visible window titles for the agent to see."""
        try:
            titles = [w.title for w in pywinctl.getAllWindows() if w.title]
            return {"status": "success", "windows": titles, "count": len(titles)}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def focus_window(self, app_name: str) -> Dict[str, str]:
        """
        Brings a window to the front using low-level OS calls.
        Uses ctypes to bypass Windows Focus Stealing Prevention.
        """
        target = self._find_window(app_name)
        if not target:
            return {"status": "error", "message": f"Window '{app_name}' not found."}

        try:
            hwnd = target.getHandle()
            user32 = ctypes.windll.user32

            # 1. Force Restore if Minimized (SW_RESTORE = 9)
            if user32.IsIconic(hwnd):
                user32.ShowWindow(hwnd, 9)

            # 2. Get current foreground window's thread
            foreground_hwnd = user32.GetForegroundWindow()
            foreground_thread = user32.GetWindowThreadProcessId(foreground_hwnd, None)
            target_thread = user32.GetWindowThreadProcessId(hwnd, None)

            # 3. Attach to the foreground thread to gain focus rights
            if foreground_thread != target_thread:
                user32.AttachThreadInput(foreground_thread, target_thread, True)

            # 4. Force window to foreground
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)

            # 5. Flash briefly to ensure visibility (non-intrusive)
            user32.SetActiveWindow(hwnd)

            # 6. Detach threads
            if foreground_thread != target_thread:
                user32.AttachThreadInput(foreground_thread, target_thread, False)

            return {"status": "success", "message": f"Focused: {target.title}"}
        except Exception as e:
            # Fallback to pyautogui method
            try:
                pyautogui.press('alt')
                target.activate()
                return {"status": "success", "message": f"Focused (fallback): {target.title}"}
            except Exception as e2:
                return {"status": "error", "message": f"Could not focus window: {str(e)} / {str(e2)}"}

    def minimize_window(self, app_name: str) -> Dict[str, str]:
        """Minimizes a window."""
        target = self._find_window(app_name)
        if not target:
            return {"status": "error", "message": f"Window '{app_name}' not found."}
        
        try:
            target.minimize()
            return {"status": "success", "message": f"Minimized: {target.title}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def maximize_window(self, app_name: str) -> Dict[str, str]:
        """Maximizes a window."""
        target = self._find_window(app_name)
        if not target:
            return {"status": "error", "message": f"Window '{app_name}' not found."}
        
        try:
            target.maximize()
            return {"status": "success", "message": f"Maximized: {target.title}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def close_window(self, app_name: str) -> Dict[str, str]:
        """Closes a window. Warning: This works like clicking 'X'."""
        target = self._find_window(app_name)
        if not target:
            return {"status": "error", "message": f"Window '{app_name}' not found."}

        try:
            target.close()
            return {"status": "success", "message": f"Closed: {target.title}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # --- TEXT INPUT ---

    def type_text(self, text: str, use_clipboard: bool = None) -> Dict[str, str]:
        """
        Types text into the currently focused window.
        For long text (>50 chars), uses clipboard paste for speed.

        Args:
            text: The text to type
            use_clipboard: Force clipboard paste (True) or typing (False).
                          None = auto-decide based on length.
        """
        try:
            # Auto-decide: paste if long text
            if use_clipboard is None:
                use_clipboard = len(text) > 50

            if use_clipboard:
                # Copy-Paste method (faster for long text)
                pyperclip.copy(text)
                pyautogui.hotkey('ctrl', 'v')
                return {"status": "success", "message": f"Pasted text via clipboard ({len(text)} chars)"}
            else:
                # Type method (more reliable for short text)
                pyautogui.write(text, interval=0.02)  # Small delay between keys
                return {"status": "success", "message": f"Typed: {text[:50]}{'...' if len(text) > 50 else ''}"}
        except Exception as e:
            return {"status": "error", "message": f"Failed to type text: {str(e)}"}

    # --- BATCH OPERATIONS ---

    def minimize_all(self, filter_name: str = None) -> Dict[str, Union[str, int]]:
        """
        Smart batch tool: Minimizes all windows, optionally filtered by name.

        Args:
            filter_name: Optional - only minimize windows containing this text.
                        If None, minimizes ALL windows.

        Examples:
            minimize_all() -> minimizes everything
            minimize_all("chrome") -> minimizes all Chrome windows
        """
        try:
            count = 0
            skipped = 0
            all_windows = pywinctl.getAllWindows()

            for win in all_windows:
                # Skip empty titles (system windows)
                if not win.title:
                    continue

                # Skip helper/system windows
                if any(skip in win.title.lower() for skip in self.SKIP_WINDOWS):
                    continue

                # Filter check
                if filter_name:
                    if filter_name.lower() not in win.title.lower():
                        skipped += 1
                        continue

                try:
                    win.minimize()
                    count += 1
                except Exception:
                    skipped += 1  # Some windows can't be minimized

            msg = f"Minimized {count} windows"
            if filter_name:
                msg += f" matching '{filter_name}'"
            if skipped > 0:
                msg += f" ({skipped} skipped)"

            return {"status": "success", "message": msg, "count": count}
        except Exception as e:
            return {"status": "error", "message": f"minimize_all failed: {str(e)}"}

    def maximize_all(self, filter_name: str = None) -> Dict[str, Union[str, int]]:
        """
        Smart batch tool: Maximizes all windows, optionally filtered by name.
        """
        try:
            count = 0
            all_windows = pywinctl.getAllWindows()

            for win in all_windows:
                if not win.title:
                    continue
                if any(skip in win.title.lower() for skip in self.SKIP_WINDOWS):
                    continue
                if filter_name and filter_name.lower() not in win.title.lower():
                    continue

                try:
                    win.maximize()
                    count += 1
                except Exception:
                    pass

            msg = f"Maximized {count} windows"
            if filter_name:
                msg += f" matching '{filter_name}'"
            return {"status": "success", "message": msg, "count": count}
        except Exception as e:
            return {"status": "error", "message": f"maximize_all failed: {str(e)}"}

    # --- DESKTOP COMMANDS (Virtual Desktops) ---

    def list_desktops(self) -> Dict[str, List[int]]:
        """Lists available virtual desktops by ID/Index."""
        try:
            desktops = pyvda.get_virtual_desktops()
            count = len(desktops)
            current = pyvda.VirtualDesktop.current().number
            return {
                "status": "success",
                "count": count,
                "current_index": current,
                "note": "Indexes start at 1"
            }
        except Exception as e:
            return {"status": "error", "message": f"Desktop API failed: {str(e)}"}

    def switch_desktop(self, index: int) -> Dict[str, str]:
        """Switches to the virtual desktop at 'index'."""
        # Validate index is an integer
        if not isinstance(index, int):
            try:
                index = int(index)
            except (ValueError, TypeError):
                return {"status": "error", "message": f"index must be an integer, got: {index}"}

        try:
            desktops = pyvda.get_virtual_desktops()
            count = len(desktops)
            if index < 1 or index > count:
                return {
                    "status": "error",
                    "message": f"Index {index} out of bounds. Valid: 1-{count}"
                }

            # desktops list is 0-indexed, but user provides 1-indexed
            desktops[index - 1].go()
            return {"status": "success", "message": f"Switched to Desktop {index}"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def move_window_to_desktop(self, app_name: str, desktop_index: int) -> Dict[str, str]:
        """Moves a specific window to another desktop."""
        # Validate desktop_index is an integer
        if not isinstance(desktop_index, int):
            try:
                desktop_index = int(desktop_index)
            except (ValueError, TypeError):
                return {"status": "error", "message": f"desktop_index must be an integer, got: {desktop_index}"}

        target = self._find_window(app_name)
        if not target:
            return {"status": "error", "message": f"Window '{app_name}' not found."}

        try:
            desktops = pyvda.get_virtual_desktops()
            count = len(desktops)
            if desktop_index < 1 or desktop_index > count:
                return {
                    "status": "error",
                    "message": f"Desktop {desktop_index} out of bounds. Valid: 1-{count}"
                }

            # pyvda needs the HWND (Handle) of the window
            hwnd = target.getHandle()
            target_desktop = desktops[desktop_index - 1]
            pyvda.AppView(hwnd).move(target_desktop)
            return {
                "status": "success",
                "message": f"Moved '{target.title}' to Desktop {desktop_index}"
            }
        except Exception as e:
            return {"status": "error", "message": f"Move failed: {str(e)}"}

# --- Usage Example ---
if __name__ == "__main__":
    wm = WindowManager()
    
    # 1. See what's open
    print("Open Windows:", wm.list_open_windows()['windows'][:3], "...")
    
    # 2. Test Smart Search & Interaction (Safe Test: Notepad)
    # Open Notepad manually first to test this!
    # print(wm.maximize_window("Notepad"))
    # time.sleep(1)
    # print(wm.minimize_window("Notepad"))
    
    # 3. Test Desktops
    # print(wm.list_desktops())
    # print(wm.switch_desktop(2)) # Be careful, this will actually switch your screen!