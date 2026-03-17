# trading_assistant_api/app/main.py

import uvicorn
from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import logging

# --- ¡CORRECCIÓN AQUÍ! ---
# Añadimos 'analysis_router' a la lista de importaciones.
from app.api.v1.router_assistant import assistant_router, market_data_router, otp_router, analysis_router
from app.core.config import settings

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    version=settings.PROJECT_VERSION,
    description=settings.PROJECT_DESCRIPTION,
)

try:
    data_path = Path(settings.DATA_PATH)
    data_path.mkdir(parents=True, exist_ok=True)
    app.mount("/data", StaticFiles(directory=data_path), name="data")
    logger.info(f"Directorio estático '{data_path.resolve()}' montado en la ruta URL '/data'.")
except Exception as e:
    logger.error(f"CRÍTICO: No se pudo montar el directorio de datos. Error: {e}")

# --- Inclusión de Routers ---
app.include_router(assistant_router, prefix="/api/v1")
app.include_router(market_data_router, prefix="/api/v1")
app.include_router(analysis_router, prefix="/api/v1")
# El router del formulario OTP se registra SIN prefijo para que la URL sea más limpia y directa.
app.include_router(otp_router)

@app.get("/", include_in_schema=False)
async def root():
    return RedirectResponse(url="/docs")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8003)