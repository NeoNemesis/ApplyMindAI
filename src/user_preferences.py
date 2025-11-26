"""
User Preferences Manager
Saves and loads user preferences to avoid repetitive questions.
"""
import json
from pathlib import Path
from typing import Optional, Dict
from src.logger_config import logger


class UserPreferences:
    """Manages persistent user preferences."""
    
    PREFERENCES_FILE = Path("data_folder/user_preferences.json")
    
    @classmethod
    def load(cls) -> Dict:
        """Load user preferences from file."""
        if not cls.PREFERENCES_FILE.exists():
            logger.debug("No preferences file found, using defaults")
            return {}
        
        try:
            with open(cls.PREFERENCES_FILE, 'r', encoding='utf-8') as f:
                prefs = json.load(f)
            logger.info(f"✅ Loaded preferences: {list(prefs.keys())}")
            return prefs
        except Exception as e:
            logger.warning(f"Failed to load preferences: {e}")
            return {}
    
    @classmethod
    def save(cls, preferences: Dict) -> bool:
        """Save user preferences to file."""
        try:
            cls.PREFERENCES_FILE.parent.mkdir(parents=True, exist_ok=True)
            with open(cls.PREFERENCES_FILE, 'w', encoding='utf-8') as f:
                json.dump(preferences, f, indent=2, ensure_ascii=False)
            logger.info("💾 Preferences saved")
            return True
        except Exception as e:
            logger.error(f"Failed to save preferences: {e}")
            return False
    
    @classmethod
    def get(cls, key: str, default=None):
        """Get a specific preference value."""
        prefs = cls.load()
        return prefs.get(key, default)
    
    @classmethod
    def set(cls, key: str, value):
        """Set a specific preference value."""
        prefs = cls.load()
        prefs[key] = value
        cls.save(prefs)
    
    @classmethod
    def clear(cls):
        """Clear all preferences."""
        if cls.PREFERENCES_FILE.exists():
            cls.PREFERENCES_FILE.unlink()
            logger.info("🗑️ Preferences cleared")
