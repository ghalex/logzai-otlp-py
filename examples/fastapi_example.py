#!/usr/bin/env python3
"""
Example: Using LogzAI with FastAPI plugin.
Demonstrates automatic logging and tracing of HTTP requests.
"""

import os
import dotenv

dotenv.load_dotenv(override=True)

from fastapi import FastAPI  # noqa: E402
from pydantic import BaseModel  # noqa: E402
from logzai_otlp import logzai  # noqa: E402
from logzai_otlp.plugins import fastapi_plugin  # noqa: E402


# Create FastAPI app
app = FastAPI(title="LogzAI FastAPI Demo")


# Request/Response models
class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    status: str
    user_id: str | None = None


# Initialize LogzAI and register FastAPI plugin
logzai.init(
    ingest_token=os.getenv("LOGZAI_TOKEN", "pylz_v1_e"),
    ingest_endpoint=os.getenv("LOGZAI_ENDPOINT", "https://ingest.logzai.com"),
    service_name="pydantic-example",
    environment="dev",
    mirror_to_console=True,
)
# Register FastAPI plugin
logzai.plugin(
    "fastapi",
    fastapi_plugin,
    {
        "app": app,
        "log_request_body": True,  # Log request bodies
        "slow_request_threshold_ms": 500,  # Warn on requests >500ms
    },
)


# Routes - all logs within routes are automatically associated with the request span
@app.get("/")
async def root():
    """Root endpoint."""
    logzai.info("Root endpoint called")
    return {"message": "Hello World"}


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.post("/login")
async def login(request: LoginRequest) -> LoginResponse:
    """Login endpoint - demonstrates logging within request context."""
    # All these logs will be associated with the POST /login span
    logzai.info("User login attempt", username=request.username)

    # Simulate authentication
    if request.username == "admin" and request.password == "secret":
        logzai.info("Login successful", username=request.username, user_id="123")
        return LoginResponse(status="success", user_id="123")
    else:
        logzai.warning("Login failed - invalid credentials", username=request.username)
        return LoginResponse(status="failed")


@app.get("/users/{user_id}")
async def get_user(user_id: str):
    """Get user endpoint - demonstrates path parameters."""
    logzai.info("Fetching user", user_id=user_id)

    # Simulate slow database query
    import asyncio

    await asyncio.sleep(0.6)  # Will trigger slow request warning

    logzai.info("User fetched successfully", user_id=user_id)
    return {"user_id": user_id, "name": "Alexandru"}


@app.get("/error")
async def error_endpoint():
    """Error endpoint - demonstrates error logging."""
    logzai.error("About to raise an error")
    raise ValueError("This is a test error")


# Run with: uvicorn fastapi_example:app --reload
# Then test:
#   curl http://localhost:8000/
#   curl -X POST http://localhost:8000/login -H "Content-Type: application/json" -d '{"username":"admin","password":"secret"}'
#   curl http://localhost:8000/users/123
#   curl http://localhost:8000/error

if __name__ == "__main__":
    import uvicorn

    print("\n" + "=" * 50)
    print("FastAPI + LogzAI Demo")
    print("=" * 50)
    print("\nEndpoints:")
    print("  GET  /              - Root endpoint")
    print("  GET  /health        - Health check")
    print("  POST /login         - Login (admin/secret)")
    print("  GET  /users/{id}    - Get user (slow)")
    print("  GET  /error         - Error example")
    print("\nStarting server...")
    print("=" * 50 + "\n")

    uvicorn.run(app, host="0.0.0.0", port=8000)
