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
from .engine_api import QlikEngineAPI
import traceback

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
        self.engine_api = None

        if self.config_valid:
            try:
                self.cloud_api = QlikCloudAPI(self.config)
                self.engine_api = QlikEngineAPI(self.config)
                logger.info(f"Cloud API initialized for {self.config.server_url}")
            except Exception as e:
                # API client will be None, tools will return errors
                logger.error(f"Failed to initialize Cloud API: {e}", exc_info=True)
                logger.error(f"Config check - Server URL: {self.config.server_url}, Auth Method: OAuth2 M2M")

        self.server = Server("qlik-sense-mcp-server")
        self._setup_handlers()

    def _validate_config(self) -> bool:
        """Validate that required configuration is present."""
        if not self.config:
            return False
        # Qlik Cloud requires OAuth2 M2M credentials
        has_server_url = bool(self.config.server_url)
        has_oauth = bool(self.config.oauth_client_id and self.config.oauth_client_secret)
        return bool(has_server_url and has_oauth)

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
                    description="Get application details including metadata, tables, and fields information.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "app_id": {"type": "string", "description": "Application ID"}
                        },
                        "required": ["app_id"]
                    }
                ),
                Tool(
                    name="get_app_tables",
                    description="Get list of tables in a Qlik Cloud application with field counts and row counts.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "app_id": {"type": "string", "description": "Application ID"}
                        },
                        "required": ["app_id"]
                    }
                ),
                Tool(
                    name="get_app_fields",
                    description="Get list of fields in a Qlik Cloud application, optionally filtered by table name.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "app_id": {"type": "string", "description": "Application ID"},
                            "table_name": {"type": "string", "description": "Optional table name to filter fields"}
                        },
                        "required": ["app_id"]
                    }
                ),
                Tool(
                    name="get_field_values",
                    description="Get distinct values of a specific field from a Qlik Cloud application.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "app_id": {"type": "string", "description": "Application ID"},
                            "field_name": {"type": "string", "description": "Name of the field"},
                            "limit": {"type": "integer", "description": "Maximum number of values to return (default: 100)", "default": 100}
                        },
                        "required": ["app_id", "field_name"]
                    }
                ),
                Tool(
                    name="get_app_data",
                    description="Get data from a Qlik Cloud application. Can read from a table or create a custom hypercube with dimensions and measures.",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "app_id": {"type": "string", "description": "Application ID"},
                            "table_name": {"type": "string", "description": "Name of the table to read data from (if provided, reads table data)"},
                            "dimensions": {"type": "array", "items": {"type": "string"}, "description": "List of dimension field names (for custom hypercube)"},
                            "measures": {"type": "array", "items": {"type": "string"}, "description": "List of measure expressions (for custom hypercube)"},
                            "limit": {"type": "integer", "description": "Maximum number of rows to return (default: 1000)", "default": 1000},
                            "offset": {"type": "integer", "description": "Number of rows to skip for pagination (default: 0)", "default": 0}
                        },
                        "required": ["app_id"]
                    }
                ),
                Tool(
                    name="health_check",
                    description="Check the health status of the Qlik Sense MCP Server. Returns server status, configuration validity, and authentication method.",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
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
                        "QLIK_OAUTH_CLIENT_ID - OAuth2 M2M client ID",
                        "QLIK_OAUTH_CLIENT_SECRET - OAuth2 M2M client secret"
                    ],
                    "example": "uvx --with-env QLIK_SERVER_URL=https://tenant.qlikcloud.com --with-env QLIK_OAUTH_CLIENT_ID=your-client-id --with-env QLIK_OAUTH_CLIENT_SECRET=your-client-secret qlik-sense-mcp-server"
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
                        # Fetch spaces map first to resolve names and types
                        spaces_map = {}
                        try:
                            # Fetch all spaces (limit 100 for now, could be paginated if needed)
                            spaces_result = self.cloud_api.get_spaces(limit=100)
                            if "data" in spaces_result:
                                for space in spaces_result["data"]:
                                    spaces_map[space["id"]] = {
                                        "name": space.get("name"),
                                        "type": space.get("type")
                                    }
                        except Exception as e:
                            logger.warning(f"Failed to fetch spaces for mapping: {e}")

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
                            space_id = app.get("spaceId")
                            space_info = spaces_map.get(space_id, {})
                            
                            # Determine published status
                            # 1. Check explicit 'published' flag in resourceAttributes
                            is_published = app.get("resourceAttributes", {}).get("published", False)
                            
                            # 2. If not explicitly published, check if it's in a managed space
                            if not is_published and space_info.get("type") == "managed":
                                is_published = True

                            apps_list.append({
                                "id": app.get("id"),
                                "name": app.get("name"),
                                "description": app.get("description"),
                                "space": space_info.get("name"),
                                "spaceId": space_id,
                                "modifiedDate": app.get("updatedAt"),
                                "published": is_published,
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
                            
                            # Get tables information
                            tables_result = self.cloud_api.get_app_tables(app_id)
                            tables_info = tables_result if "error" not in tables_result else None
                            
                            # Get fields information (summary)
                            fields_result = self.cloud_api.get_app_fields(app_id)
                            fields_info = fields_result if "error" not in fields_result else None
                            
                            result = {
                                "app_id": app_id,
                                "name": app_result.get("name"),
                                "description": app_result.get("description"),
                                "resourceType": app_result.get("resourceType"),
                                "space": app_result.get("space", {}).get("name") if app_result.get("space") else None,
                                "createdAt": app_result.get("createdAt"),
                                "updatedAt": app_result.get("updatedAt"),
                                "published": app_result.get("published", False),
                                "metadata": metadata_result if "error" not in metadata_result else None,
                                "tables": tables_info,
                                "fields_summary": {
                                    "total_fields": fields_info.get("total_fields", 0) if fields_info else 0,
                                    "field_count_by_table": {}
                                } if fields_info else None
                            }
                            
                            # Add field count by table if available
                            if fields_info and fields_info.get("fields"):
                                field_count_by_table = {}
                                for field in fields_info["fields"]:
                                    table_name = field.get("table", "Unknown")
                                    field_count_by_table[table_name] = field_count_by_table.get(table_name, 0) + 1
                                result["fields_summary"]["field_count_by_table"] = field_count_by_table
                            
                            return result
                        except Exception as e:
                            return {"error": str(e)}

                    details = await asyncio.to_thread(_get_app_details)
                    return [
                        TextContent(type="text", text=json.dumps(details, indent=2, ensure_ascii=False))
                    ]

                elif name == "get_app_tables":
                    app_id = arguments.get("app_id")
                    
                    if not self.cloud_api:
                        return [TextContent(type="text", text=json.dumps({"error": "Cloud API not initialized"}, indent=2, ensure_ascii=False))]
                    
                    def _get_app_tables():
                        return self.cloud_api.get_app_tables(app_id)
                    
                    result = await asyncio.to_thread(_get_app_tables)
                    return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]

                elif name == "get_app_fields":
                    app_id = arguments.get("app_id")
                    table_name = arguments.get("table_name")
                    
                    if not self.cloud_api:
                        return [TextContent(type="text", text=json.dumps({"error": "Cloud API not initialized"}, indent=2, ensure_ascii=False))]
                    
                    def _get_app_fields():
                        # First try REST API
                        result = self.cloud_api.get_app_fields(app_id, table_name)
                        
                        # Check if we have "Unknown" tables which indicates missing metadata
                        has_unknown_tables = False
                        if "fields" in result:
                            for field in result["fields"]:
                                if field.get("table") == "Unknown":
                                    has_unknown_tables = True
                                    break
                        
                        # If we have unknown tables and engine API is available, try fallback
                        if has_unknown_tables and self.engine_api:
                            try:
                                logger.info(f"REST API returned Unknown tables for app {app_id}, attempting Engine API fallback")
                                # Get OAuth token from cloud API
                                token = self.cloud_api._get_oauth_token()
                                
                                # Connect to engine with token
                                self.engine_api.connect(app_id, auth_token=token)
                                try:
                                    # Open doc and get fields
                                    # We need to open the doc first
                                    self.engine_api.open_doc(app_id)
                                    
                                    # Get fields from engine
                                    engine_result = self.engine_api.get_fields(handle=-1)
                                    
                                    if "fields" in engine_result and engine_result["fields"]:
                                        logger.info(f"Engine API returned {len(engine_result['fields'])} fields")
                                        
                                        # Map engine fields to common format
                                        mapped_fields = []
                                        for field in engine_result["fields"]:
                                            table = field.get("table_name", "Unknown")
                                            # Filter by table if requested
                                            if table_name and table != table_name:
                                                continue
                                                
                                            mapped_fields.append({
                                                "name": field.get("field_name"),
                                                "table": table,
                                                "type": field.get("data_type", "unknown"),
                                                "key_type": field.get("key_type"),
                                                "tags": field.get("tags", [])
                                            })
                                        
                                        if mapped_fields:
                                            return {
                                                "app_id": app_id,
                                                "fields": mapped_fields,
                                                "total_fields": len(mapped_fields),
                                                "source": "engine_api"
                                            }
                                finally:
                                    # Always disconnect
                                    self.engine_api.disconnect()
                            except Exception as e:
                                logger.error(f"Engine API fallback failed: {e}")
                                # Fall through to return original result
                                result["_fallback_error"] = str(e)
                                result["_fallback_trace"] = traceback.format_exc()
                        
                        return result
                    
                    result = await asyncio.to_thread(_get_app_fields)
                    return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]

                elif name == "get_field_values":
                    app_id = arguments.get("app_id")
                    field_name = arguments.get("field_name")
                    limit = arguments.get("limit", 100)
                    
                    if not self.cloud_api:
                        return [TextContent(type="text", text=json.dumps({"error": "Cloud API not initialized"}, indent=2, ensure_ascii=False))]
                    
                    def _get_field_values():
                        return self.cloud_api.get_field_values(app_id, field_name, limit)
                    
                    result = await asyncio.to_thread(_get_field_values)
                    return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]

                elif name == "get_app_data":
                    app_id = arguments.get("app_id")
                    table_name = arguments.get("table_name")
                    dimensions = arguments.get("dimensions")
                    measures = arguments.get("measures")
                    limit = arguments.get("limit", 1000)
                    offset = arguments.get("offset", 0)
                    
                    if not self.cloud_api:
                        return [TextContent(type="text", text=json.dumps({"error": "Cloud API not initialized"}, indent=2, ensure_ascii=False))]
                    
                    def _get_app_data():
                        # If table_name is provided, read table data
                        if table_name:
                            return self.cloud_api.get_table_data(app_id, table_name, limit, offset)
                        # If dimensions/measures are provided, create custom hypercube
                        elif dimensions or measures:
                            if not dimensions:
                                dimensions = []
                            if not measures:
                                measures = []
                            return self.cloud_api.create_hypercube(app_id, dimensions, measures, None, limit)
                        else:
                            return {"error": "Either table_name or dimensions/measures must be provided"}
                    
                    result = await asyncio.to_thread(_get_app_data)
                    return [TextContent(type="text", text=json.dumps(result, indent=2, ensure_ascii=False))]

                elif name == "health_check":
                    """Check server health status."""
                    try:
                        health_status = {
                            "status": "healthy" if self.config_valid else "unhealthy",
                            "server_url": self.config.server_url if self.config else None,
                            "config_valid": self.config_valid,
                            "has_oauth": bool(self.config and self.config.oauth_client_id and self.config.oauth_client_secret) if self.config else False,
                            "auth_method": "OAuth2 M2M" if self.config_valid else None,
                            "cloud_api_initialized": self.cloud_api is not None
                        }
                        
                        # Try to get OAuth token if API is initialized (to verify authentication works)
                        if self.cloud_api:
                            try:
                                # This will use cached token or fetch new one
                                token = self.cloud_api._get_oauth_token()
                                health_status["oauth_token_valid"] = bool(token)
                            except Exception as e:
                                health_status["oauth_token_valid"] = False
                                health_status["oauth_error"] = str(e)
                        else:
                            health_status["oauth_token_valid"] = False
                        
                        return [TextContent(type="text", text=json.dumps(health_status, indent=2, ensure_ascii=False))]
                    except Exception as e:
                        return [TextContent(type="text", text=json.dumps({"error": str(e)}, indent=2, ensure_ascii=False))]

                else:
                    # Unknown tool - Enterprise-only tools are not available in Qlik Cloud
                    return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}. Available tools: get_apps, get_app_details, get_app_tables, get_app_fields, get_field_values, get_app_data, health_check"}, indent=2, ensure_ascii=False))]

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

    QLIK_OAUTH_CLIENT_ID     - OAuth2 M2M client ID (required)
    QLIK_OAUTH_CLIENT_SECRET - OAuth2 M2M client secret (required)

EXAMPLE:
    export QLIK_SERVER_URL=https://tenant.qlikcloud.com
    export QLIK_OAUTH_CLIENT_ID=your-client-id
    export QLIK_OAUTH_CLIENT_SECRET=your-client-secret
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
