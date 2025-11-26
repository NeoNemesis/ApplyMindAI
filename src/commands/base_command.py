"""
Base command class for JobCraftAI command pattern
All commands inherit from this base class
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pathlib import Path
from loguru import logger


class BaseCommand(ABC):
    """
    Abstract base class for all commands.

    Each command represents a user action from the main menu and should:
    1. Validate inputs
    2. Execute the main logic
    3. Return results
    4. Handle errors gracefully
    """

    def __init__(self, parameters: Dict[str, Any]):
        """
        Initialize command with parameters.

        Args:
            parameters: Dictionary containing all necessary parameters
        """
        self.parameters = parameters
        self.logger = logger

    @abstractmethod
    def execute(self) -> bool:
        """
        Execute the command.

        Returns:
            bool: True if command executed successfully, False otherwise
        """
        pass

    @abstractmethod
    def validate(self) -> bool:
        """
        Validate command parameters before execution.

        Returns:
            bool: True if parameters are valid, False otherwise

        Raises:
            ValueError: If parameters are invalid with descriptive message
        """
        pass

    def pre_execute(self) -> bool:
        """
        Hook method called before execute().
        Override to add custom pre-execution logic.

        Returns:
            bool: True to continue execution, False to abort
        """
        return True

    def post_execute(self, success: bool) -> None:
        """
        Hook method called after execute().
        Override to add custom post-execution logic.

        Args:
            success: Whether the execute() method succeeded
        """
        pass

    def run(self) -> bool:
        """
        Main entry point for command execution.
        Handles validation, execution, and error handling.

        Returns:
            bool: True if command completed successfully, False otherwise
        """
        try:
            # Validate parameters
            self.logger.info(f"🔍 Validating {self.__class__.__name__}...")
            if not self.validate():
                self.logger.error("❌ Validation failed")
                return False

            # Pre-execution hook
            if not self.pre_execute():
                self.logger.warning("⚠️  Pre-execution check failed, aborting")
                return False

            # Execute command
            self.logger.info(f"▶️  Executing {self.__class__.__name__}...")
            success = self.execute()

            # Post-execution hook
            self.post_execute(success)

            if success:
                self.logger.info(f"✅ {self.__class__.__name__} completed successfully")
            else:
                self.logger.error(f"❌ {self.__class__.__name__} failed")

            return success

        except Exception as e:
            self.logger.error(f"💥 {self.__class__.__name__} error: {e}")
            self.logger.exception(e)
            return False

    def _get_required_param(self, key: str, param_type: type = str) -> Any:
        """
        Get a required parameter and validate its type.

        Args:
            key: Parameter key
            param_type: Expected type of parameter

        Returns:
            The parameter value

        Raises:
            ValueError: If parameter is missing or has wrong type
        """
        if key not in self.parameters:
            raise ValueError(f"Missing required parameter: '{key}'")

        value = self.parameters[key]

        if not isinstance(value, param_type):
            raise ValueError(
                f"Parameter '{key}' has wrong type. "
                f"Expected {param_type.__name__}, got {type(value).__name__}"
            )

        return value

    def _get_optional_param(self, key: str, default: Any = None, param_type: Optional[type] = None) -> Any:
        """
        Get an optional parameter with type validation.

        Args:
            key: Parameter key
            default: Default value if parameter is missing
            param_type: Expected type of parameter (if provided)

        Returns:
            The parameter value or default

        Raises:
            ValueError: If parameter has wrong type
        """
        if key not in self.parameters:
            return default

        value = self.parameters[key]

        if param_type is not None and value is not None:
            if not isinstance(value, param_type):
                raise ValueError(
                    f"Parameter '{key}' has wrong type. "
                    f"Expected {param_type.__name__}, got {type(value).__name__}"
                )

        return value

    def _validate_file_exists(self, file_path: Path, file_description: str = "File") -> bool:
        """
        Validate that a file exists.

        Args:
            file_path: Path to file
            file_description: Human-readable description of file

        Returns:
            bool: True if file exists

        Raises:
            ValueError: If file does not exist
        """
        if not file_path.exists():
            raise ValueError(f"{file_description} does not exist: {file_path}")

        if not file_path.is_file():
            raise ValueError(f"{file_description} is not a file: {file_path}")

        return True
