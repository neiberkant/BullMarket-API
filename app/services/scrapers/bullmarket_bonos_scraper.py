# app/services/scrapers/bullmarket_bonos_scraper.py
import logging
import asyncio
import uuid
from datetime import datetime
from typing import List, Dict, Any, Optional

from playwright.async_api import Browser, Page, TimeoutError as PlaywrightTimeoutError

from app.core.config import settings
from app.core.state_manager import OTPStateManager
from app.services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class BullmarketBonosScraper:
    """
    Scraper especializado en la extracción de datos de la tabla de Bonos de Bull Market.
    """

    def __init__(
        self,
        browser: Browser,
        notifier: NotificationService,
        otp_manager: OTPStateManager
    ):
        self.browser = browser
        self.page: Optional[Page] = None
        self.notifier = notifier
        self.otp_manager = otp_manager
        self.otp_manager = otp_manager
        self.login_request_id = f"login_bonos_{uuid.uuid4().hex[:8]}"

    async def _parse_price(self, price_str: str) -> float:
        """Limpia la cadena de texto de un precio/cantidad y la convierte a float."""
        if price_str == "N/A" or not price_str.strip() or price_str == "-":
            return 0.0
        
        # Ignorar strings que parecen ser horas (HH:MM:SS) para no spamear warnings
        if ":" in price_str and len(price_str.split(":")) == 3:
            return 0.0
            
        try:
            clean_str = price_str.upper().replace('$', '').replace('USD', '').replace('ARS', '').replace('CCL', '').replace('MEP', '').strip()
            clean_str = clean_str.replace('%', '')
            
            multiplier = 1.0
            if 'K' in clean_str:
                clean_str = clean_str.replace('K', '')
                multiplier = 1000.0
            elif 'M' in clean_str:
                clean_str = clean_str.replace('M', '')
                multiplier = 1000000.0
                
            clean_str = clean_str.strip()
            if not clean_str:
                return 0.0
                
            clean_str = clean_str.replace('.', '').replace(',', '.')
            return float(clean_str) * multiplier
        except Exception as e:
            logger.warning(f"Error parseando precio '{price_str}': {e}")
            return 0.0

    async def _login(self) -> bool:
        self.page = await self.browser.new_page()
        page = self.page
        try:
            logger.info(f"[{self.login_request_id}] Iniciando proceso de login para Bonos...")
            await page.goto("https://www.bullmarketbrokers.com/Security/SignIn", wait_until="domcontentloaded")
            await page.locator('input#Email').fill(settings.BULLMARKET_EMAIL)
            await page.locator('input#Password').fill(settings.BULLMARKET_PASSWORD)
            await asyncio.gather(
                page.wait_for_load_state("domcontentloaded", timeout=30000),
                page.locator('button#submitButton').click(),
            )
            
            try:
                await page.wait_for_function(
                    "() => window.location.href.includes('/Clients/Dashboard') || document.querySelector('input#Otp') !== null",
                    timeout=15000
                )
            except PlaywrightTimeoutError:
                pass

            current_url = page.url
            logger.info(f"[{self.login_request_id}] Evaluación post-login. URL actual: {current_url}")
            if "/Clients/Dashboard" in current_url:
                logger.info(f"[{self.login_request_id}] ¡Éxito! Redirección directa al Dashboard detectada.")
                return True
            elif await page.locator("input#Otp").is_visible():
                logger.info(f"[{self.login_request_id}] Página de OTP detectada. Procediendo con 2FA...")
                return await self._handle_2fa()
            else:
                raise Exception("No se pudo determinar el resultado del login.")
        except Exception as e:
            logger.error(f"[{self.login_request_id}] Fallo crítico durante el login: {e}", exc_info=True)
            if self.page:
                await self.page.screenshot(path=settings.DATA_PATH / "temp" / f"login_error_{self.login_request_id}.png")
            return False

    async def _handle_2fa(self) -> bool:
        if not self.page: return False
        page = self.page
        whatsapp_button = page.locator("button#btnResendCodeWhatsApp")
        if not await whatsapp_button.is_disabled():
            await whatsapp_button.click()
        form_url = f"{settings.PUBLIC_BASE_URL_FOR_FILES.rstrip('/')}/otp/form/{self.login_request_id}"
        message = f"BullMarket solicitó un código de verificación. Ingrésalo aquí: {form_url}"
        recipient = settings.WHATSAPP_RECIPIENT_NUMBER_DEFAULT
        if not recipient: return False
        await self.notifier._send_whatsapp_text(recipient, message, self.login_request_id)
        max_wait_time = 120; wait_interval = 3
        for _ in range(max_wait_time // wait_interval):
            otp_code = await self.otp_manager.get_otp(self.login_request_id)
            if otp_code:
                await page.locator("input#Otp").press_sequentially(otp_code, delay=100)
                button_selector = "#formSignInWithOtp #submitButton"
                await page.wait_for_function(f"document.querySelector('{button_selector}').disabled === false", timeout=5000)
                await page.locator(button_selector).click()
                await page.wait_for_url("**/Clients/Dashboard**", timeout=25000)
                return True
            
            # Registrar que seguimos esperando por OTP
            await self.otp_manager.set_otp(self.login_request_id, "WAITING")
            await asyncio.sleep(wait_interval)
        
        # Al finalizar, limpiamos el estado
        await self.otp_manager.set_otp(self.login_request_id, "TIMEOUT")
        raise TimeoutError(f"Tiempo de espera agotado para recibir el código OTP.")

    async def _scrape_table_data(self, metadata: Dict[str, str]) -> List[Dict[str, Any]]:
        if not self.page: return []
        page = self.page
        scraped_data = []
        try:
            await page.locator("table#prices-table tbody tr[data-key]").first.wait_for(state='visible', timeout=15000)
        except PlaywrightTimeoutError:
            logger.warning(f"No se encontraron datos en la tabla para la combinación: {metadata}")
            return []
        rows = await page.locator("table#prices-table tbody tr[data-key]").all()
        logger.info(f"Encontradas {len(rows)} filas para la combinación: {metadata}")
        for row in rows:
            async def get_text(selector, default="N/A"):
                try: return await row.locator(selector).inner_text()
                except (PlaywrightTimeoutError, Exception): return default

            asset_data = {
                "simbolo": await get_text("span.product-ticker"),
                "ultimo_precio": await self._parse_price(await get_text("td:nth-child(2)")),
                "variacion_diaria": await self._parse_price(await get_text("td:nth-child(3)")),
                "precio_cierre": await self._parse_price(await get_text("td:nth-child(4)")),
                "cantidad_compra": await self._parse_price(await get_text("td:nth-child(5)")),
                "precio_compra": await self._parse_price(await get_text("td:nth-child(6)")),
                "precio_venta": await self._parse_price(await get_text("td:nth-child(7)")),
                "cantidad_venta": await self._parse_price(await get_text("td:nth-child(8)")),
                "volumen_nominal": await self._parse_price(await get_text("td:nth-child(10)")),
                "monto": await self._parse_price(await get_text("td:nth-child(11)")),
                "operaciones": await self._parse_price(await get_text("td:nth-child(12)")),
                "hora": await get_text("td:nth-child(13)"),
                "timestamp": datetime.now().isoformat()
            }
            asset_data.update(metadata)
            scraped_data.append(asset_data)
        return scraped_data

    async def run_full_scrape(self) -> List[Dict[str, Any]]:
        all_scraped_data = []
        login_successful = await self._login()
        if not login_successful or not self.page:
            logger.error("El login falló o no se pudo crear la página. Abortando el scraping de Bonos.")
            return []
        
        page = self.page
        target_url = "https://www.bullmarketbrokers.com/Cotizaciones/Bonos"
        logger.info("Login exitoso. Navegando a la página de cotizaciones de Bonos...")
        await page.goto(target_url, wait_until="domcontentloaded", timeout=30000)
        await page.wait_for_timeout(3500)

        tipos = ["Todos", "Soberanos", "Provinciales"]
        monedas = ["Pesos", "Dólares", "Dólares CCL"]
        liquidaciones = ["24hs", "CI"]

        # --- BUCLE DE SCRAPING CON SELECTORES PRECISOS ---
        # Localizamos los contenedores de los grupos de filtros para ser específicos
        tipo_group = page.locator(".filter-group:has-text('Tipo:')")
        moneda_group = page.locator(".filter-group:has-text('Moneda:')")
        liquidacion_group = page.locator(".filter-group:has-text('Liquidación:')")

        for tipo in tipos:
            logger.info(f"--- Tipo: {tipo} ---")
            # Usamos el contenedor del grupo para encontrar el botón correcto
            await tipo_group.get_by_role("button", name=tipo, exact=True).click()
            await page.wait_for_timeout(3500)
            
            for moneda in monedas:
                logger.info(f"--- Moneda: {moneda} ---")
                await moneda_group.get_by_role("button", name=moneda, exact=True).click()
                await page.wait_for_timeout(3500)
                
                for liquidacion in liquidaciones:
                    logger.info(f"--- Liquidación: {liquidacion} ---")
                    await liquidacion_group.get_by_role("button", name=liquidacion, exact=True).click()
                    await page.wait_for_timeout(3500)
                    
                    metadata = {"tipo": tipo, "moneda": moneda, "liquidacion": liquidacion}
                    all_scraped_data.extend(await self._scrape_table_data(metadata))
        
        await self.page.close()
        logger.info(f"Scraping completo. Total de registros recolectados para Bonos: {len(all_scraped_data)}")
        return all_scraped_data