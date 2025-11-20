"""Configuration for Qlik Cloud MCP Server."""

import os
from typing import Optional
from pydantic import BaseModel, Field


class QlikSenseConfig(BaseModel):
    """
    Configuration model for Qlik Cloud server connection.

    Handles server connection details and API key authentication.
    """

    server_url: str = Field(..., description="Qlik Cloud server URL (e.g., https://tenant.qlikcloud.com)")
    api_key: str = Field(..., description="API key for authentication (required)")
    verify_ssl: bool = Field(True, description="Verify SSL certificates")

    @classmethod
    def from_env(cls) -> "QlikSenseConfig":
        """
        Create configuration instance from environment variables.

        Reads required configuration values from environment variables with QLIK_ prefix.

        Returns:
            Configured QlikSenseConfig instance
        """
        api_key = os.getenv("QLIK_API_KEY")
        if not api_key:
            raise ValueError("QLIK_API_KEY environment variable is required for Qlik Cloud")
        
        return cls(
            server_url=os.getenv("QLIK_SERVER_URL", ""),
            api_key=api_key,
            verify_ssl=os.getenv("QLIK_VERIFY_SSL", "true").lower() == "true"
        )
