# app/utils/tts_service.py
import logging
from pathlib import Path
from typing import Optional
from gtts import gTTS
import asyncio

logger = logging.getLogger(__name__)

async def text_to_audio(text_to_speak: str, output_audio_path: Path) -> Optional[Path]:
    if not text_to_speak.strip():
        logger.warning("Texto para audio está vacío.")
        return None
    try:
        tts = gTTS(text=text_to_speak, lang='es', slow=False)
        await asyncio.to_thread(tts.save, str(output_audio_path))
        logger.info(f"Archivo de audio guardado en: {output_audio_path}")
        return output_audio_path
    except Exception as e:
        logger.error(f"Error generando audio en {output_audio_path}: {e}", exc_info=True)
        return None