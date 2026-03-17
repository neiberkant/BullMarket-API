# app/services/tts_service.py

import logging
from pathlib import Path
from typing import Optional, TYPE_CHECKING
import asyncio

# Importar la librería gTTS y su excepción específica
from gtts import gTTS, gTTSError

if TYPE_CHECKING:
    # Esta importación es solo para Type Checking, no se ejecuta en runtime.
    # Permite que el type checker sepa la estructura del objeto Settings
    from app.core.config import Settings

# Configurar logger para este módulo
logger = logging.getLogger(__name__)

# Define una función asíncrona para la conversión de texto a audio
async def text_to_audio(
    # Recibimos la configuración como parámetro para mejor testabilidad
    settings_param: "Settings",
    text_to_speak: str,
    # Usamos Path de pathlib para un manejo de rutas más robusto
    output_audio_path: Path,
    # Identificador opcional para logs, útil para rastrear por usuario o request
    user_identifier: Optional[str] = "DefaultUser"
) -> Optional[Path]:
    """
    Convierte un texto dado a un archivo de audio (MP3) usando la librería gTTS.
    Guarda el archivo en la ruta especificada.
    Retorna el Path al archivo de audio generado si tiene éxito, o None si falla.

    Args:
        settings_param: Objeto de configuración con settings como TTS_LANGUAGE_CODE.
        text_to_speak: La cadena de texto a convertir en voz.
        output_audio_path: La ruta completa donde se guardará el archivo MP3 de salida.
        user_identifier: Un identificador para incluir en los logs.

    Returns:
        Path al archivo de audio generado o None si la conversión falla
        o el texto de entrada está vacío.
    """
    # Prefijo para todos los logs de esta ejecución de la función
    log_prefix = f"[TTSService ({user_identifier})]"

    # Validación básica: si el texto está vacío o solo tiene espacios en blanco, no hacemos nada
    if not text_to_speak or not text_to_speak.strip():
        logger.warning(f"{log_prefix} Se recibió texto vacío o solo con espacios en blanco para convertir a audio. Omitiendo generación de audio.")
        return None

    # Asegurarse de que el directorio de salida exista
    output_audio_path.parent.mkdir(parents=True, exist_ok=True)
    logger.info(f"{log_prefix} Directorio de salida para audio: {output_audio_path.parent} asegurado.")


    try:
        # Usamos solo la primera parte del código de idioma (ej: 'es' de 'es-ES')
        # porque gTTS solo necesita el código principal de idioma.
        lang_code = settings_param.TTS_LANGUAGE_CODE.split('-')[0]
        logger.info(f"{log_prefix} Generando audio para el texto (longitud {len(text_to_speak)}) con gTTS (lang: {lang_code})...")

        # Crear el objeto gTTS
        # slow=False para velocidad normal de habla
        tts = gTTS(text=text_to_speak, lang=lang_code, slow=False)

        # La operación de guardar puede ser síncrona y bloquear,
        # por lo que la ejecutamos en un thread separado usando asyncio.to_thread
        await asyncio.to_thread(tts.save, str(output_audio_path))

        logger.info(f"{log_prefix} Intento de guardar archivo de audio en: {output_audio_path}")

        # Verificar si el archivo se creó correctamente y no está vacío
        if output_audio_path.exists() and output_audio_path.stat().st_size > 0:
            logger.info(f"{log_prefix} Archivo de audio guardado exitosamente: {output_audio_path.name} (Tamaño: {output_audio_path.stat().st_size} bytes)")
            return output_audio_path # Retornar el Path si todo fue bien
        else:
            # Esto puede ocurrir si hubo un error en el guardado pero no lanzó excepción,
            # o si el archivo resultante es de 0 bytes.
            logger.error(f"{log_prefix} El archivo de audio generado no existe o está vacío después de intentar guardarlo.")
            # Limpiar cualquier archivo vacío o parcial
            if output_audio_path.exists():
                try:
                    os.remove(output_audio_path)
                    logger.info(f"{log_prefix} Limpiado archivo de audio vacío: {output_audio_path.name}")
                except Exception as clean_e:
                     logger.error(f"{log_prefix} Error limpiando archivo de audio {output_audio_path.name}: {clean_e}")
            return None # Retornar None si el archivo final es inválido

    except gTTSError as e_gtts:
        # Capturar errores específicos de la librería gTTS (ej: error de red, texto muy largo)
        logger.error(f"{log_prefix} Error específico de gTTS al generar audio: {e_gtts}", exc_info=True)
        return None # Retornar None en caso de error de gTTS
    except Exception as e:
        # Capturar cualquier otra excepción inesperada durante el proceso
        logger.error(f"{log_prefix} Error inesperado al generar audio desde texto: {e}", exc_info=True)
        # Limpiar posible archivo parcial en caso de excepción
        if output_audio_path.exists():
            try:
                os.remove(output_audio_path)
                logger.info(f"{log_prefix} Limpiado archivo de audio parcial tras error: {output_audio_path.name}")
            except Exception as clean_e:
                 logger.error(f"{log_prefix} Error limpiando archivo de audio {output_audio_path.name}: {clean_e}")
        return None # Retornar None en caso de error