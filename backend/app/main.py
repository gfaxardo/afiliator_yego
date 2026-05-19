from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.routers.scout_liq import router as scout_liq_router

app = FastAPI(
    title="Liquidador de Calidad Scouts Yego",
    description="API para liquidación de pagos a scouts según calidad de conversión",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(scout_liq_router)


@app.get("/")
def root():
    return {
        "app": "Liquidador de Calidad Scouts Yego",
        "version": "0.1.0",
        "docs": "/docs",
    }
