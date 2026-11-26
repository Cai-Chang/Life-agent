"""API entry point with same-origin browser authentication."""
import os
from urllib.parse import urlsplit
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from lifeagent.auth import AuthLimiter, router
from lifeagent.database import readiness
from lifeagent.planning import router as planning_router
from lifeagent.conversations import router as chat_router


def create_app():
    production = os.environ.get('APP_ENV') == 'production'
    configured_origin = os.environ.get('APP_ORIGIN', '')
    if production and (not configured_origin.startswith('https://') or not urlsplit(configured_origin).netloc):
        raise RuntimeError('Production requires an HTTPS APP_ORIGIN')
    allowed = {configured_origin} if configured_origin else {
        'http://127.0.0.1:5173', 'http://localhost:5173',
        'http://127.0.0.1:8080', 'http://localhost:8080',
    }
    app = FastAPI(title='LifeAgent', version='0.1.0', docs_url=None if production else '/docs', redoc_url=None)
    app.state.auth_limiter = AuthLimiter()

    @app.middleware('http')
    async def browser_boundary(request: Request, call_next):
        if request.url.path.startswith('/api/') and request.method not in ('GET', 'HEAD', 'OPTIONS'):
            origin = request.headers.get('origin')
            if request.headers.get('sec-fetch-site') == 'cross-site' or (origin and origin not in allowed):
                return JSONResponse(status_code=403, content={'error': {'code': 'ORIGIN_REJECTED', 'message': '不允许跨站操作'}})
            if request.headers.get('content-type', '').split(';')[0].lower() != 'application/json':
                return JSONResponse(status_code=415, content={'error': {'code': 'JSON_REQUIRED', 'message': '请求必须使用 JSON'}})
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'same-origin'
        if request.url.path.startswith('/api/'):
            response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        detail = exc.detail if isinstance(exc.detail, dict) else {'code': 'HTTP_ERROR', 'message': str(exc.detail)}
        return JSONResponse(status_code=exc.status_code, content={'error': detail}, headers=exc.headers)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        fields = [{'field': '.'.join(str(v) for v in item['loc'][1:]), 'message': item['msg']} for item in exc.errors()]
        return JSONResponse(status_code=422, content={'error': {'code': 'VALIDATION_ERROR', 'message': '请检查输入字段', 'fields': fields}})

    app.include_router(router)
    app.include_router(planning_router)
    app.include_router(chat_router)
    app.add_api_route('/health/live', live, methods=['GET'])
    app.add_api_route('/health/ready', ready, methods=['GET'])
    return app


def live() -> dict[str, str]:
    """Liveness reports only that the API process responds."""
    return {"status": "alive"}


def ready() -> JSONResponse:
    """Report actual connectivity and migration revision without writing."""
    ok, reason = readiness()
    return JSONResponse(
        status_code=200 if ok else 503,
        content={"status": "ready"} if ok else {"status": "not_ready", "reason": reason},
    )


app = create_app()
