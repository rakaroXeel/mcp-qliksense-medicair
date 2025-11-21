"""Main MCP Server for Qlik Sense APIs."""

import asyncio
import json
import sys
from typing import Any, Dict, List, Optional
from mcp.server import Server
from mcp.server.models import InitializationOptions
from mcp.server.stdio import stdio_server
from mcp.types import ServerCapabilities, Tool
from mcp.types import CallToolResult, TextContent

from .config import QlikSenseConfig
from .cloud_api import QlikCloudAPI

import logging
import os
from dotenv import load_dotenv

# Initialize logging configuration early
load_dotenv()
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Configure root logger to stderr (stdout reserved for MCP protocol)
_logging_level = getattr(logging, LOG_LEVEL, logging.INFO)
if not logging.getLogger().handlers:
    handler = logging.StreamHandler(stream=sys.stderr)
    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)
    logging.getLogger().addHandler(handler)
logging.getLogger().setLevel(_logging_level)
logger = logging.getLogger(__name__)


class QlikSenseMCPServer:
    """MCP Server for Qlik Cloud APIs."""

    def __init__(self):
        try:
            self.config = QlikSenseConfig.from_env()
            self.config_valid = self._validate_config()
        except Exception as e:
            self.config = None
            self.config_valid = False

        # Initialize Cloud API client
        self.cloud_api = None

        if self.config_valid:
            try:
                self.cloud_api = QlikCloudAPI(self.config)
                logger.info(f"Cloud API initialized for {self.config.server_url}")
            except Exception as e:
                # API client will be None, tools will return errors
                logger.error(f"Failed to initialize Cloud API: {e}", exc_info=True)
                auth_method = "OAuth2 M2M" if self.config.uses_oauth() else ("API Key" if self.config.uses_api_key() else "None")
                logger.error(f"Config check - Server URL: {self.config.server_url}, Auth Method: {auth_method}")

        self.server = Server("qlik-sense-mcp-server")
        self._setup_handlers()

    def _validate_config(self) -> bool:
        """Validate that required configuration is present."""
        if not self.config:
            return False
        # Qlik Cloud requires either OAuth2 M2M credentials or API key
        has_server_url = bool(self.config.server_url)
        has_auth = self.config.uses_oauth() or self.config.uses_api_key()
        return bool(has_server_url and has_auth)

    def _setup_handlers(self):
        """Setup MCP server handlers."""

        @self.server.list_tools()
        async def handle_list_tools():
            """
            List all available MCP tools for Qlik Sense operations.

            Returns tool definitions with schemas for Repository API and Engine API operations
            including applications, analytics tools, and data export.
            """
            tools_list = [
                Tool(
                    name="get_apps",
                    description="Get list of Qlik Sense applications with essential fields and filters (name, stream, published) and pagination.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of apps to return (default: 25, max: 50)",
                                "default": 25
                            },
                            "offset": {
                                "type": "integer",
                                "description": "Number of apps to skip for pagination (default: 0)",
                                "default": 0
                            },
                            "name": {
                                "type": "string",
                                "description": "Wildcard case-insensitive search in application name"
                            },
                            "stream": {
                                "type": "string",
                                "description": "Wildcard case-insensitive search in stream name"
                            },
                            "published": {
                                "type": "string",
                                "description": "Filter by published status (true/false or 1/0). Default: true",
                                "default": "true"
                            }
                        }
                    }
                ),
                Tool(
                    name="get_app_details",
                    description="Get application details including metadata and information.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "app_id": {"type": "string", "description": "Application ID"}
                        },
                        "required": ["app_id"]
                    }
                )
                ]
            return tools_list

        async def handle_call_tool_internal(name: str, arguments: Dict[str, Any]):
            # Check configuration before processing any tool calls
            if not self.config_valid:
                error_msg = {
                    "error": "Qlik Cloud configuration missing",
                    "message": "Please set the following environment variables:",
                    "required": [
                        "QLIK_SERVER_URL - Qlik Cloud server URL (e.g., https://tenant.qlikcloud.com)",
                        "Either:",
                        "  - QLIK_OAUTH_CLIENT_ID and QLIK_OAUTH_CLIENT_SECRET (OAuth2 M2M, preferred)",
                        "  - QLIK_API_KEY (API key authentication, fallback)"
                    ],
                    "example_oauth": "uvx --with-env QLIK_SERVER_URL=https://tenant.qlikcloud.com --with-env QLIK_OAUTH_CLIENT_ID=your-client-id --with-env QLIK_OAUTH_CLIENT_SECRET=your-client-secret qlik-sense-mcp-server",
                    "example_api_key": "uvx --with-env QLIK_SERVER_URL=https://tenant.qlikcloud.com --with-env QLIK_API_KEY=your-api-key qlik-sense-mcp-server"
                }
                return [TextContent(type="text", text=json.dumps(error_msg, indent=2))]
            """
            Handle MCP tool calls by routing to appropriate API handlers.

            Args:
                name: Tool name to execute
                arguments: Tool-specific parameters

            Returns:
                TextContent with JSON response from Qlik Sense APIs
            """
            try:
                if name == "get_apps":
                    limit = arguments.get("limit", 25)
                    offset = arguments.get("offset", 0)
                    name_filter = arguments.get("name")
                    stream_filter = arguments.get("stream")
                    published_arg = arguments.get("published", True)

                    if limit is None or limit < 1:
                        limit = 25
                    if limit > 50:
                        limit = 50

                    # Qlik Cloud API
                    if not self.cloud_api:
                        return [TextContent(type="text", text=json.dumps({"error": "Cloud API not initialized"}, indent=2, ensure_ascii=False))]
                    
                    def _get_cloud_apps():
                        result = self.cloud_api.get_apps(
                            limit=limit,
                            offset=offset,
                            name=name_filter,
                            space_id=stream_filter  # Use stream_filter as space_id
                        )
                        if "error" in result:
                            return result
                        
                        # Transform Cloud API response
                        apps_data = result.get("data", [])
                        apps_list = []
                        for app in apps_data:
                            apps_list.append({
                                "id": app.get("id"),
                                "name": app.get("name"),
                                "description": app.get("description"),
                                "space": app.get("space", {}).get("name") if app.get("space") else None,
                                "modifiedDate": app.get("updatedAt"),
                                "published": app.get("published", False),
                                "resourceType": app.get("resourceType", "app")
                            })
                        
                        return {
                            "apps": apps_list,
                            "total": result.get("total", len(apps_list)),
                            "limit": limit,
                            "offset": offset
                        }
                    
                    result = await asyncio.to_thread(_get_cloud_apps)
                    return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]

                elif name == "get_app_details":
                    app_id = arguments.get("app_id")
                    
                    if not self.cloud_api:
                        return [TextContent(type="text", text=json.dumps({"error": "Cloud API not initialized"}, indent=2, ensure_ascii=False))]
                    
                    def _get_app_details():
                        """Get application details from Cloud API."""
                        try:
                            # Get app details
                            app_result = self.cloud_api.get_app(app_id)
                            if "error" in app_result:
                                return app_result
                            
                            # Get app metadata if available
                            metadata_result = self.cloud_api.get_app_metadata(app_id)
                            
                            result = {
                                "app_id": app_id,
                                "name": app_result.get("name"),
                                "description": app_result.get("description"),
                                "resourceType": app_result.get("resourceType"),
                                "space": app_result.get("space", {}).get("name") if app_result.get("space") else None,
                                "createdAt": app_result.get("createdAt"),
                                "updatedAt": app_result.get("updatedAt"),
                                "published": app_result.get("published", False),
                                "metadata": metadata_result if "error" not in metadata_result else None
                            }
                            
                            return result
                        except Exception as e:
                            return {"error": str(e)}

                    details = await asyncio.to_thread(_get_app_details)
                    return [
                        TextContent(type="text", text=json.dumps(details, indent=2, ensure_ascii=False))
                    ]

                else:
                    # Unknown tool - Enterprise-only tools are not available in Qlik Cloud
                    return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}. Available tools: get_apps, get_app_details"}, indent=2, ensure_ascii=False))]

            except Exception as e:
                return [TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2, ensure_ascii=False))]

        # Store handler for direct access before registering
        self._tool_handler = handle_call_tool_internal
        
        # Register the handler with MCP server
        @self.server.call_tool()
        async def handle_call_tool(name: str, arguments: Dict[str, Any]):
            return await handle_call_tool_internal(name, arguments)

    async def call_tool_direct(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """
        Call a tool directly and return the result as a dictionary.
        Useful for HTTP wrappers and programmatic access.
        """
        if not self.config_valid:
            return {"error": "Qlik Cloud configuration missing"}
        
        try:
            # Call the tool handler directly
            if not hasattr(self, '_tool_handler') or self._tool_handler is None:
                return {"error": "Tool handler not initialized"}
            
            result = await self._tool_handler(name, arguments)
            
            # Extract text content from result
            if result and len(result) > 0:
                text_content = result[0].text if hasattr(result[0], 'text') else str(result[0])
                try:
                    # Try to parse as JSON
                    return json.loads(text_content)
                except json.JSONDecodeError:
                    # Return as plain text if not JSON
                    return {"result": text_content}
            else:
                return {"result": None}
        except Exception as e:
            logger.error(f"Error in call_tool_direct for {name}: {e}", exc_info=True)
            return {"error": str(e)}

    async def run(self):
        """
        Start the MCP server with stdio transport.

        Initializes server capabilities and begins listening for MCP protocol messages
        over stdin/stdout for communication with MCP clients.
        """
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="qlik-sense-mcp-server",
                    server_version="1.3.4",
                    capabilities=ServerCapabilities(
                        tools={}
                    ),
                ),
            )


