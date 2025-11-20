"""HTTP wrapper for Qlik Sense MCP Server to enable web service deployment."""

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import httpx

from .config import QlikSenseConfig
from .server import QlikSenseMCPServer

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Qlik Sense MCP Server HTTP API",
    description="HTTP wrapper for Qlik Sense MCP Server tools",
    version="1.3.4"
)

# Enable CORS for web clients
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure based on your needs
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global server instance
mcp_server: Optional[QlikSenseMCPServer] = None


class ToolRequest(BaseModel):
    """Request model for tool execution."""
    tool_name: str = Field(..., description="Name of the tool to execute")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    server_url: Optional[str] = None
    has_api_key: bool = False
    config_valid: bool = False


@app.on_event("startup")
async def startup_event():
    """Initialize MCP server on startup."""
    global mcp_server
    try:
        # Initialize in background to avoid blocking startup
        mcp_server = QlikSenseMCPServer()
        logger.info("MCP Server initialized successfully")
        if mcp_server.config_valid:
            logger.info(f"Connected to Qlik Cloud: {mcp_server.config.server_url}")
            if mcp_server.cloud_api:
                logger.info("Cloud API client initialized successfully")
            else:
                logger.error("Cloud API client failed to initialize - check configuration and API key")
        else:
            logger.warning("MCP Server configuration is invalid - check QLIK_SERVER_URL and QLIK_API_KEY")
    except Exception as e:
        logger.error(f"Failed to initialize MCP Server: {e}", exc_info=True)
        mcp_server = None


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
        "openapi": "/openapi.json"
    }


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """Health check endpoint."""
    if mcp_server is None:
        return HealthResponse(
            status="error",
            config_valid=False
        )
    
    return HealthResponse(
        status="healthy" if mcp_server.config_valid else "unhealthy",
        server_url=mcp_server.config.server_url if mcp_server.config else None,
        has_api_key=bool(mcp_server.config.api_key) if mcp_server.config else False,
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
            detail=f"MCP Server configuration invalid. Check QLIK_SERVER_URL and QLIK_API_KEY environment variables."
        )
    
    if not mcp_server.cloud_api:
        error_msg = "Cloud API not initialized"
        if mcp_server.config:
            error_msg += f". Server URL: {mcp_server.config.server_url}, Has API Key: {bool(mcp_server.config.api_key)}"
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
        "get_app_details"
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
            error_detail += f". Server URL: {mcp_server.config.server_url}, Has API Key: {bool(mcp_server.config.api_key)}, Config Valid: {mcp_server.config_valid}"
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
            error_detail += f". Server URL: {mcp_server.config.server_url}, Has API Key: {bool(mcp_server.config.api_key)}, Config Valid: {mcp_server.config_valid}"
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
            error_detail += f". Server URL: {mcp_server.config.server_url}, Has API Key: {bool(mcp_server.config.api_key)}, Config Valid: {mcp_server.config_valid}"
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

