import ctypes
import time
import screen_brightness_control as sbc
from typing import Dict, Union, Optional

# Win32 API Constants (The "Magic Numbers" for Windows)
HWND_BROADCAST = 0xFFFF
WM_SYSCOMMAND = 0x0112
SC_MONITORPOWER = 0xF170

# Power States
MONITOR_ON = -1
MONITOR_OFF = 2
MONITOR_STANDBY = 1

class HardwareController:
    """
    A deterministic controller for physical hardware capabilities.
    Uses 'ctypes' for direct Windows API calls and 'screen_brightness_control'
    for DDC/CI communication with monitors.
    """

    def set_brightness(self, level: int, monitor_index: Optional[int] = None) -> Dict[str, str]:
        """
        Sets the screen brightness (0-100).
        If monitor_index is None, sets it for all detected screens.
        """
        try:
            # Clamp value between 0 and 100 to prevent errors
            level = max(0, min(100, level))
            
            if monitor_index is not None:
                sbc.set_brightness(level, display=monitor_index)
                msg = f"Set brightness to {level}% on monitor {monitor_index}."
            else:
                sbc.set_brightness(level)
                msg = f"Set brightness to {level}% on all monitors."
            
            return {"status": "success", "message": msg, "level": level}
            
        except Exception as e:
            return {"status": "error", "message": f"Failed to set brightness: {str(e)}"}

    def get_brightness(self) -> Dict[str, Union[str, list]]:
        """Returns the current brightness level(s)."""
        try:
            current = sbc.get_brightness()
            return {"status": "success", "brightness": current}
        except Exception as e:
            return {"status": "error", "message": f"Could not read brightness: {str(e)}"}

    def turn_screen_off(self) -> Dict[str, str]:
        """
        Sends a specific system command to put the monitor to sleep immediately.
        Note: The script does NOT block; it sends the signal and returns.
        """
        try:
            # We use SendMessage via ctypes to broadcast the 'Power Off' event.
            # This mimics the OS power management signal.
            ctypes.windll.user32.SendMessageW(
                HWND_BROADCAST, 
                WM_SYSCOMMAND, 
                SC_MONITORPOWER, 
                MONITOR_OFF
            )
            return {"status": "success", "message": "Monitor power-off signal sent."}
        except Exception as e:
            return {"status": "error", "message": f"Failed to turn off screen: {str(e)}"}

    def turn_screen_on(self) -> Dict[str, str]:
        """
        Wakes the screen up. 
        Reliably waking Windows requires simulating a tiny input event, 
        as simply sending the 'On' signal is sometimes ignored by modern drivers.
        """
        try:
            # Strategy 1: Send the internal 'On' signal
            ctypes.windll.user32.SendMessageW(
                HWND_BROADCAST, 
                WM_SYSCOMMAND, 
                SC_MONITORPOWER, 
                MONITOR_ON
            )
            
            # Strategy 2: Jiggle the mouse 1 pixel (The most reliable wake method)
            # This forces the OS out of the "Away" state.
            mouse_event = ctypes.windll.user32.mouse_event
            MOUSEEVENTF_MOVE = 0x0001
            mouse_event(MOUSEEVENTF_MOVE, 0, 1, 0, 0) # Move 1 unit down
            time.sleep(0.05)
            mouse_event(MOUSEEVENTF_MOVE, 0, -1, 0, 0) # Move 1 unit up
            
            return {"status": "success", "message": "Monitor wake signal sent (input simulated)."}
        except Exception as e:
            return {"status": "error", "message": f"Failed to wake screen: {str(e)}"}

# --- Usage Example (For your testing) ---
if __name__ == "__main__":
    hw = HardwareController()
    
    # 1. Check Brightness
    print(hw.get_brightness())
    
    # 2. Dim Screen (Safety test)
    # hw.set_brightness(50)
    
    # 3. Turn off screen (Uncomment to test - moving mouse will wake it)
    # print("Turning screen off in 3 seconds...")
    # time.sleep(3)
    # hw.turn_screen_off()