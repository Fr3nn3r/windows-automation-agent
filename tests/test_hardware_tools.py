"""Unit tests for hardware_tools module."""
import pytest
from unittest.mock import patch, MagicMock

# Test imports
def test_import_hardware_tools():
    """Test that hardware_tools module can be imported."""
    try:
        from tools.hardware_tools import HardwareController
        assert HardwareController is not None
    except ImportError as e:
        pytest.fail(f"Failed to import HardwareController: {e}")


def test_import_screen_brightness_control():
    """Test that screen_brightness_control is available."""
    try:
        import screen_brightness_control as sbc
        assert sbc is not None
    except ImportError as e:
        pytest.fail(f"Failed to import screen_brightness_control: {e}")


class TestHardwareController:
    """Tests for HardwareController class."""

    @pytest.fixture
    def controller(self):
        """Create a HardwareController instance."""
        from tools.hardware_tools import HardwareController
        return HardwareController()

    def test_instantiation(self, controller):
        """Test that HardwareController can be instantiated."""
        assert controller is not None

    def test_set_brightness_has_method(self, controller):
        """Test that set_brightness method exists."""
        assert hasattr(controller, 'set_brightness')
        assert callable(controller.set_brightness)

    def test_get_brightness_has_method(self, controller):
        """Test that get_brightness method exists."""
        assert hasattr(controller, 'get_brightness')
        assert callable(controller.get_brightness)

    def test_turn_screen_off_has_method(self, controller):
        """Test that turn_screen_off method exists."""
        assert hasattr(controller, 'turn_screen_off')
        assert callable(controller.turn_screen_off)

    def test_turn_screen_on_has_method(self, controller):
        """Test that turn_screen_on method exists."""
        assert hasattr(controller, 'turn_screen_on')
        assert callable(controller.turn_screen_on)

    @patch('tools.hardware_tools.sbc')
    def test_set_brightness_valid_level(self, mock_sbc, controller):
        """Test set_brightness with valid level."""
        result = controller.set_brightness(50)
        assert result['status'] == 'success'
        assert 'level' in result

    @patch('tools.hardware_tools.sbc')
    def test_set_brightness_clamps_high(self, mock_sbc, controller):
        """Test set_brightness clamps values above 100."""
        result = controller.set_brightness(150)
        assert result['status'] == 'success'
        assert result['level'] == 100

    @patch('tools.hardware_tools.sbc')
    def test_set_brightness_clamps_low(self, mock_sbc, controller):
        """Test set_brightness clamps values below 0."""
        result = controller.set_brightness(-50)
        assert result['status'] == 'success'
        assert result['level'] == 0

    @patch('tools.hardware_tools.sbc')
    def test_get_brightness_returns_dict(self, mock_sbc, controller):
        """Test get_brightness returns proper format."""
        mock_sbc.get_brightness.return_value = [50]
        result = controller.get_brightness()
        assert isinstance(result, dict)
        assert 'status' in result

    def test_set_brightness_returns_dict(self, controller):
        """Test set_brightness returns a dictionary."""
        result = controller.set_brightness(50)
        assert isinstance(result, dict)
        assert 'status' in result

    @pytest.mark.skip(reason="Actually turns off the screen - run manually if needed")
    def test_turn_screen_off_returns_dict(self, controller):
        """Test turn_screen_off returns a dictionary."""
        # Note: This actually sends the signal, so we just check return format
        result = controller.turn_screen_off()
        assert isinstance(result, dict)
        assert 'status' in result
