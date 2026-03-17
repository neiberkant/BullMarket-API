# app/utils/pdf_generator.py
import logging
from pathlib import Path
from typing import Optional
from fpdf import FPDF
import asyncio

logger = logging.getLogger(__name__)

class ReportPDF(FPDF):
    def header(self):
        self.set_font('Arial', 'B', 12)
        self.cell(0, 10, self.title, 0, 1, 'C')
        self.ln(10)

    def footer(self):
        self.set_y(-15)
        self.set_font('Arial', 'I', 8)
        self.cell(0, 10, f'Página {self.page_no()}/{{nb}}', 0, 0, 'C')

async def create_pdf_from_text(text_content: str, output_pdf_path: Path, title: str) -> Optional[Path]:
    try:
        pdf = ReportPDF()
        pdf.set_title(title)
        pdf.alias_nb_pages()
        pdf.add_page()
        pdf.set_font('Arial', '', 11)
        # Usar 'latin-1' para manejar caracteres comunes en español
        await asyncio.to_thread(pdf.multi_cell, 0, 5, text_content.encode('latin-1', 'replace').decode('latin-1'))
        await asyncio.to_thread(pdf.output, str(output_pdf_path))
        return output_pdf_path
    except Exception as e:
        logger.error(f"Error generando PDF en {output_pdf_path}: {e}", exc_info=True)
        return None