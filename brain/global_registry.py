from typing import Dict, Any, Optional
import logging

logger = logging.getLogger("qbrain.registry")

class GlobalRegistry:
    """
    Registry for global constants, environment variables, and bootstrap states.
    Used to provide cross-file semantic awareness during dataflow analysis.
    """
    def __init__(self):
        self.constants: Dict[str, Any] = {}
        self.env_vars: Dict[str, str] = {}
        self.file_origins: Dict[str, str] = {} # Maps constant name to the file it was defined in

    def register_constant(self, name: str, value: Any, origin: Optional[str] = None):
        """Register a global constant like PHP define()."""
        self.constants[name] = value
        if origin:
            self.file_origins[name] = origin
        logger.debug(f"Registered constant: {name} = {value} (from {origin})")

    def get_constant(self, name: str) -> Optional[Any]:
        """Retrieve a registered constant."""
        return self.constants.get(name)

    def register_env(self, name: str, value: str):
        """Register an environment variable or bootstrap state."""
        self.env_vars[name] = value
        logger.debug(f"Registered env var: {name} = {value}")

    def get_env(self, name: str) -> Optional[str]:
        """Retrieve a registered environment variable."""
        return self.env_vars.get(name)

    def get_origin(self, name: str) -> Optional[str]:
        """Retrieve the file where a constant was defined."""
        return self.file_origins.get(name)

    def has_constant(self, name: str) -> bool:
        """Check if a constant exists."""
        return name in self.constants

    def clear(self):
        """Clear all registered data."""
        self.constants.clear()
        self.env_vars.clear()
        self.file_origins.clear()
