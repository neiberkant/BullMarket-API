# app/services/notification_service.py

import logging
import smtplib
import httpx
import asyncio
import mimetypes
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional, Tuple, Dict, Any, List
from urllib.parse import quote, urljoin
import os

from app.core.config import settings
from app.models.assistant_models import NotificationResult, NotificationStatus, OrdenOperativa, RecomendacionMercado
from app.utils import tts_service

logger = logging.getLogger(__name__)

# --- CONSTANTES PARA REINTENTOS ---
MAX_RETRIES = 3
INITIAL_BACKOFF_S = 1.0

class NotificationService:
    def __init__(self):
        logger.info("Inicializando NotificationService...")

    def _build_public_url_for_file(self, file_path: Path) -> Optional[str]:
        if not settings.PUBLIC_BASE_URL_FOR_FILES:
            logger.error("PUBLIC_BASE_URL_FOR_FILES no está configurada.")
            return None
        try:
            relative_path = file_path.relative_to(settings.DATA_PATH)
            public_url = urljoin(settings.PUBLIC_BASE_URL_FOR_FILES.rstrip('/') + '/', f"data/{str(relative_path).replace(os.path.sep, '/')}")
            return public_url
        except Exception as e:
            logger.error(f"Error al construir la URL pública para '{file_path}': {e}", exc_info=True)
            return None

    async def _send_whatsapp_text(self, recipient: str, message: str, request_id: str) -> NotificationResult:
        log_prefix = f"[{request_id}][WhatsApp Texto]"
        endpoint = f"{settings.EVOLUTION_API_URL.rstrip('/')}/message/sendText/{quote(settings.EVOLUTION_INSTANCE_ID)}"
        headers = {"apikey": settings.EVOLUTION_API_KEY, "Content-Type": "application/json"}
        payload = {"number": recipient, "options": {"delay": 1200}, "text": message}

        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"{log_prefix} Enviando texto a {recipient} (Intento {attempt + 1}/{MAX_RETRIES})...")
                async with httpx.AsyncClient(timeout=settings.WHATSAPP_TIMEOUT_REQUEST) as client:
                    response = await client.post(endpoint, headers=headers, json=payload)
                    response.raise_for_status()
                    return NotificationResult(success=True, message=f"Texto enviado a {recipient}.")
            except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as e:
                wait_time = INITIAL_BACKOFF_S * (2 ** attempt)
                logger.warning(f"{log_prefix} Intento {attempt + 1} falló. Error: {type(e).__name__}. Reintentando en {wait_time}s...")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(wait_time)
                else:
                    error_msg = f"Error final enviando texto a WhatsApp después de {MAX_RETRIES} intentos: {e}"
                    logger.error(f"{log_prefix} {error_msg}", exc_info=True)
                    return NotificationResult(success=False, message=error_msg)
        
        return NotificationResult(success=False, message="Fallo el envío después de todos los reintentos.")


    async def _send_whatsapp_media(self, recipient: str, file_path: Path, caption: str, media_type: str, request_id: str) -> NotificationResult:
        log_prefix = f"[{request_id}][WhatsApp {media_type.capitalize()}]"
        public_url = self._build_public_url_for_file(file_path)
        if not public_url:
            return NotificationResult(success=False, message=f"Fallo al crear URL pública para {file_path.name}.")

        endpoint = f"{settings.EVOLUTION_API_URL.rstrip('/')}/message/sendMedia/{quote(settings.EVOLUTION_INSTANCE_ID)}"
        headers = {"apikey": settings.EVOLUTION_API_KEY, "Content-Type": "application/json"}
        mimetype, _ = mimetypes.guess_type(file_path.name)
        payload: Dict[str, Any] = {
            "number": recipient, "options": {"delay": 1200},
            "media": public_url, "mediatype": media_type,
            "mimetype": mimetype or "application/octet-stream",
            "fileName": file_path.name, "caption": caption
        }

        for attempt in range(MAX_RETRIES):
            try:
                logger.info(f"{log_prefix} Enviando payload a Evolution API (Intento {attempt + 1}/{MAX_RETRIES})...")
                async with httpx.AsyncClient(timeout=settings.WHATSAPP_TIMEOUT_REQUEST) as client:
                    response = await client.post(endpoint, headers=headers, json=payload)
                    response.raise_for_status()
                    return NotificationResult(success=True, message=f"Archivo '{file_path.name}' enviado a {recipient}.")
            except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as e:
                wait_time = INITIAL_BACKOFF_S * (2 ** attempt)
                logger.warning(f"{log_prefix} Intento {attempt + 1} falló. Error: {type(e).__name__}. Reintentando en {wait_time}s...")
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(wait_time)
                else:
                    error_body = e.response.text if isinstance(e, httpx.HTTPStatusError) else str(e)
                    error_msg = f"Error final enviando media después de {MAX_RETRIES} intentos. Respuesta: {error_body[:500]}"
                    logger.error(f"{log_prefix} {error_msg}", exc_info=True)
                    return NotificationResult(success=False, message=error_msg)

        return NotificationResult(success=False, message="Fallo el envío de media después de todos los reintentos.")

    async def _send_email(self, recipient: str, subject: str, body_html: str, attachments: List[Path], request_id: str) -> NotificationResult:
        log_prefix = f"[{request_id}][Email]"
        msg_obj = MIMEMultipart('mixed')
        msg_obj["From"] = settings.EMAIL_FROM_ADDRESS; msg_obj["To"] = recipient; msg_obj["Subject"] = subject
        msg_obj.attach(MIMEText(body_html, "html", "utf-8"))

        for path in attachments:
            if not path.exists(): continue
            try:
                with open(path, "rb") as f: part = MIMEApplication(f.read(), Name=path.name)
                part['Content-Disposition'] = f'attachment; filename="{path.name}"'
                msg_obj.attach(part)
            except Exception as e:
                return NotificationResult(success=False, message=f"Error adjuntando {path.name}: {e}")
        
        logger.info(f"{log_prefix} Enviando email a {recipient}...")
        try:
            server = smtplib.SMTP(settings.EMAIL_SMTP_SERVER, settings.EMAIL_SMTP_PORT, timeout=settings.SMTP_TIMEOUT_S)
            if settings.EMAIL_USE_TLS: await asyncio.to_thread(server.starttls)
            await asyncio.to_thread(server.login, settings.SMTP_USER, settings.SMTP_PASSWORD)
            await asyncio.to_thread(server.sendmail, settings.EMAIL_FROM_ADDRESS, recipient, msg_obj.as_string())
            await asyncio.to_thread(server.quit)
            return NotificationResult(success=True, message=f"Email enviado a {recipient}.")
        except Exception as e:
            error_msg = f"Error al enviar email: {e}"
            logger.error(f"{log_prefix} {error_msg}", exc_info=True)
            return NotificationResult(success=False, message=error_msg)

    async def send_analysis_notification(
        self, request_id: str, analysis_results: Dict[str, Any],
        whatsapp_recipient: Optional[str] = None, email_recipient: Optional[str] = None
    ) -> Tuple[Optional[NotificationStatus], Optional[NotificationStatus]]:
        whatsapp_status = NotificationStatus()
        email_status = NotificationStatus()
        final_whatsapp_recipient = whatsapp_recipient or settings.WHATSAPP_RECIPIENT_NUMBER_DEFAULT
        final_email_recipient = email_recipient or settings.EMAIL_RECIPIENT_DEFAULT

        if final_whatsapp_recipient:
            whatsapp_status.recipient = final_whatsapp_recipient
            for text_msg in analysis_results.get("whatsapp_messages", []):
                if text_msg:
                    result = await self._send_whatsapp_text(final_whatsapp_recipient, text_msg, request_id)
                    whatsapp_status.text_messages.append(result)
                    await asyncio.sleep(1)
            
            if analysis_results.get("audio_report_path"):
                audio_path = Path(analysis_results["audio_report_path"])
                result = await self._send_whatsapp_media(final_whatsapp_recipient, audio_path, "", "audio", request_id)
                whatsapp_status.audio_files.append(result)

            if analysis_results.get("pdf_report_path"):
                pdf_path = Path(analysis_results["pdf_report_path"])
                caption = f"Análisis detallado: {pdf_path.name}"
                result = await self._send_whatsapp_media(final_whatsapp_recipient, pdf_path, caption, "document", request_id)
                whatsapp_status.document_files.append(result)

        if final_email_recipient:
            email_status.recipient = final_email_recipient
            attachments = []
            if analysis_results.get("pdf_report_path"):
                attachments.append(Path(analysis_results["pdf_report_path"]))
            
            email_body = analysis_results.get("pdf_report_text", "El análisis del reporte se encuentra adjunto.").replace("\n", "<br>")
            subject = f"Análisis de Trading Assistant - ID: {request_id}"
            result = await self._send_email(final_email_recipient, subject, email_body, attachments, request_id)
            email_status.document_files.append(result)
            
        return whatsapp_status, email_status
    
    async def send_tactical_notification(
        self,
        request_id: str,
        full_analysis_response: Dict[str, Any],
        whatsapp_recipient: Optional[str] = None,
        email_recipient: Optional[str] = None
    ):
        """
        Formatea y envía los resultados de un análisis táctico completo.
        Construye mensajes separados para órdenes operativas y recomendaciones de mercado.
        """
        ordenes = [OrdenOperativa(**o) for o in full_analysis_response.get("ordenes_operativa", [])]
        recomendaciones = [RecomendacionMercado(**r) for r in full_analysis_response.get("recomendaciones_mercado", [])]
        
        # --- 1. Construir Mensaje de Órdenes Operativas ---
        text_orders_lines = []
        html_orders_lines = []
        if ordenes:
            text_orders_lines.append(f"🤖 *Órdenes del Asistente - ID: {request_id}* 🤖\n")
            html_orders_lines.append(f"<h1>🤖 Órdenes del Asistente - ID: {request_id}</h1>")
            for orden in ordenes:
                emoji = "🟢" if orden.recommendation == "COMPRAR" else "🔴" if orden.recommendation == "VENDER" else "⚪️"
                text_orders_lines.extend([
                    f"*{orden.ticker.upper()}*",
                    f"{emoji} *Acción:* {orden.recommendation}",
                    f"🔢 *Cantidad:* {orden.cantidad}",
                    f"💵 *Precio:* ${orden.action_price:,.2f} ({orden.moneda})",
                    f"🤔 *Razón:* {orden.reasoning}\n"
                ])
                html_orders_lines.extend([
                    f"<h2>{orden.ticker.upper()}</h2>",
                    f"<p><strong>{emoji} Acción:</strong> {orden.recommendation}</p>",
                    f"<p><strong>🔢 Cantidad:</strong> {orden.cantidad}</p>",
                    f"<p><strong>💵 Precio:</strong> ${orden.action_price:,.2f} ({orden.moneda})</p>",
                    f"<p><strong>🤔 Razón:</strong> {orden.reasoning}</p><hr>"
                ])
        
        # --- 2. Construir Mensaje de Recomendaciones de Mercado ---
        text_recos_lines = []
        html_recos_lines = []
        if recomendaciones:
            text_recos_lines.append(f"📊 *Recomendaciones de Mercado - ID: {request_id}* 📊\n")
            html_recos_lines.append(f"<br><h1>📊 Recomendaciones de Mercado</h1>")
            current_category = ""
            for reco in recomendaciones:
                if reco.categoria != current_category:
                    text_recos_lines.append(f"\n*{reco.categoria}*")
                    html_recos_lines.append(f"<h2>{reco.categoria}</h2>")
                    current_category = reco.categoria
                
                text_recos_lines.extend([
                    f"• *Ticker:* {reco.ticker}",
                    f"  *Justificación:* {reco.justificacion}"
                ])
                html_recos_lines.append(f"<p><strong>Ticker:</strong> {reco.ticker}<br><strong>Justificación:</strong> {reco.justificacion}</p>")
        
        # --- 3. Enviar Notificaciones ---
        orders_text_msg = "\n".join(text_orders_lines)
        recos_text_msg = "\n".join(text_recos_lines)
        full_html_msg = "".join(html_orders_lines) + "".join(html_recos_lines)

        # Enviar a WhatsApp
        if whatsapp_recipient:
            if orders_text_msg:
                logger.info(f"[{request_id}] Enviando órdenes operativas a WhatsApp: {whatsapp_recipient}")
                await self._send_whatsapp_text(whatsapp_recipient, orders_text_msg, request_id)
                
                # Generar y enviar audio solo para las órdenes
                audio_dir = settings.DATA_PATH / "temp" / request_id; audio_dir.mkdir(parents=True, exist_ok=True)
                audio_path = audio_dir / f"tactical_orders_{request_id}.mp3"
                audio_text = orders_text_msg.replace("*", "").replace("🤖", "")
                generated_audio_path = await tts_service.text_to_audio(text_to_speak=audio_text, output_audio_path=audio_path)
                if generated_audio_path:
                    await asyncio.sleep(1) # Pausa para que el mensaje de texto llegue primero
                    await self._send_whatsapp_media(whatsapp_recipient, generated_audio_path, "", "audio", request_id)
            
            if recos_text_msg:
                await asyncio.sleep(2) # Pausa para separar los mensajes
                logger.info(f"[{request_id}] Enviando recomendaciones de mercado a WhatsApp: {whatsapp_recipient}")
                await self._send_whatsapp_text(whatsapp_recipient, recos_text_msg, request_id)

        # Enviar a Email
        if email_recipient:
            if full_html_msg:
                logger.info(f"[{request_id}] Enviando reporte táctico completo a Email: {email_recipient}")
                await self._send_email(
                    recipient=email_recipient, 
                    subject=f"Reporte Táctico del Asistente - {request_id}", 
                    body_html=full_html_msg, 
                    attachments=[], 
                    request_id=request_id
                )