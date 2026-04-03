"""
Configuration Loader for Echo-Node

Loads and validates config.yaml. All pipeline behavior is driven by this config.
"""

import os
from pathlib import Path
from typing import Any
import yaml


class ConfigError(Exception):
    """Configuration validation error."""
    pass


class Config:
    """Echo-Node configuration."""

    def __init__(self, config_path: str | None = None):
        """
        Load and validate configuration.
        
        Args:
            config_path: Path to config.yaml (default: ./config.yaml or ./config.example.yaml)
        """
        self.config_path = config_path or self._find_config()
        self.raw: dict[str, Any] = {}
        self._load()
        self._validate()

    def _find_config(self) -> str:
        """Find config file in current directory or parent."""
        candidates = ["config.yaml", "config.example.yaml"]
        for candidate in candidates:
            if os.path.exists(candidate):
                return candidate
            # Check parent directory
            parent = Path(__file__).parent.parent / candidate
            if parent.exists():
                return str(parent)
        raise ConfigError("No config.yaml or config.example.yaml found")

    def _load(self) -> None:
        """Load YAML configuration."""
        with open(self.config_path, 'r') as f:
            self.raw = yaml.safe_load(f)

    def _validate(self) -> None:
        """Validate required configuration fields."""
        errors: list[str] = []

        # Required provider fields
        if not self.raw.get('stt', {}).get('provider'):
            errors.append("stt.provider is required")
        if not self.raw.get('tts', {}).get('provider'):
            errors.append("tts.provider is required")
        if not self.raw.get('llm', {}).get('provider'):
            errors.append("llm.provider is required")
        if not self.raw.get('wake_word', {}).get('provider'):
            errors.append("wake_word.provider is required")

        # Personality validation
        personality_cfg = self.raw.get('personality')
        if personality_cfg:
            active = personality_cfg.get('active', 'hacker')
            valid_personalities = [
                'hacker', 'seductive', 'butler', 'drill-sergeant',
                'stoner-philosopher', 'custom'
            ]
            if active not in valid_personalities:
                errors.append(
                    f"Invalid personality.active: {active}. "
                    f"Must be one of: {', '.join(valid_personalities)}"
                )
            if active == 'custom' and not personality_cfg.get('custom_prompt', '').strip():
                errors.append("custom_prompt is required when personality.active is 'custom'")

        # LLM validation
        llm = self.raw.get('llm', {})
        if llm.get('provider') == 'openai-compat' and not llm.get('api_key'):
            # OpenAI/OpenRouter require API key, Ollama doesn't
            if not llm.get('base_url', '').startswith('http://localhost'):
                errors.append("llm.api_key is required for cloud LLM providers")

        # Pipeline mode validation
        pipeline_mode = self.raw.get('pipeline_mode', 'local')
        if pipeline_mode not in ('local', 'cloud'):
            errors.append(f"Invalid pipeline_mode: {pipeline_mode}. Must be 'local' or 'cloud'")

        # Cloud mode requires API key
        if pipeline_mode == 'cloud':
            if not llm.get('api_key'):
                errors.append("llm.api_key is required for cloud pipeline mode")

        if errors:
            error_msg = "Configuration validation failed:\n" + "\n".join(f"  - {e}" for e in errors)
            raise ConfigError(error_msg)

    def get(self, *keys: str, default: Any = None) -> Any:
        """
        Get nested configuration value.
        
        Args:
            *keys: Nested keys (e.g., 'stt', 'provider')
            default: Default value if key not found
        
        Returns:
            Configuration value or default
        """
        value = self.raw
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        return value

    @property
    def pipeline_mode(self) -> str:
        """Get pipeline mode: 'local' or 'cloud'."""
        return self.raw.get('pipeline_mode', 'local')

    @property
    def stt_provider(self) -> str:
        """Get STT provider name."""
        return self.raw.get('stt', {}).get('provider', 'sherpa-onnx')

    @property
    def tts_provider(self) -> str:
        """Get TTS provider name."""
        return self.raw.get('tts', {}).get('provider', 'kokoro')

    @property
    def llm_provider(self) -> str:
        """Get LLM provider name."""
        return self.raw.get('llm', {}).get('provider', 'ollama')

    @property
    def wake_word_provider(self) -> str:
        """Get wake word provider name."""
        return self.raw.get('wake_word', {}).get('provider', 'openwakeword')

    @property
    def personality(self) -> str:
        """Get active personality name."""
        return self.raw.get('personality', {}).get('active', 'hacker')

    @property
    def custom_prompt(self) -> str:
        """Get custom personality prompt (used when active == 'custom')."""
        return self.raw.get('personality', {}).get('custom_prompt', '')

    @property
    def ui_mode(self) -> str:
        """Get UI mode: 'web' or 'headless'."""
        return self.raw.get('ui', {}).get('mode', 'web')

    def update(self, updates: dict[str, Any]) -> None:
        """
        Update configuration with new values.
        
        Args:
            updates: Nested dict of configuration updates
        """
        self._deep_update(self.raw, updates)
        self._validate()

    def _deep_update(self, base: dict, update: dict) -> None:
        """Recursively update nested dictionary."""
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_update(base[key], value)
            else:
                base[key] = value

    def to_dict(self) -> dict[str, Any]:
        """Get full configuration as dictionary."""
        return self.raw.copy()
