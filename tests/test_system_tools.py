"""Unit tests for system_tools module."""
import pytest
import os
import tempfile
from unittest.mock import patch, MagicMock


# Test imports
def test_import_system_tools():
    """Test that system_tools module can be imported."""
    try:
        from tools.system_tools import SystemTools
        assert SystemTools is not None
    except ImportError as e:
        pytest.fail(f"Failed to import SystemTools: {e}")


def test_import_psutil():
    """Test that psutil is available."""
    try:
        import psutil
        assert psutil is not None
    except ImportError as e:
        pytest.fail(f"Failed to import psutil: {e}")


def test_import_wmi():
    """Test that wmi is available."""
    try:
        import wmi
        assert wmi is not None
    except ImportError as e:
        pytest.fail(f"Failed to import wmi: {e}")


class TestSystemTools:
    """Tests for SystemTools class."""

    @pytest.fixture
    def tools(self):
        """Create a SystemTools instance."""
        from tools.system_tools import SystemTools
        return SystemTools()

    def test_instantiation(self, tools):
        """Test that SystemTools can be instantiated."""
        assert tools is not None

    def test_has_wmi_client(self, tools):
        """Test that SystemTools has WMI client."""
        assert hasattr(tools, 'wmi_client')
        assert tools.wmi_client is not None

    # --- Method existence tests ---

    def test_list_directory_method_exists(self, tools):
        """Test that list_directory method exists."""
        assert hasattr(tools, 'list_directory')
        assert callable(tools.list_directory)

    def test_create_file_method_exists(self, tools):
        """Test that create_file method exists."""
        assert hasattr(tools, 'create_file')
        assert callable(tools.create_file)

    def test_delete_item_method_exists(self, tools):
        """Test that delete_item method exists."""
        assert hasattr(tools, 'delete_item')
        assert callable(tools.delete_item)

    def test_get_system_info_method_exists(self, tools):
        """Test that get_system_info method exists."""
        assert hasattr(tools, 'get_system_info')
        assert callable(tools.get_system_info)

    def test_get_environment_variable_method_exists(self, tools):
        """Test that get_environment_variable method exists."""
        assert hasattr(tools, 'get_environment_variable')
        assert callable(tools.get_environment_variable)

    def test_list_processes_method_exists(self, tools):
        """Test that list_processes method exists."""
        assert hasattr(tools, 'list_processes')
        assert callable(tools.list_processes)

    def test_list_usb_devices_method_exists(self, tools):
        """Test that list_usb_devices method exists."""
        assert hasattr(tools, 'list_usb_devices')
        assert callable(tools.list_usb_devices)

    # --- Functional tests ---

    def test_list_directory_current(self, tools):
        """Test list_directory with current directory."""
        result = tools.list_directory(".")
        assert result['status'] == 'success'
        assert 'items' in result
        assert isinstance(result['items'], list)

    def test_list_directory_home(self, tools):
        """Test list_directory with home directory."""
        result = tools.list_directory("~")
        assert result['status'] == 'success'
        assert 'items' in result

    def test_list_directory_nonexistent(self, tools):
        """Test list_directory with non-existent path."""
        result = tools.list_directory("/nonexistent/path/12345")
        assert result['status'] == 'error'

    def test_list_directory_downloads(self, tools):
        """Test list_directory with Downloads folder."""
        result = tools.list_directory("~/Downloads")
        assert isinstance(result, dict)
        assert 'status' in result

    def test_get_system_info_returns_dict(self, tools):
        """Test get_system_info returns proper format."""
        result = tools.get_system_info()
        assert isinstance(result, dict)
        assert 'status' in result

    def test_get_system_info_success(self, tools):
        """Test get_system_info succeeds."""
        result = tools.get_system_info()
        assert result['status'] == 'success'
        assert 'data' in result
        data = result['data']
        assert 'os' in data
        assert 'hostname' in data
        assert 'cpu_usage' in data
        assert 'memory_usage' in data

    def test_list_processes_returns_dict(self, tools):
        """Test list_processes returns proper format."""
        result = tools.list_processes()
        assert isinstance(result, dict)
        assert 'status' in result

    def test_list_processes_success(self, tools):
        """Test list_processes succeeds."""
        result = tools.list_processes()
        assert result['status'] == 'success'
        assert 'processes' in result
        assert isinstance(result['processes'], list)

    def test_list_processes_with_filter(self, tools):
        """Test list_processes with filter."""
        result = tools.list_processes(filter_name="python")
        assert result['status'] == 'success'
        assert 'processes' in result

    def test_get_environment_variable_path(self, tools):
        """Test get_environment_variable with PATH."""
        result = tools.get_environment_variable("PATH")
        assert result['status'] == 'success'
        assert 'value' in result
        assert isinstance(result['value'], list)

    def test_get_environment_variable_nonexistent(self, tools):
        """Test get_environment_variable with non-existent var."""
        result = tools.get_environment_variable("NONEXISTENT_VAR_12345")
        assert result['status'] == 'error'

    def test_delete_item_safety_lock(self, tools):
        """Test delete_item requires confirm=True."""
        result = tools.delete_item("/some/path")
        assert result['status'] == 'blocked'
        assert 'SAFETY LOCK' in result['message']

    def test_delete_item_system_protection(self, tools):
        """Test delete_item protects system paths."""
        result = tools.delete_item("C:\\", confirm=True)
        assert result['status'] == 'error'
        assert 'CRITICAL SAFETY' in result['message']

    def test_delete_item_windows_protection(self, tools):
        """Test delete_item protects Windows folder."""
        result = tools.delete_item("C:\\Windows", confirm=True)
        assert result['status'] == 'error'

    def test_create_and_delete_file(self, tools):
        """Test creating and deleting a file."""
        # Create a temp file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.txt') as f:
            temp_path = f.name

        try:
            # Delete the temp file to test create
            os.remove(temp_path)

            # Create file
            result = tools.create_file(temp_path, "test content")
            assert result['status'] == 'success'
            assert os.path.exists(temp_path)

            # Verify content
            with open(temp_path, 'r') as f:
                assert f.read() == "test content"

            # Delete file
            result = tools.delete_item(temp_path, confirm=True)
            assert result['status'] == 'success'
            assert not os.path.exists(temp_path)

        finally:
            # Cleanup just in case
            if os.path.exists(temp_path):
                os.remove(temp_path)

    def test_list_usb_devices_returns_dict(self, tools):
        """Test list_usb_devices returns proper format."""
        result = tools.list_usb_devices()
        assert isinstance(result, dict)
        assert 'status' in result
