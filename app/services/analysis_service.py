# app/services/analysis_service.py
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
import asyncio
import datetime
import re
import json

import google.generativeai as genai
from google.generativeai.types import HarmCategory, HarmBlockThreshold
from google.api_core.exceptions import GoogleAPIError

from app.core.config import settings
from app.utils.pdf_generator import create_pdf_from_text
from app.utils.tts_service import text_to_audio
# --- LÍNEA CORREGIDA ---
# Se eliminó la importación del obsoleto 'TradeAction'.
from app.models.assistant_models import PortfolioState

logger = logging.getLogger(__name__)

DEFAULT_SAFETY_SETTINGS = {
    HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
    HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
}

def parse_gemini_response(text: str) -> Dict[str, Any]:
    parsed_data = {"whatsapp_messages": [], "pdf_report_text": None, "error": None}
    if not text or not text.strip():
        parsed_data["error"] = "La respuesta de Gemini está vacía."
        return parsed_data
    try:
        wa_start_tag, wa_end_tag = "[WHATSAPP_START]", "[WHATSAPP_END]"
        msg_separator = "[MSG]"
        pdf_start_tag, pdf_end_tag = "[PDF_REPORT_START]", "[PDF_REPORT_END]"
        
        wa_block_match = re.search(f"{re.escape(wa_start_tag)}(.*?){re.escape(wa_end_tag)}", text, re.DOTALL)
        pdf_block_match = re.search(f"{re.escape(pdf_start_tag)}(.*?){re.escape(pdf_end_tag)}", text, re.DOTALL)

        if wa_block_match and pdf_block_match:
            wa_content = wa_block_match.group(1).strip()
            messages = re.split(re.escape(msg_separator), wa_content)
            parsed_data["whatsapp_messages"] = [msg.strip() for msg in messages if msg.strip()]
            parsed_data["pdf_report_text"] = pdf_block_match.group(1).strip()
        else:
            parsed_data["error"] = "La respuesta de la IA no siguió el formato de etiquetas esperado."
            parsed_data["pdf_report_text"] = text.strip()
            
    except Exception as e:
        parsed_data["error"] = f"Excepción inesperada durante el parseo de la respuesta de Gemini: {e}"
        parsed_data["pdf_report_text"] = text
    return parsed_data

