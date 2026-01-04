import os
import shutil
import subprocess
import psutil
import wmi
import platform
import socket
from typing import Dict, List, Union, Optional

import pyperclip

class SystemTools:
    """
    Manages Files, Processes, and System Information.
    Includes strict safety guardrails for file deletion.
    """

    def __init__(self):
        self.wmi_client = wmi.WMI()

    # --- FILE SYSTEM COMMANDS ---

    def list_directory(self, path: str = ".") -> Dict[str, Union[List[str], str]]:
        """
        Lists files and folders in a directory. 
        Safely handles permission errors.
        """
        try:
            # Expand ~ to user home directory
            target_path = os.path.expanduser(path)
            
            if not os.path.exists(target_path):
                return {"status": "error", "message": "Path does not exist."}
                
            items = os.listdir(target_path)
            # Annotate items (File vs Dir) for the agent's clarity
            annotated = []
            for item in items[:50]: # Limit to 50 to prevent context flooding
                full = os.path.join(target_path, item)
                kind = "DIR" if os.path.isdir(full) else "FILE"
                annotated.append(f"[{kind}] {item}")
                
            if len(items) > 50:
                annotated.append(f"... (+{len(items)-50} more)")
                
            return {
                "status": "success",
                "action": "list_directory",
                "target": {"path": target_path},
                "path": target_path,
                "items": annotated
            }
        except PermissionError:
            return {"status": "error", "message": "Access Denied"}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def create_file(self, path: str, content: str = "") -> Dict[str, str]:
        """Creates a new file with text content."""
        try:
            target_path = os.path.expanduser(path)
            with open(target_path, 'w', encoding='utf-8') as f:
                f.write(content)
            return {
                "status": "success",
                "action": "create_file",
                "target": {"path": target_path},
                "message": f"File created at {target_path}"
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def delete_item(self, path: str, confirm: bool = False) -> Dict[str, str]:
        """
        DANGEROUS: Deletes a file or folder.
        Requires 'confirm=True' to execute.
        """
        if not confirm:
            return {
                "status": "blocked", 
                "message": "SAFETY LOCK: You must set 'confirm=True' to delete items."
            }
        
        target_path = os.path.expanduser(path)
        
        # Hardcoded Guardrail: Prevent deletion of C: root or Windows folder
        if target_path.lower() in ["c:\\", "c:\\windows", "/"]:
             return {"status": "error", "message": "CRITICAL SAFETY: Cannot delete system roots."}

        try:
            if os.path.isfile(target_path):
                os.remove(target_path)
            elif os.path.isdir(target_path):
                shutil.rmtree(target_path)
            else:
                return {"status": "error", "action": "delete_item", "message": "Path not found."}

            return {
                "status": "success",
                "action": "delete_item",
                "target": {"path": target_path},
                "message": f"Deleted: {target_path}"
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    # --- PROCESS & SYSTEM INFO ---

    def get_system_info(self) -> Dict[str, str]:
        """Returns OS, Hostname, and IP info."""
        try:
            info = {
                "os": f"{platform.system()} {platform.release()}",
                "hostname": socket.gethostname(),
                "ip_address": socket.gethostbyname(socket.gethostname()),
                "cpu_usage": f"{psutil.cpu_percent()}%",
                "memory_usage": f"{psutil.virtual_memory().percent}%"
            }
            return {
                "status": "success",
                "action": "get_system_info",
                "data": info
            }
        except Exception as e:
            return {"status": "error", "action": "get_system_info", "message": str(e)}

    def get_environment_variable(self, var_name: str) -> Dict[str, Union[str, List[str]]]:
        """Gets a specific env var. If 'PATH', returns a list."""
        try:
            val = os.environ.get(var_name)
            if not val:
                return {"status": "error", "action": "get_env", "message": "Variable not found"}

            # Special handling for PATH to make it readable
            if var_name.upper() == "PATH":
                return {
                    "status": "success",
                    "action": "get_env",
                    "target": {"var_name": var_name},
                    "value": val.split(os.pathsep)
                }

            return {
                "status": "success",
                "action": "get_env",
                "target": {"var_name": var_name},
                "value": val
            }
        except Exception as e:
            return {"status": "error", "action": "get_env", "message": str(e)}

    def list_processes(self, filter_name: str = None) -> Dict[str, List[dict]]:
        """
        Lists running processes. 
        If filter_name is provided, matches partial names (e.g. 'chrome').
        """
        matches = []
        try:
            # We iterate only essential attributes to be fast
            for proc in psutil.process_iter(['pid', 'name', 'username']):
                p_info = proc.info
                if filter_name:
                    if filter_name.lower() in p_info['name'].lower():
                        matches.append(p_info)
                else:
                    matches.append(p_info)
            
            # Limit results if no filter to avoid flooding
            if not filter_name:
                matches = matches[:20]

            return {
                "status": "success",
                "action": "list_processes",
                "target": {"filter": filter_name} if filter_name else {},
                "count": len(matches),
                "processes": matches
            }
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def list_usb_devices(self) -> Dict[str, List[str]]:
        """
        Uses WMI to list connected USB devices.
        """
        try:
            # Win32_PnPEntity is the most reliable place for this
            # We filter for "USB" in the DeviceID to reduce noise
            devices = self.wmi_client.query("SELECT * FROM Win32_PnPEntity WHERE DeviceID LIKE '%USB%'")
            
            device_list = []
            for dev in devices:
                # Get the friendly name or description
                name = getattr(dev, "Name", "Unknown")
                status = getattr(dev, "Status", "Unknown")
                device_list.append(f"{name} [{status}]")
                
            # Filter out duplicates (common in WMI)
            unique_devices = list(set(device_list))

            return {
                "status": "success",
                "action": "list_usb",
                "count": len(unique_devices),
                "devices": unique_devices
            }
        except Exception as e:
            return {"status": "error", "action": "list_usb", "message": str(e)}

    # --- DIRECTORY NAVIGATION ---

    def change_directory(self, path: str) -> Dict[str, str]:
        """
        Changes the agent's working directory.
        Returns the new absolute path for context update.

        Args:
            path: Target directory (supports ~ for home, relative paths)
        """
        try:
            target_path = os.path.expanduser(path)

            # Resolve relative paths
            if not os.path.isabs(target_path):
                target_path = os.path.abspath(target_path)

            if not os.path.exists(target_path):
                return {
                    "status": "error",
                    "action": "change_directory",
                    "message": f"Path does not exist: {target_path}"
                }

            if not os.path.isdir(target_path):
                return {
                    "status": "error",
                    "action": "change_directory",
                    "message": f"Not a directory: {target_path}"
                }

            os.chdir(target_path)
            return {
                "status": "success",
                "action": "change_directory",
                "target": {"path": target_path},
                "message": f"Changed to: {target_path}"
            }
        except PermissionError:
            return {
                "status": "error",
                "action": "change_directory",
                "message": f"Access denied: {path}"
            }
        except Exception as e:
            return {
                "status": "error",
                "action": "change_directory",
                "message": str(e)
            }

    # --- APP LAUNCHER ---

    # Common app shortcuts for quick launch
    APP_SHORTCUTS = {
        "notepad": "notepad.exe",
        "calculator": "calc.exe",
        "calc": "calc.exe",
        "explorer": "explorer.exe",
        "cmd": "cmd.exe",
        "powershell": "powershell.exe",
        "chrome": "chrome.exe",
        "edge": "msedge.exe",
        "firefox": "firefox.exe",
        "code": "code",
        "vscode": "code",
    }

    def launch_app(self, app_name: str) -> Dict[str, Union[str, int]]:
        """
        Launch an application by name or path.
        Uses subprocess.Popen for non-blocking execution.

        Args:
            app_name: Application name (e.g., "notepad", "calc") or full path

        Returns:
            Dict with status, message, and pid if successful
        """
        try:
            # Resolve shortcut or use as-is
            executable = self.APP_SHORTCUTS.get(app_name.lower(), app_name)

            # Launch non-blocking
            process = subprocess.Popen(
                executable,
                shell=True,  # Allow PATH resolution
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )

            return {
                "status": "success",
                "action": "launch_app",
                "target": {"app_name": app_name},
                "message": f"Launched: {app_name}",
                "pid": process.pid
            }
        except Exception as e:
            return {"status": "error", "action": "launch_app", "message": f"Failed to launch {app_name}: {e}"}

    def open_explorer(self, path: str = ".") -> Dict[str, str]:
        """
        Open Windows Explorer at a specific path.
        Uses os.startfile for native Windows behavior.

        Args:
            path: Directory path to open (defaults to current directory)

        Returns:
            Dict with status and message
        """
        try:
            target_path = os.path.expanduser(path)

            if not os.path.exists(target_path):
                return {"status": "error", "message": f"Path does not exist: {target_path}"}

            if not os.path.isdir(target_path):
                # If it's a file, open its parent directory
                target_path = os.path.dirname(target_path)

            os.startfile(target_path)

            return {
                "status": "success",
                "action": "open_explorer",
                "target": {"path": target_path},
                "message": f"Opened Explorer at: {target_path}"
            }
        except Exception as e:
            return {"status": "error", "action": "open_explorer", "message": f"Failed to open Explorer: {e}"}

    # --- CLIPBOARD ---

    def get_clipboard(self) -> Dict[str, Union[str, int]]:
        """
        Get the current clipboard text content.

        Returns:
            Dict with status and clipboard content
        """
        try:
            content = pyperclip.paste()

            # Truncate if too long to prevent context flooding
            original_length = len(content)
            if original_length > 1000:
                content = content[:1000] + "... [truncated]"

            return {
                "status": "success",
                "action": "get_clipboard",
                "content": content,
                "length": original_length
            }
        except Exception as e:
            return {"status": "error", "action": "get_clipboard", "message": f"Failed to read clipboard: {e}"}

    def set_clipboard(self, text: str) -> Dict[str, str]:
        """
        Set text to the clipboard.

        Args:
            text: Text to copy to clipboard

        Returns:
            Dict with status and message
        """
        try:
            pyperclip.copy(text)

            return {
                "status": "success",
                "action": "set_clipboard",
                "target": {"text_length": len(text)},
                "message": f"Copied {len(text)} characters to clipboard"
            }
        except Exception as e:
            return {"status": "error", "action": "set_clipboard", "message": f"Failed to set clipboard: {e}"}

# --- Usage Example ---
if __name__ == "__main__":
    sys_tools = SystemTools()
    
    # 1. Process Check
    # print(sys_tools.list_processes("python"))
    
    # 2. USB Check
    # print(sys_tools.list_usb_devices())
    
    # 3. Env Var Check (PATH)
    # path_data = sys_tools.get_environment_variable("PATH")
    # print(f"Path entries: {len(path_data.get('value', []))}")