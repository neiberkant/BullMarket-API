# app/services/pdf_generation_service.py
import logging
from pathlib import Path
from typing import Optional, TYPE_CHECKING
import asyncio
from fpdf import FPDF, FPDFException # type: ignore
import os
import traceback
import re

if TYPE_CHECKING:
    from app.core.config import Settings

logger = logging.getLogger(__name__)

class AnalysisReportPDF(FPDF):
    def __init__(self, orientation='P', unit='mm', format='A4', user_identifier: Optional[str] = "N/A"):
        super().__init__(orientation, unit, format)
        self.user_identifier = user_identifier
        self.set_auto_page_break(auto=True, margin=15)

        self.active_font_family = "Arial"
        self.has_dejavu_bold = False
        self.has_dejavu_italic = False
        self.has_dejavu_bold_italic = False

        dejavu_base_name = "DejaVuSans"
        dejavu_sans_regular_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        dejavu_sans_bold_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        dejavu_sans_italic_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"
        dejavu_sans_bold_italic_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-BoldOblique.ttf"

        font_paths_to_try = {
            "": dejavu_sans_regular_path,
            "B": dejavu_sans_bold_path,
            "I": dejavu_sans_italic_path,
            "BI": dejavu_sans_bold_italic_path,
        }

        regular_loaded = False
        logger.info("Intentando cargar fuentes DejaVu Sans...")
        for style, fpath in font_paths_to_try.items():
            if os.path.exists(fpath):
                try:
                    self.add_font(family=dejavu_base_name, style=style, fname=fpath, uni=True)
                    logger.info(f"Fuente {dejavu_base_name} (Estilo: '{style if style else 'Regular'}') cargada desde: {fpath}")
                    if style == "":
                        regular_loaded = True
                        self.active_font_family = dejavu_base_name
                    if style == "B": self.has_dejavu_bold = True
                    if style == "I": self.has_dejavu_italic = True
                    if style == "BI": self.has_dejavu_bold_italic = True
                except (RuntimeError, FPDFException, FileNotFoundError) as e_font_add:
                    logger.warning(f"No se pudo añadir la fuente {dejavu_base_name} estilo '{style}' desde {fpath}: {e_font_add}")
                except Exception as e_font_add_other:
                    logger.error(f"Error inesperado al añadir fuente {dejavu_base_name} estilo '{style}': {e_font_add_other}", exc_info=True)
            else:
                logger.warning(f"Archivo de fuente para {dejavu_base_name} estilo '{style}' NO ENCONTRADO en {fpath}")

        if not regular_loaded:
            logger.warning("Fuente base DejaVuSans (Regular) NO pudo ser cargada. Recurriendo a Arial (core). Es posible que se pierda soporte para caracteres especiales.")
            self.active_font_family = "Arial"
            self.has_dejavu_bold = False
            self.has_dejavu_italic = False
            self.has_dejavu_bold_italic = False

        self.set_font(self.active_font_family, "", 11)

    # >>> MÉTODO _get_style_if_available MOVido DENTRO DE LA CLASE <<<
    def _get_style_if_available(self, desired_style: str) -> str:
        """Devuelve el estilo deseado si la fuente activa lo soporta y se cargó, sino un fallback."""
        if self.active_font_family == "DejaVuSans":
            if desired_style == "B" and self.has_dejavu_bold: return "B"
            if desired_style == "I" and self.has_dejavu_italic: return "I"
            if desired_style == "BI" and self.has_dejavu_bold_italic: return "BI"
            if desired_style == "": return ""
            return "" # Fallback a regular si el estilo específico de DejaVu no está disponible
        else:
            # Para fuentes core como Arial, FPDF2 maneja B, I, BI por defecto
            return desired_style

    def header(self):
        style = self._get_style_if_available("B")
        self.set_font(self.active_font_family, style, 12)
        report_title = "Informe de Análisis de Mercado y Portafolio"
        self.cell(0, 10, report_title, 0, 1, "C")
        self.ln(5)
        self.set_font(self.active_font_family, self._get_style_if_available(""), 11)

    def footer(self):
        self.set_y(-15)
        style = self._get_style_if_available("I")
        self.set_font(self.active_font_family, style, 8)
        self.cell(0, 10, f"Página {self.page_no()}/{{nb}}", 0, 0, "C")

    def chapter_title(self, title: str):
        style = self._get_style_if_available("B")
        self.set_font(self.active_font_family, style, 12)
        self.cell(0, 8, title, 0, 1, "L")
        self.ln(4)
        self.set_font(self.active_font_family, self._get_style_if_available(""), 11)

    def chapter_body(self, text_content: str):
        style = self._get_style_if_available("")
        self.set_font(self.active_font_family, style, 11)
        self.multi_cell(0, 7, text_content)
        self.ln()

    def add_content_from_markdown_like_text(self, text_content: str):
         pass

