# app/services/data_service.py
import logging
import json
import shutil
import asyncio
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import List, Dict, Any, Optional, Literal

from app.core.config import settings
from app.models.assistant_models import PortfolioState

logger = logging.getLogger(__name__)

DataType = Literal["acciones", "cedears", "bonos", "opciones"]

class DataService:
    def __init__(self, base_path: Path = settings.MARKET_DATA_PATH):
        """
        Inicializa el servicio de datos, asegurando que los directorios existan.
        """
        self.market_data_path = base_path
        self.market_data_path.mkdir(parents=True, exist_ok=True)
        
        self.portfolio_path = settings.DATA_PATH / "portfolio"
        self.portfolio_path.mkdir(parents=True, exist_ok=True)
        self.portfolio_filepath = self.portfolio_path / "PORTAFOLIO_ACTUAL.json"

        logger.info(f"DataService inicializado. Directorio de datos de mercado: {self.market_data_path}")
        logger.info(f"DataService: Ruta de archivo de portafolio: {self.portfolio_filepath}")

    def _get_daily_data_filepath(self, data_type: str) -> Path:
        """
        Genera la ruta completa para el archivo JSON de datos de mercado del día actual.
        """
        today_str = datetime.now().strftime('%Y-%m-%d')
        filename = f"{data_type}_{today_str}.json"
        return self.market_data_path / filename

    async def read_daily_data(self, data_type: str) -> List[Dict[str, Any]]:
        """
        Lee y devuelve los datos de mercado del archivo JSON del día.
        """
        filepath = self._get_daily_data_filepath(data_type)
        if not filepath.exists():
            logger.info(f"El archivo de datos para '{data_type}' no existe hoy. Se devolverá una lista vacía.")
            return []
            
        try:
            def read_sync():
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if not content.strip():
                        return []
                    # Vuelve al inicio del archivo para leer con json.load
                    f.seek(0)
                    return json.load(f)

            data = await asyncio.to_thread(read_sync)
            logger.info(f"Leídos {len(data)} registros del archivo '{filepath.name}'.")
            return data
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error al leer o parsear el archivo JSON '{filepath.name}': {e}. Se devolverá una lista vacía.", exc_info=True)
            return []

    async def append_daily_data(self, data_type: str, new_data: List[Dict[str, Any]]):
        """
        Agrega nuevos datos de mercado al archivo JSON del día y lo reordena.
        """
        if not new_data:
            logger.info("No hay nuevos datos para agregar. Omitiendo escritura.")
            return
            
        filepath = self._get_daily_data_filepath(data_type)
        existing_data = await self.read_daily_data(data_type)
        combined_data = existing_data + new_data
        
        # Ordenamiento en dos pasos para asegurar Símbolo ASC, Timestamp DESC
        combined_data.sort(key=lambda record: record.get("timestamp", ""), reverse=True)
        combined_data.sort(key=lambda record: record.get("simbolo", "").strip())
        
        logger.info("Datos combinados y ordenados para el análisis.")

        try:
            def write_sync():
                with open(filepath, 'w', encoding='utf-8') as f:
                    json.dump(combined_data, f, indent=4, ensure_ascii=False)

            await asyncio.to_thread(write_sync)
            logger.info(
                f"Archivo '{filepath.name}' actualizado con éxito. "
                f"Registros añadidos: {len(new_data)}, "
                f"Total de registros ahora: {len(combined_data)}."
            )
        except IOError as e:
            logger.error(f"Error al escribir en el archivo JSON '{filepath.name}': {e}", exc_info=True)
            
    # --- NUEVOS MÉTODOS PARA GESTIONAR EL PORTAFOLIO ---

    async def read_portfolio(self) -> PortfolioState:
        """
        Lee el estado actual del portafolio desde PORTAFOLIO_ACTUAL.json.
        Si el archivo no existe, crea y devuelve un estado por defecto.
        Calcula automáticamente los agregados (cantidad total y precio promedio) para el frontend.
        """
        # Ejecutar limpieza de temporales antes de leer (mantenimiento)
        await self.cleanup_old_files()

        if not self.portfolio_filepath.exists():
            logger.warning(f"No se encontró el archivo de portafolio en {self.portfolio_filepath}. Creando uno por defecto.")
            default_portfolio = PortfolioState(
                cash_disponible_ars=1000000.00,
                cash_disponible_usd=10000.00,
                posiciones=[],
                realized_pnl={"ars": 0.0, "usd": 0.0}
            )
            await self.save_portfolio(default_portfolio)
            return default_portfolio
        
        try:
            def read_sync():
                with open(self.portfolio_filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return PortfolioState(**data)
            
            portfolio = await asyncio.to_thread(read_sync)
            
            # --- AGREGACIÓN DE DATOS PARA EL FRONTEND ---
            for pos in portfolio.posiciones:
                total_qty = sum(lote.cantidad for lote in pos.lotes_compra)
                pos.cantidad = total_qty
                
                if total_qty > 0:
                    total_cost = sum(lote.cantidad * lote.precio_compra for lote in pos.lotes_compra)
                    pos.precio_promedio_compra = total_cost / total_qty
                
                # Inferir tipo de activo si no está presente o es genérico
                pos.tipo_activo = self._infer_tipo_activo(pos.ticker)

            logger.info("Estado del portafolio leído y verificado exitosamente.")
            return portfolio
        except (json.JSONDecodeError, IOError, TypeError) as e:
            logger.error(f"Error al leer o parsear el archivo de portafolio: {e}. Se devolverá un portafolio de emergencia.", exc_info=True)
            # Devuelve un estado seguro y vacío para evitar que el sistema se detenga
            return PortfolioState(cash_disponible_ars=0.0, cash_disponible_usd=0.0, posiciones=[], realized_pnl={"ars": 0.0, "usd": 0.0})

    async def save_portfolio(self, portfolio_state: PortfolioState):
        """
        Guarda (sobrescribe) el estado del portafolio en PORTAFOLIO_ACTUAL.json.
        """
        try:
            def write_sync():
                with open(self.portfolio_filepath, 'w', encoding='utf-8') as f:
                    # Usamos .model_dump(mode='json') para asegurar que se serialice correctamente
                    json.dump(portfolio_state.model_dump(mode='json'), f, indent=4, ensure_ascii=False)
            
            await asyncio.to_thread(write_sync)
            logger.info(f"Portafolio guardado exitosamente en '{self.portfolio_filepath.name}'.")
        except IOError as e:
            logger.error(f"Error al escribir en el archivo de portafolio: {e}", exc_info=True)

    def _infer_tipo_activo(self, ticker: str) -> str:
        """Lógica simple para inferir el tipo de activo basado en el ticker."""
        t = ticker.upper()
        # Reglas básicas (pueden expandirse)
        if any(x in t for x in ["CEDEAR", "AAPL", "MSFT", "GOOGL", "MELI", "TSLA", "META", "NVDA", "AMZN", "NFLX"]):
             return "cedears"
        if len(t) <= 4 or t.endswith("D"): # Acciones locales o MEP
             return "acciones"
        return "bonos" # Default

    async def cleanup_old_files(self):
        """
        Elimina archivos temporales y reportes de audio antiguos para evitar crecimiento de disco.
        """
        try:
            def cleanup_sync():
                now = time.time()
                
                # 1. Limpiar carpeta 'temp' (archivos mayores a 1 hora)
                temp_path = settings.DATA_PATH / "temp"
                if temp_path.exists():
                    for item in temp_path.iterdir():
                        if item.is_dir():
                            # Si el directorio tiene más de 1 hora
                            if (now - item.stat().st_mtime) > 3600:
                                try:
                                    shutil.rmtree(item)
                                    logger.info(f"Cleanup: Directorio temporal eliminado: {item.name}")
                                except Exception as e:
                                    logger.error(f"Cleanup: No se pudo eliminar {item}: {e}")

                # 2. Limpiar reportes de audio (mayores a 24 horas)
                audio_path = settings.DATA_PATH / "audio_reports"
                if audio_path.exists():
                    cutoff = now - (24 * 3600)
                    for file in audio_path.glob("*.mp3"):
                        if file.stat().st_mtime < cutoff:
                            try:
                                file.unlink()
                                logger.info(f"Cleanup: Audio antiguo eliminado: {file.name}")
                            except Exception as e:
                                logger.error(f"Cleanup: No se pudo eliminar audio {file}: {e}")

            await asyncio.to_thread(cleanup_sync)
        except Exception as e:
            logger.error(f"Error general en el proceso de limpieza: {e}")