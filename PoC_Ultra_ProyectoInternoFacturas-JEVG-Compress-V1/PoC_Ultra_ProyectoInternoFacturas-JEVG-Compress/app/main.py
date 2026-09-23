import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.core.config import settings
from app.core.logging_config import configure_logging
from app.routers import admin, auth, contracts, dashboard, invoices, suppliers

configure_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings.storage_path.mkdir(parents=True, exist_ok=True)
    logger.info("Starting %s in %s", settings.app_name, settings.app_env)
    yield
    logger.info("Stopping %s", settings.app_name)


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, session_cookie="invoice_portal_session",
                   same_site="lax", https_only=settings.session_https_only, max_age=8 * 60 * 60)
app.mount("/static", StaticFiles(directory="app/static"), name="static")
for router in (auth.router, dashboard.router, invoices.router, suppliers.router, contracts.router, admin.router):
    app.include_router(router)


@app.get("/health")
def health():
    return {"status": "ok", "app": settings.app_name}


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == 401 and request.url.path != "/login":
        return RedirectResponse("/login", status_code=303)
    if request.headers.get("accept", "").startswith("application/json"):
        return JSONResponse({"detail": exc.detail}, status_code=exc.status_code)
    from app.routers.common import templates
    return templates.TemplateResponse(request, "error.html", {"status_code": exc.status_code, "message": exc.detail}, status_code=exc.status_code)


@app.exception_handler(Exception)
async def unexpected_error(request: Request, exc: Exception):
    logger.exception("Unhandled application error")
    from app.routers.common import templates
    return templates.TemplateResponse(request, "error.html", {"status_code": 500, "message": "Ocurrio un error interno. Consulte el log local."}, status_code=500)

