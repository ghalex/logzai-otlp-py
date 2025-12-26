"""
LogzAI plugin for FastAPI applications.
Automatically logs HTTP requests and responses with distributed tracing.

Note: fastapi and starlette are imported only when the plugin is registered,
making them optional dependencies.
"""

from typing import Optional
import time


def fastapi_plugin(instance, config: Optional[dict] = None):
    """
    LogzAI plugin for FastAPI applications.

    Creates a span for each HTTP request and logs request/response details.
    All logs during request handling are automatically associated with the request span.

    Args:
        instance: LogzAI instance
        config: Configuration dict with keys:
            - app: FastAPI application instance (required)
            - log_request_body: bool (default: False) - log request body
            - log_response_body: bool (default: False) - log response body
            - log_request_headers: bool (default: False) - log all request headers
            - log_response_headers: bool (default: False) - log all response headers
            - slow_request_threshold_ms: int (default: 1000) - log warning for slow requests

    Returns:
        Cleanup function that removes the middleware

    Raises:
        ImportError: If fastapi is not installed
        ValueError: If app is not provided in config

    Example:
        from fastapi import FastAPI
        from logzai_otlp import logzai, fastapi_plugin

        app = FastAPI()

        logzai.init(ingest_token="token", ingest_endpoint="http://localhost")
        logzai.plugin('fastapi', fastapi_plugin, {
            "app": app,
            "log_request_body": True,
            "log_request_headers": True,
            "log_response_headers": True,
            "slow_request_threshold_ms": 500
        })

        @app.post("/login")
        async def login(username: str):
            logzai.info("User logging in", username=username)
            return {"status": "ok"}
    """
    # Import fastapi/starlette only when plugin is registered
    try:
        from fastapi import FastAPI
        from starlette.middleware.base import BaseHTTPMiddleware
        from starlette.requests import Request
        from starlette.responses import Response
    except ImportError as e:
        raise ImportError(
            "fastapi is required to use the fastapi_plugin. "
            "Install it with: pip install fastapi"
        ) from e

    # Validate config
    if not config or "app" not in config:
        raise ValueError("fastapi_plugin requires 'app' in config")

    app: FastAPI = config["app"]
    log_request_body = config.get("log_request_body", False)
    log_response_body = config.get("log_response_body", False)

    log_request_headers = config.get("log_request_headers", False)
    log_response_headers = config.get("log_response_headers", False)
    slow_threshold_ms = config.get("slow_request_threshold_ms", 1000)

    class LogzAIMiddleware(BaseHTTPMiddleware):
        """Middleware that creates spans and logs for each HTTP request."""

        async def dispatch(self, request: Request, call_next):
            # Get route info
            method = request.method
            path = request.url.path
            route_name = f"{method} → {path}"

            # Match route pattern if available
            if hasattr(request, "scope") and "route" in request.scope:
                route = request.scope.get("route")
                if route and hasattr(route, "path"):
                    route_name = f"{method} → {route.path}"

            # Create span for this request with method and route
            with instance.span(route_name) as span:
                # Set span attributes
                span.set_attribute("type", "http")
                span.set_attribute("http.method", method)
                span.set_attribute("http.route", path)
                span.set_attribute("http.url", str(request.url))
                span.set_attribute("http.scheme", request.url.scheme)
                span.set_attribute("http.host", request.url.hostname or "")

                # Client info
                if request.client:
                    span.set_attribute("http.client.ip", request.client.host)

                # User agent
                user_agent = request.headers.get("user-agent", "")
                if user_agent:
                    span.set_attribute("http.user_agent", user_agent)

                # Capture all request headers if enabled
                if log_request_headers:
                    for header_name, header_value in request.headers.items():
                        # Normalize header name: lowercase and replace hyphens with underscores
                        normalized_name = header_name.lower().replace("-", "_")
                        span.set_attribute(
                            f"http.request.header.{normalized_name}", header_value
                        )

                # Start timing
                start_time = time.time()

                # Optionally log request body
                request_body = None
                if log_request_body:
                    try:
                        body_bytes = await request.body()
                        request_body = (
                            body_bytes.decode("utf-8") if body_bytes else None
                        )
                        # Note: We need to create a new request with the body since it's consumed
                        # This is handled by FastAPI's dependency injection
                    except Exception:
                        request_body = None

                # Process request
                try:
                    response: Response = await call_next(request)

                    # Calculate duration
                    duration_ms = (time.time() - start_time) * 1000

                    # Set response attributes
                    span.set_attribute("http.status_code", response.status_code)
                    span.set_attribute("http.duration_ms", round(duration_ms, 2))

                    # Capture all response headers if enabled
                    if log_response_headers:
                        for header_name, header_value in response.headers.items():
                            # Normalize header name: lowercase and replace hyphens with underscores
                            normalized_name = header_name.lower().replace("-", "_")
                            span.set_attribute(
                                f"http.response.header.{normalized_name}", header_value
                            )

                    # Log only for errors or slow requests
                    is_error = response.status_code >= 400
                    is_slow = duration_ms >= slow_threshold_ms

                    if is_error or is_slow:
                        # Prepare log data
                        log_data = {
                            "event": "http.request",
                            "type": "http",
                            "http_method": method,
                            "http_route": path,
                            "http_status": response.status_code,
                            "duration_ms": round(duration_ms, 2),
                        }

                        # Add optional data
                        if request.client:
                            log_data["client_ip"] = request.client.host

                        if user_agent:
                            log_data["user_agent"] = user_agent

                        if request_body:
                            log_data["request_body"] = request_body

                        # Log based on status and performance
                        if is_error:
                            instance.error(
                                f"{route_name} → {response.status_code}", **log_data
                            )
                        elif is_slow:
                            span.set_attribute("http.slow_request", True)
                            instance.warning(
                                f"{route_name} → slow request ({round(duration_ms, 0)}ms)",
                                **log_data,
                            )

                    return response

                except Exception as e:
                    # Calculate duration even on error
                    duration_ms = (time.time() - start_time) * 1000

                    span.set_attribute("http.duration_ms", round(duration_ms, 2))
                    span.set_attribute("error", True)
                    span.set_attribute("error.message", str(e))

                    # Log error
                    instance.error(
                        f"{route_name} → error: {str(e)}",
                        event="http.request.error",
                        http_method=method,
                        http_route=path,
                        duration_ms=round(duration_ms, 2),
                        error=str(e),
                        exc_info=True,
                    )

                    raise

    # Add middleware to app
    LogzAIMiddleware(app)
    app.user_middleware.insert(0, (LogzAIMiddleware, [], {}))  # type: ignore

    # instance.info(
    #     "FastAPI instrumentation enabled",
    #     event="fastapi.plugin.registered",
    #     log_request_body=log_request_body,
    #     log_response_body=log_response_body,
    #     slow_threshold_ms=slow_threshold_ms
    # )

    # Return cleanup function
    def cleanup():
        """Remove middleware from FastAPI app."""
        try:
            # Remove our middleware
            app.user_middleware = [  # type: ignore
                (mw_cls, args, kwargs)
                for mw_cls, args, kwargs in app.user_middleware
                if mw_cls is not LogzAIMiddleware
            ]

            # Rebuild middleware stack
            app.middleware_stack = None
            app.build_middleware_stack()

            # instance.info(
            #     "FastAPI instrumentation disabled",
            #     event="fastapi.plugin.unregistered"
            # )
        except Exception as e:
            instance.error(
                f"Error removing FastAPI middleware: {str(e)}",
                event="fastapi.plugin.cleanup.error",
                error=str(e),
            )

    return cleanup
