# tools/window_tools.py
import subprocess
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

    Features:
    - Session-scoped window IDs for reliable window targeting
    - Smart search fallback for partial name matching
    - Filters out invisible system windows
    """

    # Windows to skip (invisible/system windows that clutter listings)
    # These are partial matches (case-insensitive)
    SKIP_TITLES = [
        # Windows system junk
        'Program Manager', 'Settings', 'Microsoft Text Input Application',
        'Windows Input Experience', 'DesktopWindowXamlSource',
        'MSCTFIME UI', 'Default IME', 'MediaContextNotificationWindow',
        'legacy window', 'helper', 'notification', 'widget',
        # Input/focus system windows
        'CoreInput', 'Non Client Input Sink', 'Input Sink',
        'Running applications', 'Filter Control',
        # Glass/visual effect windows
        'Glass Window',
        # Task Manager internals
        'TaskManagerMain',
        # Explorer shell internals (but not File Explorer windows)
        'Namespace Tree Control', 'Navigation Pane', 'ShellView',
        'ReunionCaptionControlsWindow',
        # Adobe Acrobat internals
        'TopTabBarContainerViewForDocs', 'AVUITopRightCommandCluster',
        'AVTabLinksContainerViewForDocs', 'AVTabsContainerView',
        'AVDocumentMainView', 'AVTaskPaneHostView', 'AVFlipContainerView',
        'AVTaskPaneView', 'AVScrollView', 'AppsCefView',
        'AVTaskPanelTableContainerView', 'AVTableContainerView',
        'AVTaskPaneBarView', 'AVExpandCollapseButtonView',
        'AVDocumentHeaderView',
    ]

    # Common app shortcuts for quick launch (same as SystemTools for consistency)
    APP_SHORTCUTS = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "explorer": "explorer.exe",
        "cmd": "cmd.exe",
        "powershell": "powershell.exe",
        "chrome": r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        "edge": "msedge.exe",
        "firefox": r"C:\Program Files\Mozilla Firefox\firefox.exe",
        "code": "code",
        "vscode": "code",
    }

    def __init__(self):
        # Cache maps simple IDs (1, 2, 3) to Window objects
        self._window_cache: Dict[int, pywinctl.Window] = {}

    # Generic/internal window names that are usually child windows or shell components
    GENERIC_TITLES = [
        'Downloads', 'Documents', 'Pictures', 'Videos', 'Music', 'Desktop',
    ]

    def _is_real_window(self, win: pywinctl.Window) -> bool:
        """Filters out invisible system windows and clutter."""
        if not win.title:
            return False

        # Check visibility
        try:
            if not win.isVisible:
                return False
        except Exception:
            pass  # Some windows don't support isVisible

        # Check window size - very small windows are usually system components
        try:
            width = win.width
            height = win.height
            if width < 50 or height < 50:
                return False
        except Exception:
            pass

        title = win.title
        title_lower = title.lower()

        # Filter by skip list (partial match)
        for skip in self.SKIP_TITLES:
            if skip.lower() in title_lower:
                return False

        # Filter exact matches of generic folder names (these are shell components)
        # Real File Explorer windows have " - File Explorer" suffix
        if title in self.GENERIC_TITLES:
            return False

        return True

    def _get_window(self, query: Union[int, str]) -> Optional[pywinctl.Window]:
        """
        Smart resolver: Accepts window ID (int) OR title (str).
        Priority:
        1. ID match from cache (fastest, most reliable)
        2. ID as string (e.g., LLM sends "1" instead of 1)
        3. Title search fallback (legacy compatibility)
        """
        # 1. Try ID Match (Fastest & Most Reliable)
        if isinstance(query, int):
            return self._window_cache.get(query)

        # 2. Try ID inside String (e.g., LLM sends "1")
        if isinstance(query, str) and query.isdigit():
            return self._window_cache.get(int(query))

        # 3. Fallback to Title Search (Legacy/Slow)
        return self._find_window(query)

    def _find_window(self, query: str) -> Optional[pywinctl.Window]:
        """
        Private helper: Finds the best matching window object by title.
        Priority:
        1. Exact Match (Title)
        2. Case-insensitive Substring (Title) - prefers real windows
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
            # Filter out system/helper windows
            real_windows = [
                w for w in matches
                if not any(skip.lower() in w.title.lower() for skip in self.SKIP_TITLES)
            ]

            # Prefer real windows, fall back to all matches
            candidates = real_windows if real_windows else matches

            # Sort by title length (longer titles usually mean main windows)
            candidates.sort(key=lambda x: len(x.title), reverse=True)
            return candidates[0]

        return None

    # --- WINDOW COMMANDS ---

    def list_open_windows(self) -> Dict[str, Union[List[str], int, str]]:
        """
        Lists windows and assigns them temporary IDs for the session.
        Returns a clean list: "1. Notepad", "2. Chrome - YouTube"

        The IDs can be used with other commands (focus_window, minimize_window, etc.)
        for reliable window targeting.
        """
        try:
            self._window_cache.clear()  # Reset cache on every fresh list

            raw_windows = pywinctl.getAllWindows()
            clean_list = []
            id_counter = 1

            for win in raw_windows:
                if self._is_real_window(win):
                    self._window_cache[id_counter] = win
                    clean_list.append(f"{id_counter}. {win.title}")
                    id_counter += 1

            return {
                "status": "success",
                "action": "list_windows",
                "windows": clean_list,
                "count": len(clean_list),
                "note": "Use these IDs (1, 2, etc.) with focus_window, minimize_window, etc."
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # --- APP LAUNCHER WITH AUTO-FOCUS ---

    def launch_app(self, app_name: str) -> Dict[str, str]:
        """
        Launches an application and waits for its window to appear, then focuses it.

        This solves the "time gap" problem where:
        1. Python launches the process instantly
        2. Windows takes ~500ms+ to create the window
        3. Trying to focus immediately fails

        Uses a polling loop to wait for the window to appear (up to 5 seconds).

        Args:
            app_name: Application name (e.g., "notepad", "chrome") or full path

        Returns:
            Dict with status and message
        """
        # Resolve shortcut or use as-is
        executable = self.APP_SHORTCUTS.get(app_name.lower(), app_name)

        try:
            # 1. Launch the process
            proc = subprocess.Popen(
                executable,
                shell=True,  # Allow PATH resolution
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
            pid = proc.pid

            # 2. Wait for the window to appear (Max 5 seconds)
            # We poll every 0.2s to see if a matching window exists
            found_window = None
            start_time = time.time()

            while time.time() - start_time < 5.0:
                # Refresh our internal window list
                self.list_open_windows()

                # Strategy: Look for a window containing the app name
                # (e.g., "notepad" matches "Untitled - Notepad")
                app_name_lower = app_name.lower()

                for win_id, win in self._window_cache.items():
                    if app_name_lower in win.title.lower():
                        found_window = win_id
                        break

                if found_window:
                    break

                time.sleep(0.2)

            # 3. Focus it if found
            if found_window:
                # Give it a tiny moment to finish rendering
                time.sleep(0.3)
                focus_result = self.focus_window(found_window)

                if focus_result.get("status") == "success":
                    return {
                        "status": "success",
                        "action": "launch",
                        "target": focus_result.get("target", {"app_name": app_name}),
                        "message": f"Launched and focused: {app_name}",
                        "pid": pid
                    }
                else:
                    return {
                        "status": "success",
                        "action": "launch",
                        "target": {"app_name": app_name},
                        "message": f"Launched {app_name} (focus attempt: {focus_result.get('message')})",
                        "pid": pid
                    }
            else:
                return {
                    "status": "success",
                    "action": "launch",
                    "target": {"app_name": app_name},
                    "message": f"Launched {app_name}, but could not find window to focus (timed out)",
                    "pid": pid
                }

        except FileNotFoundError:
            return {"status": "error", "message": f"App executable not found: {executable}"}
        except Exception as e:
            return {"status": "error", "message": f"Failed to launch {app_name}: {e}"}

    def focus_window(self, window_id: Union[int, str] = None, app_name: str = None) -> Dict[str, str]:
        """
        Brings a window to the front using low-level OS calls.
        Uses ctypes to bypass Windows Focus Stealing Prevention.

        Args:
            window_id: Window ID from list_windows (preferred) OR window title
            app_name: Legacy parameter, same as window_id (for backward compatibility)
        """
        query = window_id if window_id is not None else app_name
        if query is None:
            return {"status": "error", "message": "Must provide window_id or app_name"}

        target = self._get_window(query)
        if not target:
            return {"status": "error", "message": f"Window '{query}' not found. Run list_windows first to get IDs."}

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

            # Find the ID for this window
            win_id = None
            for wid, win in self._window_cache.items():
                if win == target:
                    win_id = wid
                    break
            return {
                "status": "success",
                "action": "focus",
                "target": {"id": win_id, "title": target.title},
                "message": f"Focused: {target.title}"
            }
        except Exception as e:
            # Fallback to pyautogui method
            try:
                pyautogui.press('alt')
                target.activate()
                win_id = None
                for wid, win in self._window_cache.items():
                    if win == target:
                        win_id = wid
                        break
                return {
                    "status": "success",
                    "action": "focus",
                    "target": {"id": win_id, "title": target.title},
                    "message": f"Focused (fallback): {target.title}"
                }
            except Exception as e2:
                return {"status": "error", "message": f"Could not focus window: {str(e)} / {str(e2)}"}

    def minimize_window(self, window_id: Union[int, str] = None, app_name: str = None) -> Dict[str, str]:
        """
        Minimizes a window.

        Args:
            window_id: Window ID from list_windows (preferred) OR window title
            app_name: Legacy parameter (for backward compatibility)
        """
        query = window_id if window_id is not None else app_name
        if query is None:
            return {"status": "error", "message": "Must provide window_id or app_name"}

        target = self._get_window(query)
        if not target:
            return {"status": "error", "message": f"Window '{query}' not found."}

        try:
            win_id = None
            for wid, win in self._window_cache.items():
                if win == target:
                    win_id = wid
                    break
            target.minimize()
            return {
                "status": "success",
                "action": "minimize",
                "target": {"id": win_id, "title": target.title},
                "message": f"Minimized: {target.title}"
            }
        except Exception as e:
            return {"status": "error", "action": "minimize", "message": str(e)}

    def maximize_window(self, window_id: Union[int, str] = None, app_name: str = None) -> Dict[str, str]:
        """
        Maximizes a window.

        Args:
            window_id: Window ID from list_windows (preferred) OR window title
            app_name: Legacy parameter (for backward compatibility)
        """
        query = window_id if window_id is not None else app_name
        if query is None:
            return {"status": "error", "message": "Must provide window_id or app_name"}

        target = self._get_window(query)
        if not target:
            return {"status": "error", "message": f"Window '{query}' not found."}

        try:
            win_id = None
            for wid, win in self._window_cache.items():
                if win == target:
                    win_id = wid
                    break
            target.maximize()
            return {
                "status": "success",
                "action": "maximize",
                "target": {"id": win_id, "title": target.title},
                "message": f"Maximized: {target.title}"
            }
        except Exception as e:
            return {"status": "error", "action": "maximize", "message": str(e)}

    def close_window(self, window_id: Union[int, str] = None, app_name: str = None) -> Dict[str, str]:
        """
        Closes a window. Warning: This works like clicking 'X'.

        Args:
            window_id: Window ID from list_windows (preferred) OR window title
            app_name: Legacy parameter (for backward compatibility)
        """
        query = window_id if window_id is not None else app_name
        if query is None:
            return {"status": "error", "message": "Must provide window_id or app_name"}

        target = self._get_window(query)
        if not target:
            return {"status": "error", "message": f"Window '{query}' not found."}

        try:
            win_id = None
            for wid, win in self._window_cache.items():
                if win == target:
                    win_id = wid
                    break
            title = target.title
            target.close()
            return {
                "status": "success",
                "action": "close",
                "target": {"id": win_id, "title": title},
                "message": f"Closed: {title}"
            }
        except Exception as e:
            return {"status": "error", "action": "close", "message": str(e)}

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
                return {
                    "status": "success",
                    "action": "type_text",
                    "target": {"text_length": len(text)},
                    "message": f"Pasted text via clipboard ({len(text)} chars)"
                }
            else:
                # Type method (more reliable for short text)
                pyautogui.write(text, interval=0.02)  # Small delay between keys
                return {
                    "status": "success",
                    "action": "type_text",
                    "target": {"text_length": len(text)},
                    "message": f"Typed: {text[:50]}{'...' if len(text) > 50 else ''}"
                }
        except Exception as e:
            return {"status": "error", "message": f"Failed to type text: {str(e)}"}

    # --- BATCH OPERATIONS ---

    # Windows Shell components that should NEVER be minimized
    SHELL_SAFE_LIST = [
        "Program Manager",  # Desktop background
        "Windows Explorer",  # File browser
        "Taskbar",  # Taskbar
    ]

    def minimize_all(self, filter_name: str = None) -> Dict[str, Union[str, int]]:
        """
        Safely minimizes applications, keeping Desktop and Explorer visible.

        Args:
            filter_name: Optional - only minimize windows containing this text.
                        If None, minimizes ALL app windows (keeps shell safe).

        Examples:
            minimize_all() -> minimizes all apps (keeps Explorer visible)
            minimize_all("chrome") -> minimizes all Chrome windows
        """
        try:
            count = 0
            skipped = 0
            all_windows = pywinctl.getAllWindows()

            for win in all_windows:
                # Skip non-real windows
                if not self._is_real_window(win):
                    continue

                # SAFETY: Never minimize shell components
                if win.title in self.SHELL_SAFE_LIST:
                    continue
                if "Explorer" in win.title and "File Explorer" not in win.title:
                    # Skip Windows Explorer shell, but allow File Explorer windows
                    continue

                # Filter check
                if filter_name:
                    if filter_name.lower() not in win.title.lower():
                        skipped += 1
                        continue

                # Only minimize visible, non-minimized windows
                try:
                    if win.isVisible and not win.isMinimized:
                        win.minimize()
                        count += 1
                except Exception:
                    skipped += 1  # Some windows can't be minimized

            msg = f"Minimized {count} windows"
            if filter_name:
                msg += f" matching '{filter_name}'"
            msg += " (kept Explorer visible)"

            return {
                "status": "success",
                "action": "minimize_all",
                "target": {"filter": filter_name} if filter_name else {},
                "message": msg,
                "count": count
            }
        except Exception as e:
            return {"status": "error", "message": f"minimize_all failed: {str(e)}"}

    def restore_all(self) -> Dict[str, Union[str, int]]:
        """
        The 'Undo' button - restores all minimized windows.
        Use this if you accidentally minimized too many windows.
        """
        try:
            count = 0
            all_windows = pywinctl.getAllWindows()

            for win in all_windows:
                if not self._is_real_window(win):
                    continue

                try:
                    if win.isMinimized:
                        win.restore()
                        count += 1
                except Exception:
                    pass

            return {
                "status": "success",
                "action": "restore_all",
                "message": f"Restored {count} windows.",
                "count": count
            }
        except Exception as e:
            return {"status": "error", "action": "restore_all", "message": f"restore_all failed: {str(e)}"}

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
                if any(skip.lower() in win.title.lower() for skip in self.SKIP_TITLES):
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
            return {
                "status": "success",
                "action": "maximize_all",
                "target": {"filter": filter_name} if filter_name else {},
                "message": msg,
                "count": count
            }
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
                "action": "list_desktops",
                "count": count,
                "current_index": current,
                "note": "Indexes start at 1"
            }
        except Exception as e:
            return {"status": "error", "action": "list_desktops", "message": f"Desktop API failed: {str(e)}"}

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
            return {
                "status": "success",
                "action": "switch_desktop",
                "target": {"desktop_index": index},
                "message": f"Switched to Desktop {index}"
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def move_window_to_desktop(
        self,
        desktop_index: int,
        window_id: Union[int, str] = None,
        app_name: str = None
    ) -> Dict[str, str]:
        """
        Moves a specific window to another desktop.

        Args:
            desktop_index: Target desktop (1-indexed)
            window_id: Window ID from list_windows (preferred) OR window title
            app_name: Legacy parameter (for backward compatibility)
        """
        # Validate desktop_index is an integer
        if not isinstance(desktop_index, int):
            try:
                desktop_index = int(desktop_index)
            except (ValueError, TypeError):
                return {"status": "error", "message": f"desktop_index must be an integer, got: {desktop_index}"}

        query = window_id if window_id is not None else app_name
        if query is None:
            return {"status": "error", "message": "Must provide window_id or app_name"}

        target = self._get_window(query)
        if not target:
            return {"status": "error", "message": f"Window '{query}' not found."}

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
            win_id = None
            for wid, win in self._window_cache.items():
                if win == target:
                    win_id = wid
                    break
            return {
                "status": "success",
                "action": "move_window",
                "target": {"id": win_id, "title": target.title, "desktop_index": desktop_index},
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