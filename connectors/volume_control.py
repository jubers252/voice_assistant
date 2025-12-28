"""
Simple Volume Control Module
Provides functions to control system volume on Linux using PulseAudio
"""

import subprocess
import logging

logger = logging.getLogger(__name__)


class VolumeController:
    """Control system volume using PulseAudio commands"""
    
    def __init__(self):
        """Initialize the volume controller"""
        self.min_volume = 0
        self.max_volume = 100
    
    def get_current_volume(self):
        """
        Get the current system volume level
        
        Returns:
            int: Current volume percentage (0-100)
        """
        try:
            result = subprocess.run(
                ["pactl", "get-sink-volume", "@DEFAULT_SINK@"],
                capture_output=True,
                text=True,
                check=True
            )
            # Parse output: "Volume: front-left: 65536 / 100%  front-right: 65536 / 100%"
            for word in result.stdout.split():
                if word.endswith("%"):
                    volume = int(word.rstrip("%"))
                    return volume
        except (subprocess.CalledProcessError, ValueError, IndexError) as e:
            logger.error(f"Error getting volume: {e}")
            return None
    
    def set_volume(self, level):
        """
        Set the system volume to a specific level
        
        Args:
            level (int): Volume level (0-100)
            
        Returns:
            bool: True if successful, False otherwise
        """
        if not 0 <= level <= 100:
            logger.warning(f"Volume level {level} out of range (0-100)")
            return False
        
        try:
            subprocess.run(
                ["pactl", "set-sink-volume", "@DEFAULT_SINK@", f"{level}%"],
                check=True
            )
            logger.info(f"Volume set to {level}%")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Error setting volume: {e}")
            return False
    
    def increase_volume(self, step=5):
        """
        Increase volume by a certain step
        
        Args:
            step (int): Amount to increase (default: 5%)
            
        Returns:
            int: New volume level, or None if error
        """
        current = self.get_current_volume()
        if current is None:
            return None
        
        new_volume = min(current + step, self.max_volume)
        if self.set_volume(new_volume):
            return new_volume
        return None
    
    def decrease_volume(self, step=5):
        """
        Decrease volume by a certain step
        
        Args:
            step (int): Amount to decrease (default: 5%)
            
        Returns:
            int: New volume level, or None if error
        """
        current = self.get_current_volume()
        if current is None:
            return None
        
        new_volume = max(current - step, self.min_volume)
        if self.set_volume(new_volume):
            return new_volume
        return None
    
    def mute(self):
        """
        Mute the system volume
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            subprocess.run(
                ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "1"],
                check=True
            )
            logger.info("Volume muted")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Error muting: {e}")
            return False
    
    def unmute(self):
        """
        Unmute the system volume
        
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            subprocess.run(
                ["pactl", "set-sink-mute", "@DEFAULT_SINK@", "0"],
                check=True
            )
            logger.info("Volume unmuted")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Error unmuting: {e}")
            return False
    
    def is_muted(self):
        """
        Check if the system volume is muted
        
        Returns:
            bool: True if muted, False if not, None if error
        """
        try:
            result = subprocess.run(
                ["pactl", "get-sink-mute", "@DEFAULT_SINK@"],
                capture_output=True,
                text=True,
                check=True
            )
            # Output: "Mute: yes" or "Mute: no"
            return "yes" in result.stdout.lower()
        except subprocess.CalledProcessError as e:
            logger.error(f"Error checking mute status: {e}")
            return None


# Create a global instance
volume_controller = VolumeController()


# Convenience functions
def get_volume():
    """Get current volume level"""
    return volume_controller.get_current_volume()


def set_volume(level):
    """Set volume to specific level"""
    return volume_controller.set_volume(level)


def increase_volume(step=5):
    """Increase volume by step"""
    return volume_controller.increase_volume(step)


def decrease_volume(step=5):
    """Decrease volume by step"""
    return volume_controller.decrease_volume(step)


def mute():
    """Mute volume"""
    return volume_controller.mute()


def unmute():
    """Unmute volume"""
    return volume_controller.unmute()


def is_muted():
    """Check if muted"""
    return volume_controller.is_muted()

def main_control(action, step=10, level=None):
    """
    Main control function for volume operations
    
    Args:
        action (str): Action to perform (increase, decrease, set, mute, unmute, status)
        step (int): Step size for increase/decrease operations
        level (int): Target volume level for set operation
        
    Returns:
        int: Volume level for increase/decrease/status
        bool: True/False for mute/unmute operations
        dict: Status dictionary with volume and muted state for status action
    """
    if action == "increase":
        return increase_volume(step)
    elif action == "decrease":
        return decrease_volume(step)
    elif action == "set":
        if level is not None:
            return set_volume(level)
        else:
            logger.warning("Set action requires a level parameter")
            return False
    elif action == "mute":
        return mute()
    elif action == "unmute":
        return unmute()
    elif action == "status":
        return {
            "volume": get_volume(),
            "muted": is_muted()
        }
    else:
        logger.warning(f"Invalid action specified: {action}")
        return None

if __name__ == "__main__":
    # Example usage
    logging.basicConfig(level=logging.INFO)
    
    print(f"Current volume: {get_volume()}%")
    print(f"Is muted: {is_muted()}")
    
    # print("\nIncreasing volume by 10%...")
    # new_vol = increase_volume(10)
    # print(f"New volume: {new_vol}%")
    
    new_vol = decrease_volume(10)
    print(f"New volume: {new_vol}%")
    # print("\nSetting volume to 50%...")
    # set_volume(50)
    # print(f"Current volume: {get_volume()}%")
    
    # print("\nMuting...")
    # mute()
    # print(f"Is muted: {is_muted()}")
    
    # print("\nUnmuting...")
    # unmute()
    # print(f"Is muted: {is_muted()}")
