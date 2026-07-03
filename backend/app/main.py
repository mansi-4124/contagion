from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.logging import configure_logging, get_logger
from app.config.settings import get_settings
from app.api.v1.auth import router as auth_router
# as you build more routers in later days, import them here too:
# from app.api.v1.onboarding import router as onboarding_router
# from app.api.v1.graph import router as graph_router
# from app.api.v1.alerts import router as alerts_router
# from app.api.v1.query import router as query_router
# from app.api.v1.simulate import router as simulate_router
# from app.api.v1.exposure import router as exposure_router
# from app.api.v1.supplier_form import router as supplier_form_router
# from app.api.v1.ws import router as ws_router

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging()
    settings = get_settings()
    log.info("contagion api starting", cognee_cloud=bool(settings.cognee.service_url))
    yield
    log.info("contagion api shutting down")


def create_app() -> FastAPI:
    settings = get_settings()

    app = FastAPI(
        title="Contagion API",
        version="0.1.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(auth_router)
    # app.include_router(onboarding_router)
    # app.include_router(graph_router)
    # app.include_router(alerts_router)
    # app.include_router(query_router)
    # app.include_router(simulate_router)
    # app.include_router(exposure_router)
    # app.include_router(supplier_form_router)
    # app.include_router(ws_router)

    app.state.settings = settings
    return app


app = create_app()