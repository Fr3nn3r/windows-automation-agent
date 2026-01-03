import os
import shutil
import psutil
import wmi
import platform
import socket
from typing import Dict, List, Union, Optional

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
                
            return {"status": "success", "path": target_path, "items": annotated}
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
            return {"status": "success", "message": f"File created at {target_path}"}
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
                return {"status": "error", "message": "Path not found."}
                
            return {"status": "success", "message": f"Deleted: {target_path}"}
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
            return {"status": "success", "data": info}
        except Exception as e:
            return {"status": "error", "message": str(e)}

    def get_environment_variable(self, var_name: str) -> Dict[str, Union[str, List[str]]]:
        """Gets a specific env var. If 'PATH', returns a list."""
        try:
            val = os.environ.get(var_name)
            if not val:
                return {"status": "error", "message": "Variable not found"}
            
            # Special handling for PATH to make it readable
            if var_name.upper() == "PATH":
                return {"status": "success", "value": val.split(os.pathsep)}
            
            return {"status": "success", "value": val}
        except Exception as e:
            return {"status": "error", "message": str(e)}

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
                
            return {"status": "success", "count": len(matches), "processes": matches}
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
            
            return {"status": "success", "devices": unique_devices}
        except Exception as e:
            return {"status": "error", "message": str(e)}

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