async def async_main():
    """
    Async main entry point for the Qlik Cloud MCP Server.

    Creates and starts the MCP server instance with configured
    Qlik Cloud REST API connections.
    """
    server = QlikSenseMCPServer()
    await server.run()


def main():
    """
    Synchronous entry point for CLI usage.

    This function is used as the entry point in pyproject.toml
    for the qlik-sense-mcp-server command.
    """
    # Handle command line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] in ["--help", "-h"]:
            print_help()
            return
        elif sys.argv[1] in ["--version", "-v"]:
            sys.stderr.write("qlik-sense-mcp-server 1.3.4\n")
            sys.stderr.flush()
            return

    asyncio.run(async_main())


def print_help():
    """Print help information using logging instead of print."""
    help_text = """
Qlik Cloud MCP Server - Model Context Protocol server for Qlik Cloud REST API

USAGE:
    qlik-sense-mcp-server [OPTIONS]
    uvx qlik-sense-mcp-server [OPTIONS]

OPTIONS:
    -h, --help     Show this help message
    -v, --version  Show version information

CONFIGURATION:
    Set these environment variables before running:

    QLIK_SERVER_URL       - Qlik Cloud server URL (required)
                           Example: https://tenant.qlikcloud.com

    Authentication (choose one method):
    
    Option 1 - OAuth2 M2M (preferred):
    QLIK_OAUTH_CLIENT_ID     - OAuth2 M2M client ID (required if not using API key)
    QLIK_OAUTH_CLIENT_SECRET - OAuth2 M2M client secret (required if not using API key)
    
    Option 2 - API Key (fallback):
    QLIK_API_KEY          - API key for authentication (required if not using OAuth2)
                           Example: your-api-key

EXAMPLE (OAuth2 M2M):
    export QLIK_SERVER_URL=https://tenant.qlikcloud.com
    export QLIK_OAUTH_CLIENT_ID=your-client-id
    export QLIK_OAUTH_CLIENT_SECRET=your-client-secret
    qlik-sense-mcp-server

EXAMPLE (API Key):
    export QLIK_SERVER_URL=https://tenant.qlikcloud.com
    export QLIK_API_KEY=your-api-key
    qlik-sense-mcp-server

AVAILABLE TOOLS:
    - get_apps: Get list of applications
    - get_app_details: Get application details
"""
    # Use stderr for help output to avoid mixing with MCP protocol output
    import sys
    sys.stderr.write(help_text + "\n")
    sys.stderr.flush()


if __name__ == "__main__":
    main()
