"""HTTP wrapper for Qlik Sense MCP Server to enable web service deployment."""

import asyncio
import contextlib
import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from starlette.routing import Mount
import httpx

from mcp.server.fastmcp import FastMCP

from .config import QlikSenseConfig
from .server import QlikSenseMCPServer

logger = logging.getLogger(__name__)

# Global server instance
mcp_server: Optional[QlikSenseMCPServer] = None

# FastMCP instance for Streamable HTTP transport
# streamable_http_path="/" means the app handles requests at the mount root
fastmcp = FastMCP("Qlik Sense MCP Server", streamable_http_path="/")


# Lifespan context manager for FastAPI
@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan including FastMCP session manager."""
    global mcp_server
    
    # Initialize MCP server
    try:
        mcp_server = QlikSenseMCPServer()
        logger.info("MCP Server initialized successfully")
        if mcp_server.config_valid:
            logger.info(f"Connected to Qlik Cloud: {mcp_server.config.server_url}")
            if mcp_server.cloud_api:
                logger.info("Cloud API client initialized successfully (Auth: OAuth2 M2M)")
            else:
                logger.error("Cloud API client failed to initialize - check OAuth2 M2M configuration")
        else:
            logger.warning("MCP Server configuration is invalid - check QLIK_SERVER_URL, QLIK_OAUTH_CLIENT_ID and QLIK_OAUTH_CLIENT_SECRET")
    except Exception as e:
        logger.error(f"Failed to initialize MCP Server: {e}", exc_info=True)
        mcp_server = None
    
    # Start FastMCP session manager
    async with fastmcp.session_manager.run():
        logger.info("FastMCP Streamable HTTP session manager started")
        yield  # Application runs here
        logger.info("Shutting down FastMCP session manager")


app = FastAPI(
    title="Qlik Sense MCP Server HTTP API",
    description="HTTP wrapper for Qlik Sense MCP Server tools",
    version="1.3.4",
    lifespan=lifespan
)

# Mount FastMCP Streamable HTTP app on /mcp
# This must be done after FastAPI app creation but before requests are handled
app.mount("/mcp", fastmcp.streamable_http_app())
logger.info("FastMCP Streamable HTTP endpoint mounted on /mcp")

# Enable CORS for web clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure based on your needs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)



class ToolRequest(BaseModel):
    """Request model for tool execution."""
    tool_name: str = Field(..., description="Name of the tool to execute")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    server_url: Optional[str] = None
    has_oauth: bool = False
    auth_method: Optional[str] = None
    config_valid: bool = False


# Register FastMCP tools
@fastmcp.tool()
async def get_apps(
    limit: int = 25,
    offset: int = 0,
    name: Optional[str] = None,
    space_id: Optional[str] = None
) -> str:
    """
    Get list of Qlik Cloud applications with essential fields and filters (name, space) and pagination.
    
    Args:
        limit: Maximum number of apps to return (default: 25, max: 50)
        offset: Number of apps to skip for pagination (default: 0)
        name: Wildcard case-insensitive search in application name
        space_id: Filter applications by Space ID
    
    Returns:
        JSON string with list of applications
    """
    if mcp_server is None:
        return json.dumps({"error": "MCP Server not initialized"}, indent=2)
    
    if not mcp_server.config_valid:
        return json.dumps({"error": "MCP Server configuration invalid"}, indent=2)
    
    try:
        result = await mcp_server.call_tool_direct("get_apps", {
            "limit": limit,
            "offset": offset,
            "name": name,
            "space_id": space_id
        })
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error in get_apps tool: {e}", exc_info=True)
        return json.dumps({"error": str(e)}, indent=2)


@fastmcp.tool()
async def get_app_details(app_id: str) -> str:
    """
    Get application details including metadata and information from Qlik Cloud.
    
    Args:
        app_id: Application ID
    
    Returns:
        JSON string with application details
    """
    if mcp_server is None:
        return json.dumps({"error": "MCP Server not initialized"}, indent=2)
    
    if not mcp_server.config_valid:
        return json.dumps({"error": "MCP Server configuration invalid"}, indent=2)
    
    try:
        result = await mcp_server.call_tool_direct("get_app_details", {
            "app_id": app_id
        })
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error in get_app_details tool: {e}", exc_info=True)
        return json.dumps({"error": str(e)}, indent=2)


@fastmcp.tool()
async def get_datasets(
    limit: int = 100,
    offset: int = 0,
    space_id: Optional[str] = None
) -> str:
    """
    Get list of data assets (datasets) from Qlik Cloud.
    
    Args:
        limit: Maximum number of datasets to return (default: 100)
        offset: Number of datasets to skip for pagination (default: 0)
        space_id: Filter datasets by Space ID
    
    Returns:
        JSON string with list of datasets
    """
    if mcp_server is None or not mcp_server.config_valid:
        return json.dumps({"error": "MCP Server not configured"}, indent=2)
    
    if not mcp_server.cloud_api:
        return json.dumps({"error": "Cloud API not initialized"}, indent=2)
    
    try:
        result = await asyncio.to_thread(
            mcp_server.cloud_api.get_data_assets,
            limit=limit,
            offset=offset,
            space_id=space_id
        )
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error in get_datasets tool: {e}", exc_info=True)
        return json.dumps({"error": str(e)}, indent=2)


@fastmcp.tool()
async def get_dataset(dataset_id: str) -> str:
    """
    Get specific dataset details by ID from Qlik Cloud.
    
    Args:
        dataset_id: Dataset ID
    
    Returns:
        JSON string with dataset details
    """
    if mcp_server is None or not mcp_server.config_valid:
        return json.dumps({"error": "MCP Server not configured"}, indent=2)
    
    if not mcp_server.cloud_api:
        return json.dumps({"error": "Cloud API not initialized"}, indent=2)
    
    try:
        result = await asyncio.to_thread(mcp_server.cloud_api.get_data_asset, dataset_id)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error in get_dataset tool: {e}", exc_info=True)
        return json.dumps({"error": str(e)}, indent=2)


@fastmcp.tool()
async def get_spaces(
    limit: int = 100,
    offset: int = 0
) -> str:
    """
    Get list of spaces from Qlik Cloud.
    
    Args:
        limit: Maximum number of spaces to return (default: 100)
        offset: Number of spaces to skip for pagination (default: 0)
    
    Returns:
        JSON string with list of spaces
    """
    if mcp_server is None or not mcp_server.config_valid:
        return json.dumps({"error": "MCP Server not configured"}, indent=2)
    
    if not mcp_server.cloud_api:
        return json.dumps({"error": "Cloud API not initialized"}, indent=2)
    
    try:
        result = await asyncio.to_thread(
            mcp_server.cloud_api.get_spaces,
            limit=limit,
            offset=offset
        )
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error in get_spaces tool: {e}", exc_info=True)
        return json.dumps({"error": str(e)}, indent=2)


@fastmcp.tool()
async def get_app_tables(app_id: str) -> str:
    """
    Get list of tables in a Qlik Cloud application with field counts and row counts.
    
    Args:
        app_id: Application ID
    
    Returns:
        JSON string with list of tables
    """
    if mcp_server is None or not mcp_server.config_valid:
        return json.dumps({"error": "MCP Server not configured"}, indent=2)
    
    if not mcp_server.cloud_api:
        return json.dumps({"error": "Cloud API not initialized"}, indent=2)
    
    try:
        result = await asyncio.to_thread(mcp_server.cloud_api.get_app_tables, app_id)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error in get_app_tables tool: {e}", exc_info=True)
        return json.dumps({"error": str(e)}, indent=2)


@fastmcp.tool()
async def get_app_fields(app_id: str, table_name: Optional[str] = None) -> str:
    """
    Get list of fields in a Qlik Cloud application, optionally filtered by table name.
    
    Args:
        app_id: Application ID
        table_name: Optional table name to filter fields
    
    Returns:
        JSON string with list of fields
    """
    if mcp_server is None or not mcp_server.config_valid:
        return json.dumps({"error": "MCP Server not configured"}, indent=2)
    
    if not mcp_server.cloud_api:
        return json.dumps({"error": "Cloud API not initialized"}, indent=2)
    
    try:
        result = await asyncio.to_thread(mcp_server.cloud_api.get_app_fields, app_id, table_name)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error in get_app_fields tool: {e}", exc_info=True)
        return json.dumps({"error": str(e)}, indent=2)


@fastmcp.tool()
async def get_field_values(app_id: str, field_name: str, limit: int = 100) -> str:
    """
    Get distinct values of a specific field from a Qlik Cloud application.
    
    Args:
        app_id: Application ID
        field_name: Name of the field
        limit: Maximum number of values to return (default: 100)
    
    Returns:
        JSON string with field values
    """
    if mcp_server is None or not mcp_server.config_valid:
        return json.dumps({"error": "MCP Server not configured"}, indent=2)
    
    if not mcp_server.cloud_api:
        return json.dumps({"error": "Cloud API not initialized"}, indent=2)
    
    try:
        result = await asyncio.to_thread(mcp_server.cloud_api.get_field_values, app_id, field_name, limit)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error in get_field_values tool: {e}", exc_info=True)
        return json.dumps({"error": str(e)}, indent=2)


@fastmcp.tool()
async def get_app_data(
    app_id: str,
    table_name: Optional[str] = None,
    dimensions: Optional[List[str]] = None,
    measures: Optional[List[str]] = None,
    limit: int = 1000,
    offset: int = 0
) -> str:
    """
    Get data from a Qlik Cloud application. Can read from a table or create a custom hypercube.
    
    Args:
        app_id: Application ID
        table_name: Name of the table to read data from (if provided, reads table data)
        dimensions: List of dimension field names (for custom hypercube)
        measures: List of measure expressions (for custom hypercube)
        limit: Maximum number of rows to return (default: 1000)
        offset: Number of rows to skip for pagination (default: 0)
    
    Returns:
        JSON string with data
    """
    if mcp_server is None or not mcp_server.config_valid:
        return json.dumps({"error": "MCP Server not configured"}, indent=2)
    
    if not mcp_server.cloud_api:
        return json.dumps({"error": "Cloud API not initialized"}, indent=2)
    
    try:
        def _get_app_data():
            # If table_name is provided, read table data
            if table_name:
                return mcp_server.cloud_api.get_table_data(app_id, table_name, limit, offset)
            # If dimensions/measures are provided, create custom hypercube
            elif dimensions or measures:
                dims = dimensions or []
                meas = measures or []
                return mcp_server.cloud_api.create_hypercube(app_id, dims, meas, None, limit)
            else:
                return {"error": "Either table_name or dimensions/measures must be provided"}
        
        result = await asyncio.to_thread(_get_app_data)
        return json.dumps(result, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error in get_app_data tool: {e}", exc_info=True)
        return json.dumps({"error": str(e)}, indent=2)


@fastmcp.tool()
async def health_check() -> str:
    """
    Check the health status of the Qlik Sense MCP Server.
    Returns server status, configuration validity, and authentication method.
    
    Returns:
        JSON string with health status information
    """
    if mcp_server is None:
        return json.dumps({
            "status": "error",
            "message": "MCP Server not initialized"
        }, indent=2)
    
    try:
        health_status = {
            "status": "healthy" if mcp_server.config_valid else "unhealthy",
            "server_url": mcp_server.config.server_url if mcp_server.config else None,
            "config_valid": mcp_server.config_valid,
            "has_oauth": bool(mcp_server.config and mcp_server.config.oauth_client_id and mcp_server.config.oauth_client_secret) if mcp_server.config else False,
            "auth_method": "OAuth2 M2M" if mcp_server.config_valid else None,
            "cloud_api_initialized": mcp_server.cloud_api is not None
        }
        
        # Try to get OAuth token if API is initialized (to verify authentication works)
        if mcp_server.cloud_api:
            try:
                token = mcp_server.cloud_api._get_oauth_token()
                health_status["oauth_token_valid"] = bool(token)
            except Exception as e:
                health_status["oauth_token_valid"] = False
                health_status["oauth_error"] = str(e)
        else:
            health_status["oauth_token_valid"] = False
        
        return json.dumps(health_status, indent=2, ensure_ascii=False)
    except Exception as e:
        logger.error(f"Error in health_check tool: {e}", exc_info=True)
        return json.dumps({"error": str(e)}, indent=2)




@app.get("/", response_model=Dict[str, str])
async def root():
    """Root endpoint with API information."""
    return {
        "name": "Qlik Sense MCP Server HTTP API",
        "version": "1.3.4",
        "status": "running",
        "docs": "/docs",
        "redoc": "/redoc",
        "health": "/health",
        "openapi": "/openapi.json",
        "mcp": "/mcp"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    if mcp_server is None:
        return HealthResponse(
            status="error",
            config_valid=False
        )
    
    auth_method = "OAuth2 M2M" if mcp_server.config and mcp_server.config_valid else None
    
    return HealthResponse(
        status="healthy" if mcp_server.config_valid else "unhealthy",
        server_url=mcp_server.config.server_url if mcp_server.config else None,
        has_oauth=bool(mcp_server.config and mcp_server.config.oauth_client_id and mcp_server.config.oauth_client_secret) if mcp_server.config else False,
        auth_method=auth_method,
        config_valid=mcp_server.config_valid
    )


@app.get("/ping")
async def ping_cloud():
    """Ping Qlik Cloud API."""
    if mcp_server is None:
        raise HTTPException(status_code=503, detail="MCP Server not initialized")
    
    if not mcp_server.config_valid:
        raise HTTPException(
            status_code=503, 
            detail="MCP Server configuration invalid. Check QLIK_SERVER_URL, QLIK_OAUTH_CLIENT_ID and QLIK_OAUTH_CLIENT_SECRET"
        )
    
    if not mcp_server.cloud_api:
        error_msg = "Cloud API not initialized"
        if mcp_server.config:
            error_msg += f". Server URL: {mcp_server.config.server_url}, Auth Method: OAuth2 M2M"
        raise HTTPException(status_code=503, detail=error_msg)
    
    try:
        # Simple health check - try to get apps with limit=1
        result = await asyncio.to_thread(mcp_server.cloud_api.get_apps, limit=1, offset=0)
        if "error" in result:
            return {
                "status": "error",
                "message": result.get("error", "Unknown error"),
                "details": result.get("details"),
                "timestamp": datetime.now().isoformat()
            }
        return {
            "status": "success",
            "message": "Qlik Cloud API is accessible",
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        logger.error(f"Error pinging Qlik Cloud: {e}", exc_info=True)
        return {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now().isoformat()
        }


@app.get("/tools")
async def list_tools():
    """List all available tools."""
    if mcp_server is None:
        raise HTTPException(status_code=503, detail="MCP Server not initialized")
    
    # List of available tools (Qlik Cloud only)
    tools = [
        "get_apps",
        "get_app_details",
        "get_app_tables",
        "get_app_fields",
        "get_field_values",
        "get_app_data",
        "get_datasets",
        "get_dataset",
        "get_spaces",
        "health_check"
    ]
    
    return {
        "tools": tools,
        "total": len(tools),
        "description": "Available Qlik Sense MCP tools"
    }


@app.post("/tools/execute")
async def execute_tool(request: ToolRequest):
    """Execute a tool with given arguments."""
    if mcp_server is None:
        raise HTTPException(status_code=503, detail="MCP Server not initialized")
    
    if not mcp_server.config_valid:
        raise HTTPException(
            status_code=503,
            detail="MCP Server configuration invalid. Check environment variables."
        )
    
    try:
        # Use the direct tool call method
        result = await mcp_server.call_tool_direct(request.tool_name, request.arguments)
        
        # Check for errors
        if "error" in result:
            raise HTTPException(status_code=500, detail=result["error"])
        
        return result
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error executing tool {request.tool_name}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# Convenience endpoints for common tools
@app.get("/apps")
async def get_apps(
    limit: int = 25,
    offset: int = 0,
    name: Optional[str] = None,
    stream: Optional[str] = None,
    published: Optional[str] = "true"
):
    """Get list of applications (convenience endpoint)."""
    return await execute_tool(ToolRequest(
        tool_name="get_apps",
        arguments={
            "limit": limit,
            "offset": offset,
            "name": name,
            "stream": stream,
            "published": published
        }
    ))


@app.get("/datasets")
async def get_datasets(
    limit: int = 100,
    offset: int = 0,
    space_id: Optional[str] = None
):
    """Get list of data assets (datasets) - Qlik Cloud only."""
    if mcp_server is None or not mcp_server.config_valid:
        raise HTTPException(status_code=503, detail="MCP Server not configured")
    
    if not mcp_server.cloud_api:
        error_detail = "Cloud API not initialized"
        if mcp_server.config:
            error_detail += f". Server URL: {mcp_server.config.server_url}, Auth Method: OAuth2 M2M, Config Valid: {mcp_server.config_valid}"
        raise HTTPException(status_code=503, detail=error_detail)
    
    try:
        result = await asyncio.to_thread(
            mcp_server.cloud_api.get_data_assets,
            limit=limit,
            offset=offset,
            space_id=space_id
        )
        return result
    except Exception as e:
        logger.error(f"Error getting datasets: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/datasets/{dataset_id}")
async def get_dataset(dataset_id: str):
    """Get specific dataset by ID - Qlik Cloud only."""
    if mcp_server is None or not mcp_server.config_valid:
        raise HTTPException(status_code=503, detail="MCP Server not configured")
    
    if not mcp_server.cloud_api:
        error_detail = "Cloud API not initialized"
        if mcp_server.config:
            error_detail += f". Server URL: {mcp_server.config.server_url}, Auth Method: OAuth2 M2M, Config Valid: {mcp_server.config_valid}"
        raise HTTPException(status_code=503, detail=error_detail)
    
    try:
        result = await asyncio.to_thread(mcp_server.cloud_api.get_data_asset, dataset_id)
        return result
    except Exception as e:
        logger.error(f"Error getting dataset {dataset_id}: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/spaces")
async def get_spaces(limit: int = 100, offset: int = 0):
    """Get list of spaces - Qlik Cloud only."""
    if mcp_server is None or not mcp_server.config_valid:
        raise HTTPException(status_code=503, detail="MCP Server not configured")
    
    if not mcp_server.cloud_api:
        error_detail = "Cloud API not initialized"
        if mcp_server.config:
            error_detail += f". Server URL: {mcp_server.config.server_url}, Auth Method: OAuth2 M2M, Config Valid: {mcp_server.config_valid}"
        raise HTTPException(status_code=503, detail=error_detail)
    
    try:
        result = await asyncio.to_thread(
            mcp_server.cloud_api.get_spaces,
            limit=limit,
            offset=offset
        )
        return result
    except Exception as e:
        logger.error(f"Error getting spaces: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/apps/{app_id}/details")
async def get_app_details(app_id: str):
    """Get application details (convenience endpoint)."""
    return await execute_tool(ToolRequest(
        tool_name="get_app_details",
        arguments={"app_id": app_id}
    ))




if __name__ == "__main__":
    import os
    import uvicorn
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(app, host="0.0.0.0", port=port)

