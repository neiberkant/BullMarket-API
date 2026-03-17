# app/core/state_manager.py
import logging
from typing import Dict, Optional
import asyncio

logger = logging.getLogger(__name__)

class OTPStateManager:
    """
    Una clase simple para gestionar el estado de los códigos OTP en memoria.
    
    Esta clase actúa como un "buzón" temporal donde el endpoint del webhook
    o formulario puede "dejar" un código OTP, y el scraper en ejecución puede
    "recogerlo".
    
    El almacenamiento es un simple diccionario en memoria, lo que es suficiente
    para este propósito, ya que los códigos OTP tienen una vida muy corta.
    """
    def __init__(self):
        # El diccionario almacenará: { request_id: otp_code }
        self._otp_storage: Dict[str, str] = {}
        # Un Lock de asyncio para manejar el acceso concurrente al diccionario de forma segura.
        self._lock = asyncio.Lock()
        logger.info("OTP State Manager inicializado en memoria.")

    async def set_otp(self, request_id: str, otp_code: str):
        """
        Guarda un código OTP para un ID de solicitud específico.
        Esta función será llamada por el endpoint que recibe el código del usuario.
        """
        async with self._lock:
            self._otp_storage[request_id] = otp_code
            logger.info(f"Código OTP guardado para el request_id: {request_id}")

    async def get_otp(self, request_id: str) -> Optional[str]:
        """
        Obtiene y elimina un código OTP para un ID de solicitud específico.
        Esta función será llamada por el scraper en su bucle de sondeo.
        
        Devuelve el código si se encuentra, o None si no.
        Una vez devuelto, el código se elimina para evitar su reutilización.
        """
        async with self._lock:
            # .pop() es ideal aquí: devuelve el valor y elimina la clave en una operación atómica.
            # El segundo argumento (None) es el valor a devolver si la clave no existe.
            otp_code = self._otp_storage.pop(request_id, None)
            if otp_code:
                logger.info(f"Código OTP recuperado y eliminado para el request_id: {request_id}")
            return otp_code

    async def get_pending_requests(self) -> list:
        """
        Retorna una lista de request_ids que están esperando (WAITING) un OTP.
        """
        async with self._lock:
            return [req_id for req_id, code in self._otp_storage.items() if code == "WAITING"]

# Creamos una única instancia global del gestor de estado para que
# toda la aplicación comparta el mismo "buzón".
otp_manager = OTPStateManager()