class AnalysisService:
    def __init__(self):
        self.settings = settings
        if not self.settings.GEMINI_API_KEY:
            self._is_configured = False
            return
        
        genai.configure(api_key=str(self.settings.GEMINI_API_KEY))
        
        self._gemini_model_json = genai.GenerativeModel(
            model_name=str(self.settings.GEMINI_MODEL_NAME),
            safety_settings=DEFAULT_SAFETY_SETTINGS,
            generation_config={"response_mime_type": "application/json"}
        )
        self._gemini_model_text = genai.GenerativeModel(
            model_name=str(self.settings.GEMINI_MODEL_NAME),
            safety_settings=DEFAULT_SAFETY_SETTINGS
        )
        self._is_configured = True
        logger.info("AnalysisService inicializado y configurado con Gemini.")

    async def analyze_and_generate_recommendation(
        self, combined_pdf_path: Path, portfolio_data: List[Dict[str, Any]], tickers: List[str], user_identifier: str
    ) -> Dict[str, Any]:
        log_prefix = f"[{user_identifier}]"
        analysis_results: Dict[str, Any] = {'error': None}
        if not self._is_configured:
            analysis_results['error'] = "AnalysisService no está configurado."; return analysis_results
        try:
            with open(self.settings.PROMPT_FILE_GEMINI, "r", encoding="utf-8") as f: prompt_text = f.read()
            portfolio_str = json.dumps(portfolio_data, indent=2); tickers_str = ", ".join(tickers) if tickers else "Ninguno"
            full_prompt = f"{prompt_text}\n\n#--DATOS-ADICIONALES--#\n**Portafolio:**\n{portfolio_str}\n**Tickers:** {tickers_str}"
            logger.info(f"{log_prefix} Subiendo PDF '{combined_pdf_path.name}' a Gemini...")
            uploaded_file = await asyncio.to_thread(genai.upload_file, path=combined_pdf_path)
            logger.info(f"{log_prefix} Enviando prompt y archivo a Gemini para análisis (modo texto)...")
            response = await self._gemini_model_text.generate_content_async([full_prompt, uploaded_file])
            await asyncio.to_thread(genai.delete_file, name=uploaded_file.name)
            gemini_response_text = response.text
        except Exception as e:
            analysis_results['error'] = f"Error al interactuar con Gemini: {e}"; logger.error(f"{log_prefix} {analysis_results['error']}", exc_info=True); return analysis_results
        parsed_texts = parse_gemini_response(gemini_response_text); analysis_results.update(parsed_texts)
        if analysis_results.get("pdf_report_text"):
            today = datetime.datetime.now(); year_month_folder = self.settings.SCRAPED_REPORTS_PATH / str(today.year) / f"{today.month:02d}"; year_month_folder.mkdir(parents=True, exist_ok=True)
            report_filename = f"Reporte_Analisis_Financiero_{today.strftime('%Y-%m-%d')}.pdf"; output_report_pdf_path = year_month_folder / report_filename
            generated_pdf_path = await create_pdf_from_text(text_content=analysis_results["pdf_report_text"], output_pdf_path=output_report_pdf_path, title=f"Reporte de Análisis Financiero - {today.strftime('%d/%m/%Y')}")
            analysis_results['pdf_report_path'] = str(generated_pdf_path) if generated_pdf_path else None
        audio_text = "\n".join(analysis_results.get("whatsapp_messages", []))
        if audio_text:
            today_for_audio = datetime.datetime.now(); audio_folder = self.settings.AUDIO_REPORTS_PATH / str(today_for_audio.year) / f"{today_for_audio.month:02d}"; audio_folder.mkdir(parents=True, exist_ok=True)
            audio_filename = f"Resumen_Audio_{today_for_audio.strftime('%Y-%m-%d_%H%M%S')}.mp3"; output_audio_path = audio_folder / audio_filename
            generated_audio_path = await text_to_audio(text_to_speak=audio_text, output_audio_path=output_audio_path)
            analysis_results['audio_report_path'] = str(generated_audio_path) if generated_audio_path else None
        analysis_results['analysis_summary'] = (analysis_results.get("whatsapp_messages", []) or [""])[0]
        logger.info(f"{log_prefix} Análisis y generación de artefactos completado."); return analysis_results

    async def run_tactical_analysis(
        self,
        historical_data: List[Dict[str, Any]],
        portfolio_state: PortfolioState,
        fundamental_report_path: Optional[Path],
        user_identifier: str,
        custom_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        log_prefix = f"[{user_identifier}]"
        if not self._is_configured or not historical_data:
            return {}

        try:
            if custom_prompt and custom_prompt.strip():
                prompt_template = custom_prompt
            else:
                prompt_path = self.settings.PROMPTS_PATH / "tactical_prompt.txt"
                with open(prompt_path, "r", encoding="utf-8") as f:
                    prompt_template = f.read()
            
            historical_data_json_str = json.dumps(historical_data, indent=2)
            portfolio_state_json_str = portfolio_state.model_dump_json(indent=2)

            full_prompt = (
                f"{prompt_template}\n\n"
                f"#--INPUT_DATA_SCHEMA--#\n"
                f"**PORTAFOLIO_ACTUAL**:\n{portfolio_state_json_str}\n\n"
                f"**HISTORIAL_INTRADIARIO**:\n{historical_data_json_str}"
            )
            
            contents_for_gemini = [full_prompt]
            if fundamental_report_path and fundamental_report_path.exists():
                uploaded_file = await asyncio.to_thread(genai.upload_file, path=fundamental_report_path)
                contents_for_gemini.append(uploaded_file)
            
            logger.info(f"{log_prefix} Enviando prompt de gestión de portafolio a Gemini...")
            response = await self._gemini_model_json.generate_content_async(contents_for_gemini)
            
            if 'uploaded_file' in locals() and locals()['uploaded_file']:
                await asyncio.to_thread(genai.delete_file, name=locals()['uploaded_file'].name)

            logger.info(f"--- RESPUESTA DE GEMINI ---\n{response.text}\n-------------------------------")
            
            # Limpieza y extracción de JSON
            text_response = response.text
            # Intentar extraer contenido entre bloques de código si existen
            json_match = re.search(r'```json\s*(.*?)\s*```', text_response, re.DOTALL)
            if json_match:
                text_response = json_match.group(1)
            else:
                # Si no hay bloques de código, buscar el primer { y el último }
                start_idx = text_response.find('{')
                end_idx = text_response.rfind('}')
                if start_idx != -1 and end_idx != -1:
                    text_response = text_response[start_idx:end_idx+1]

            try:
                response_json = json.loads(text_response)
            except json.JSONDecodeError as jde:
                logger.error(f"{log_prefix} Error al parsear JSON (posible truncamiento): {jde}")
                # Si el JSON está truncado, devolvemos un error estructurado para que el router lo maneje
                return {"error": "Respuesta truncada de la IA", "raw_text": response.text}

            return response_json

        except Exception as e:
            logger.error(f"{log_prefix} Error al ejecutar el análisis táctico con Gemini: {e}", exc_info=True)
            return {}