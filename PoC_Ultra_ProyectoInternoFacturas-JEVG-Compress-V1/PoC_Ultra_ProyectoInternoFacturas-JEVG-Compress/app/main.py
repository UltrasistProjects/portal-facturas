import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import BASE_DIR, settings
from app.core.database import SessionLocal
from app.core.errors import BusinessRuleError
from app.core.logging_config import configure_logging
from app.core.middleware import (
    RequestContextMiddleware,
    SecurityHeadersMiddleware,
    request_id_var,
    security_headers,
)
from app.core.startup import run_startup_checks
from app.routers import admin, auth, contracts, dashboard, invoices, suppliers

configure_logging(settings.log_dir, settings.debug)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    with SessionLocal() as db:
        run_startup_checks(settings, db)
    settings.storage_path.mkdir(parents=True, exist_ok=True)
    logger.info("Starting %s in %s", settings.app_name, settings.app_env)
    yield
    logger.info("Stopping %s", settings.app_name)


# `debug` nunca se pasa a FastAPI: con debug=True Starlette muestra trazas en lugar del handler de errores.
app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.secret_key,
    session_cookie="invoice_portal_session",
    same_site="lax",
    https_only=settings.session_https_only,
    max_age=8 * 60 * 60,
)
# add_middleware envuelve por fuera: RequestContext queda como el mas externo de los middlewares de usuario.
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RequestContextMiddleware)
app.mount("/static", StaticFiles(directory=BASE_DIR / "app" / "static"), name="static")
for router in (auth.router, dashboard.router, invoices.router, suppliers.router, contracts.router, admin.router):
    app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name}


def render_error(request: Request, status_code: int, message: str):
    if request.headers.get("accept", "").startswith("application/json"):
        return JSONResponse({"detail": message}, status_code=status_code)
    from app.routers.common import templates

    context = {"status_code": status_code, "message": message, "request_id": getattr(request.state, "request_id", None)}
    return templates.TemplateResponse(request, "error.html", context, status_code=status_code)


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401 and request.url.path != "/login":
        return RedirectResponse("/login", status_code=303)
    return render_error(request, exc.status_code, exc.detail)


@app.exception_handler(BusinessRuleError)
async def business_rule_handler(request: Request, exc: BusinessRuleError):
    return render_error(request, exc.status_code, exc.message)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    # Starlette ejecuta este handler en ServerErrorMiddleware, por fuera de los middlewares de usuario:
    # las cabeceras de seguridad y el request_id se agregan aqui explicitamente.
    request_id = getattr(request.state, "request_id", None)
    token = request_id_var.set(request_id)
    try:
        logger.exception("Unhandled application error")
    finally:
        request_id_var.reset(token)
    response = render_error(request, 500, "Ocurrio un error interno. Informe la referencia al soporte.")
    response.headers.update(security_headers(request.url.scheme))
    if request_id:
        response.headers["X-Request-ID"] = request_id
    return response
