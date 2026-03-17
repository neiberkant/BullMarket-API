# app/utils/file_utils.py

import logging
import os
import shutil
import base64
import re
import asyncio
import httpx
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Any

from fastapi import UploadFile
from pypdf import PdfWriter, PdfReader,errors as pypdf_errors

logger = logging.getLogger(__name__)

# --- NUEVA FUNCIÓN: Guardar Archivos Subidos ---
async def save_upload_file(upload_file: UploadFile, destination_folder: Path) -> Optional[Path]:
    """
    Guarda un objeto UploadFile en una carpeta de destino con un nombre seguro y único.

    Args:
        upload_file: El archivo subido desde FastAPI.
        destination_folder: La carpeta (Path) donde se guardará el archivo.

    Returns:
        La ruta (Path) al archivo guardado, o None si ocurre un error.
    """
    if not upload_file or not upload_file.filename:
        logger.warning("Intento de guardar un UploadFile inválido o sin nombre de archivo.")
        return None

    try:
        # Sanear el nombre del archivo para seguridad
        original_stem = Path(upload_file.filename).stem
        safe_stem = "".join(c for c in original_stem if c.isalnum() or c in ['_','-']).strip()[:50] or "archivo_subido"
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        final_filename = f"comp_{safe_stem}_{timestamp}.pdf"
        destination_path = destination_folder / final_filename

        # Asegurarse de que el directorio de destino exista
        destination_folder.mkdir(parents=True, exist_ok=True)

        logger.info(f"Guardando archivo subido '{upload_file.filename}' como '{destination_path}'...")
        with open(destination_path, "wb") as buffer:
            shutil.copyfileobj(upload_file.file, buffer)
        
        # Verificar que el archivo se guardó correctamente
        if destination_path.exists() and destination_path.stat().st_size > 0:
            logger.info(f"Archivo '{destination_path.name}' guardado exitosamente.")
            return destination_path
        else:
            logger.error(f"Fallo al guardar '{upload_file.filename}': el archivo no existe o está vacío después de escribir.")
            return None

    except Exception as e:
        logger.error(f"Error crítico al guardar archivo subido '{upload_file.filename}': {e}", exc_info=True)
        return None
    finally:
        # Siempre es buena práctica cerrar el archivo subido
        if upload_file:
            await upload_file.close()


# --- FUNCIÓN REFINADA: Combinar PDFs ---
async def combine_pdfs(input_paths: List[Path], output_path: Path) -> Optional[Path]:
    """
    Combina una lista de archivos PDF en uno solo de forma asíncrona.
    
    Args:
        input_paths: Lista de objetos Path a los PDFs de entrada.
        output_path: Objeto Path para el archivo PDF de salida.

    Returns:
        La ruta (Path) al archivo combinado, o None si falla.
    """
    if not input_paths:
        logger.warning("No se proporcionaron PDFs para combinar.")
        return None
    
    logger.info(f"Iniciando combinación de {len(input_paths)} PDFs en '{output_path.name}'...")
    pdf_writer = PdfWriter()

    valid_pdfs_added = 0
    for path in input_paths:
        if not path.exists() or path.stat().st_size == 0:
            logger.warning(f"Omitiendo PDF no encontrado o vacío: {path}")
            continue
        try:
            # pdf_writer.append() es una operación de I/O, mejor en un thread.
            await asyncio.to_thread(pdf_writer.append, str(path))
            logger.info(f"PDF '{path.name}' añadido al combinador.")
            valid_pdfs_added += 1
        except pypdf_errors.PdfReadError as e:
            logger.error(f"Error al leer el PDF '{path.name}', podría estar corrupto. Omitiendo. Error: {e}")
        except Exception as e:
            logger.error(f"Error inesperado al añadir PDF '{path.name}' a la combinación. Omitiendo. Error: {e}", exc_info=True)
            
    if valid_pdfs_added == 0:
        logger.error("No se pudo añadir ningún PDF válido a la combinación. Abortando.")
        return None

    try:
        # Asegurarse de que el directorio de salida exista
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Guardar el archivo combinado
        await asyncio.to_thread(pdf_writer.write, str(output_path))
        pdf_writer.close()

        if output_path.exists() and output_path.stat().st_size > 0:
            logger.info(f"PDF combinado guardado exitosamente en: {output_path}")
            return output_path
        else:
            logger.error(f"Fallo al combinar: el archivo de salida '{output_path}' no existe o está vacío.")
            return None
    except Exception as e:
        logger.error(f"Error crítico al guardar el PDF combinado '{output_path}': {e}", exc_info=True)
        return None

# --- FUNCIÓN REFINADA: Descarga Directa de PDF ---
async def download_pdf_direct(url: str, filename: str, directory: Path) -> Optional[Path]:
    """
    Descarga un archivo directamente desde una URL a un directorio.
    
    Args:
        url: La URL de descarga.
        filename: El nombre deseado para el archivo guardado.
        directory: El directorio (Path) donde guardar el archivo.
    
    Returns:
        La ruta (Path) al archivo guardado, o None si falla.
    """
    file_path = directory / filename
    try:
        # Asegurarse de que el directorio exista
        directory.mkdir(parents=True, exist_ok=True)
        
        async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
            async with client.stream("GET", url) as response:
                response.raise_for_status()
                with open(file_path, "wb") as f:
                    async for chunk in response.aiter_bytes():
                        f.write(chunk)
        
        if file_path.exists() and file_path.stat().st_size > 0:
            logger.info(f"Descarga directa de '{filename}' desde '{url}' completada.")
            return file_path
        else:
            logger.error(f"Fallo en descarga directa: archivo '{file_path}' no existe o está vacío.")
            return None
            
    except httpx.HTTPStatusError as e:
        logger.error(f"Error HTTP al descargar desde '{url}': {e.response.status_code} - {e.response.text}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Error inesperado en descarga directa desde '{url}': {e}", exc_info=True)
        return None


# (Las funciones de base64 y extracción de texto no son necesarias para el flujo principal ahora,
# pero se pueden mantener por si se usan en el futuro o se eliminan para limpiar el código)
# Por ahora las mantendremos por si son útiles.

async def save_base64_pdf(base64_string: str, filename: str, directory: Path) -> Optional[Path]:
    """Decodifica y guarda una cadena base64 como PDF."""
    try:
        pdf_data = base64.b64decode(base64_string)
        file_path = directory / filename
        directory.mkdir(parents=True, exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(pdf_data)
        return file_path
    except Exception as e:
        logger.error(f"Error guardando PDF desde base64: {e}", exc_info=True)
        return None