# create_pdf_from_text (wrapper asíncrono)
async def create_pdf_from_text(
    text_content: str,
    output_pdf_path: Path,
    title: Optional[str] = "Análisis del Informe",
    user_identifier: Optional[str] = "N/A",
) -> Optional[Path]:
    log_prefix = f"[PDFGenerationService ({user_identifier})]"
    logger.info(f"{log_prefix} Iniciando generación de PDF en: {output_pdf_path.name}")
    logger.debug(f"{log_prefix} Contenido de texto para PDF (longitud {len(text_content)}, primeros 500 chars): {text_content[:500]}...")


    if not text_content or not text_content.strip():
        logger.error(f"{log_prefix} No hay contenido de texto válido para generar el PDF.")
        return None

    output_pdf_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        pdf = AnalysisReportPDF(user_identifier=user_identifier)
        pdf.alias_nb_pages()

        def generate_pdf_and_save_sync():
            logger.info(f"{log_prefix} Ejecutando generación de PDF en thread...")
            # --- Añadir contenido a la página ---
            pdf.add_page() # Esto llama a header() y footer()

            lines = text_content.strip().split('\n')
            current_section_body = []
            current_section_title = None

            def add_current_section():
                 if current_section_title:
                      logger.debug(f"{log_prefix} Añadiendo sección: {current_section_title[:100]}...")
                      pdf.chapter_title(current_section_title)
                 if current_section_body:
                      body_text = "\n".join(current_section_body).strip()
                      logger.debug(f"{log_prefix} Añadiendo cuerpo de sección (primeros 200 chars): {body_text[:200]}...")
                      pdf.chapter_body(body_text)
                 # No reset title/body here, done in the loop


            for line in lines:
                 line = line.strip()
                 if not line: continue

                 section_title_match = re.match(r'#\s*\d+\.\s*(.*)', line)

                 if section_title_match:
                      add_current_section()
                      current_section_title = section_title_match.group(1).strip()
                      current_section_body = []
                 elif line.startswith('#'): # Otros títulos Markdown, tratar como cuerpo
                      current_section_body.append(line)
                 else: # Línea normal de cuerpo
                      current_section_body.append(line)

            add_current_section() # Añadir la última sección

            logger.info(f"{log_prefix} Contenido de PDF generado. Total páginas: {pdf.page_no()}")

            # --- Guardar el archivo PDF ---
            logger.info(f"{log_prefix} Guardando PDF en: {output_pdf_path}...")
            # pdf.output() es síncrono
            pdf.output(str(output_pdf_path), "F")
            logger.info(f"{log_prefix} Operación de guardado de PDF finalizada para {output_pdf_path.name}.")


        # Ejecutar la función síncrona en un thread
        await asyncio.to_thread(generate_pdf_and_save_sync)

        # Verificar si el archivo fue creado y no está vacío
        if output_pdf_path.exists() and output_pdf_path.stat().st_size > 0:
            logger.info(f"{log_prefix} PDF generado exitosamente: {output_pdf_path.name} (Tamaño: {output_pdf_path.stat().st_size} bytes)")
            return output_pdf_path
        else:
            logger.error(f"{log_prefix} La generación del PDF finalizó, pero el archivo no existe o está vacío.")
            if output_pdf_path.exists():
                try: os.remove(output_pdf_path)
                except Exception as clean_e: logger.error(f"{log_prefix} Error limpiando archivo PDF {output_pdf_path.name}: {clean_e}")
            return None

    except Exception as e:
        logger.error(f"{log_prefix} Error crítico al generar PDF desde texto: {e}", exc_info=True)
        if output_pdf_path.exists():
            try: os.remove(output_pdf_path)
            except Exception as clean_e: logger.error(f"{log_prefix} Error limpiando archivo PDF {output_pdf_path.name}: {clean_e}")
        return None