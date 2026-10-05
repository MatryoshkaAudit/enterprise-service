import asyncio
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import service_settings
from app.database import db_manager
from app.api.routers import bom_router, health_router
from app.grpc_server import serve_grpc

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Запуск Matryoshka Enterprise Service...")
    try:
        from matryoshka_db.seed_data import seed_database
        await seed_database()
    except Exception as e:
        logger.warning(f"Авто-инициализация БД: {e}")
    # Старт фонового gRPC-сервера
    grpc_server = await serve_grpc(service_settings.grpc_port)
    yield
    logger.info("Остановка Matryoshka Enterprise Service...")
    await grpc_server.stop(5)
    await db_manager.close()


app = FastAPI(
    title=service_settings.app_name,
    version="1.0.0",
    description="Микросервис управления многоуровневыми структурами изделий (BOM), O-Ring уязвимостями и каталогом отечественных аналогов",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=service_settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health_router.router)
app.include_router(bom_router.router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=service_settings.rest_host,
        port=service_settings.rest_port,
        reload=service_settings.debug,
    )
