"""Unit tests for windows_tools module."""
import pytest
from unittest.mock import patch, MagicMock


# Test imports
def test_import_windows_tools():
    """Test that windows_tools module can be imported."""
    try:
        from tools.windows_tools import WindowManager
        assert WindowManager is not None
    except ImportError as e:
        pytest.fail(f"Failed to import WindowManager: {e}")


def test_import_pywinctl():
    """Test that pywinctl is available."""
    try:
        import pywinctl
        assert pywinctl is not None
    except ImportError as e:
        pytest.fail(f"Failed to import pywinctl: {e}")


def test_import_pyvda():
    """Test that pyvda is available."""
    try:
        import pyvda
        assert pyvda is not None
    except ImportError as e:
        pytest.fail(f"Failed to import pyvda: {e}")


class TestPyvdaAPI:
    """Tests to verify pyvda API compatibility."""

    def test_pyvda_has_get_virtual_desktops(self):
        """Test that pyvda has get_virtual_desktops function."""
        import pyvda
        assert hasattr(pyvda, 'get_virtual_desktops'), \
            "pyvda missing get_virtual_desktops - API may have changed"

    def test_pyvda_has_get_virtual_desktop_count(self):
        """Test that pyvda has get_virtual_desktop_count function."""
        import pyvda
        # Check both possible names
        has_count = hasattr(pyvda, 'get_virtual_desktop_count')
        has_desktops = hasattr(pyvda, 'get_virtual_desktops')
        assert has_count or has_desktops, \
            "pyvda missing desktop count functions"

    def test_pyvda_virtual_desktop_class(self):
        """Test that pyvda has VirtualDesktop class."""
        import pyvda
        assert hasattr(pyvda, 'VirtualDesktop'), \
            "pyvda missing VirtualDesktop class"

    def test_pyvda_get_current_desktop(self):
        """Test that pyvda VirtualDesktop has current() class method."""
        import pyvda
        # The current desktop is accessed via VirtualDesktop.current()
        assert hasattr(pyvda.VirtualDesktop, 'current'), \
            "pyvda.VirtualDesktop missing current() class method"

    def test_pyvda_available_functions(self):
        """List all available pyvda functions for debugging."""
        import pyvda
        public_attrs = [attr for attr in dir(pyvda) if not attr.startswith('_')]
        print(f"\nAvailable pyvda attributes: {public_attrs}")
        assert len(public_attrs) > 0


class TestWindowManager:
    """Tests for WindowManager class."""

    @pytest.fixture
    def manager(self):
        """Create a WindowManager instance."""
        from tools.windows_tools import WindowManager
        return WindowManager()

    def test_instantiation(self, manager):
        """Test that WindowManager can be instantiated."""
        assert manager is not None

    def test_list_open_windows_method_exists(self, manager):
        """Test that list_open_windows method exists."""
        assert hasattr(manager, 'list_open_windows')
        assert callable(manager.list_open_windows)

    def test_focus_window_method_exists(self, manager):
        """Test that focus_window method exists."""
        assert hasattr(manager, 'focus_window')
        assert callable(manager.focus_window)

    def test_minimize_window_method_exists(self, manager):
        """Test that minimize_window method exists."""
        assert hasattr(manager, 'minimize_window')
        assert callable(manager.minimize_window)

    def test_maximize_window_method_exists(self, manager):
        """Test that maximize_window method exists."""
        assert hasattr(manager, 'maximize_window')
        assert callable(manager.maximize_window)

    def test_close_window_method_exists(self, manager):
        """Test that close_window method exists."""
        assert hasattr(manager, 'close_window')
        assert callable(manager.close_window)

    def test_list_desktops_method_exists(self, manager):
        """Test that list_desktops method exists."""
        assert hasattr(manager, 'list_desktops')
        assert callable(manager.list_desktops)

    def test_switch_desktop_method_exists(self, manager):
        """Test that switch_desktop method exists."""
        assert hasattr(manager, 'switch_desktop')
        assert callable(manager.switch_desktop)

    def test_move_window_to_desktop_method_exists(self, manager):
        """Test that move_window_to_desktop method exists."""
        assert hasattr(manager, 'move_window_to_desktop')
        assert callable(manager.move_window_to_desktop)

    def test_launch_app_method_exists(self, manager):
        """Test that launch_app method exists (poll-and-focus feature)."""
        assert hasattr(manager, 'launch_app')
        assert callable(manager.launch_app)

    def test_launch_app_has_app_shortcuts(self, manager):
        """Test that WindowManager has APP_SHORTCUTS for common apps."""
        assert hasattr(manager, 'APP_SHORTCUTS')
        assert isinstance(manager.APP_SHORTCUTS, dict)
        assert 'notepad' in manager.APP_SHORTCUTS
        assert 'chrome' in manager.APP_SHORTCUTS

    def test_list_open_windows_returns_dict(self, manager):
        """Test list_open_windows returns proper format."""
        result = manager.list_open_windows()
        assert isinstance(result, dict)
        assert 'status' in result

    def test_list_open_windows_success(self, manager):
        """Test list_open_windows succeeds."""
        result = manager.list_open_windows()
        assert result['status'] == 'success'
        assert 'windows' in result
        assert isinstance(result['windows'], list)

    def test_focus_window_not_found(self, manager):
        """Test focus_window with non-existent window."""
        result = manager.focus_window("NonExistentWindow12345")
        assert result['status'] == 'error'

    def test_minimize_window_not_found(self, manager):
        """Test minimize_window with non-existent window."""
        result = manager.minimize_window("NonExistentWindow12345")
        assert result['status'] == 'error'

    def test_list_desktops_returns_dict(self, manager):
        """Test list_desktops returns proper format."""
        result = manager.list_desktops()
        assert isinstance(result, dict)
        assert 'status' in result

    def test_switch_desktop_invalid_index(self, manager):
        """Test switch_desktop with invalid index."""
        result = manager.switch_desktop(999)
        assert result['status'] == 'error'

    def test_switch_desktop_zero_index(self, manager):
        """Test switch_desktop with zero index (should fail, 1-based)."""
        result = manager.switch_desktop(0)
        assert result['status'] == 'error'
