# app/services/scraper_service.py
import logging
import asyncio
from typing import List, Optional, Set, Tuple, Dict, Any
from pathlib import Path

from playwright.async_api import async_playwright, Browser, Page, Playwright, TimeoutError as PlaywrightTimeoutError
from urllib.parse import urljoin

from app.core.config import settings
from app.models.assistant_models import AssetTickers
from app.utils.file_utils import combine_pdfs, download_pdf_direct
from app.core.state_manager import OTPStateManager
from app.services.notification_service import NotificationService
# --- Importamos a nuestros scrapers especialistas ---
from app.services.scrapers.bullmarket_acciones_scraper import BullmarketAccionesScraper
from app.services.scrapers.bullmarket_cedears_scraper import BullmarketCedearsScraper
from app.services.scrapers.bullmarket_bonos_scraper import BullmarketBonosScraper
from app.services.scrapers.bullmarket_opciones_scraper import BullmarketOpcionesScraper

logger = logging.getLogger(__name__)

BULLMARKET_URL_MAP = {
    'bonos': settings.BULLMARKET_BONDS_URL_TEMPLATE,
    'cedears': settings.BULLMARKET_CEDEAX_URL_TEMPLATE,
    'acciones': settings.BULLMARKET_STOCKS_URL_TEMPLATE,
    'fondos': settings.BULLMARKET_FUNDS_URL_TEMPLATE,
    'obligaciones_negociables': settings.BULLMARKET_FUNDS_URL_TEMPLATE,
}

ASSET_TYPE_TO_BYMA_SECURITY = {
    "bonos": "GO",
    "obligaciones_negociables": "CO",
    "acciones": "ST",
    "cedears": "CED",
    "fondos": "FC",
}

# Límite de concurrencia para evitar sobrecarga. Se establece en 1 para forzar ejecución secuencial.
MAX_CONCURRENT_SCRAPERS = 1

class ScraperService:
    def __init__(self):
        # El semáforo se moverá al método asíncrono para evitar el error de event loop.
        pass

    async def _launch_browser(self) -> Tuple[Playwright, Browser]:
        pw_instance = await async_playwright().start()
        browser = await pw_instance.chromium.launch(
            headless=settings.PLAYWRIGHT_HEADLESS,
            args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-gpu"]
        )
        logger.info(f"Navegador Playwright lanzado (headless={settings.PLAYWRIGHT_HEADLESS}).")
        return pw_instance, browser

    async def _close_browser(self, pw_instance: Playwright, browser: Browser):
        if browser and browser.is_connected(): await browser.close()
        if pw_instance: await pw_instance.stop()
        logger.info("Instancia de Playwright y navegador cerrados.")

    def _normalize_tickers(self, ticker_list: List[str]) -> Set[str]:
        normalized_set = set()
        for item in ticker_list:
            tickers = [t.strip().upper() for t in item.split(',') if t.strip()]
            normalized_set.update(tickers)
        return normalized_set

    async def _handle_cookie_consent(self, page: Page):
        selectors = ['button:has-text("Aceptar todo")', 'button:has-text("Aceptar")', '[data-cky-tag="accept-button"]']
        for selector in selectors:
            try:
                await page.locator(selector).first.click(timeout=2500)
                logger.info(f"Banner de cookies aceptado con selector: '{selector}'")
                await page.wait_for_timeout(500)
                return
            except PlaywrightTimeoutError: continue
        logger.info("No se encontró un banner de cookies obvio.")

    async def _scrape_bacs_report(self, browser: Browser, report_type: str, directory: Path) -> Optional[Path]:
        page = None
        report_map = { 'mensual': {'li_selector': '#menu-item-5897', 'filename': 'BACS_InformeMensual.pdf'}, 'diario': {'li_selector': '#menu-item-5896', 'filename': 'BACS_InformeDiario.pdf'} }
        config = report_map.get(report_type)
        if not config: return None
        filepath = directory / config['filename']
        if filepath.exists(): return filepath
        try:
            page = await browser.new_page()
            await page.goto(settings.BACS_BASE_URL, wait_until="domcontentloaded")
            await self._handle_cookie_consent(page)
            await page.locator('#menu-item-5895 > a').click()
            await page.wait_for_timeout(1500)
            link_locator = page.locator(f"{config['li_selector']} a").first
            await link_locator.wait_for(state='visible')
            pdf_url = await link_locator.get_attribute('href')
            if not pdf_url or not pdf_url.endswith('.pdf'): return None
            full_pdf_url = urljoin(settings.BACS_BASE_URL, pdf_url)
            return await download_pdf_direct(full_pdf_url, config['filename'], directory)
        except Exception as e:
            logger.warning(f"Error leve scrapeando BACS ({report_type}): {type(e).__name__}")
            return None
        finally:
            if page and not page.is_closed(): await page.close()

    async def _scrape_balanz_daily(self, browser: Browser, directory: Path) -> Optional[Path]:
        page = None
        filename = "Balanz_InformeDiario.pdf"
        filepath = directory / filename
        if filepath.exists(): return filepath
        try:
            page = await browser.new_page()
            await page.goto(settings.BALANZ_DAILY_REPORTS_URL, wait_until="domcontentloaded")
            await self._handle_cookie_consent(page)
            async with page.expect_download(timeout=30000) as download_info:
                await page.locator('button.download-report:has-text("Síntesis de mercado")').click()
            download = await download_info.value
            await download.save_as(filepath)
            logger.info("Descargado reporte diario de Balanz.")
            return filepath
        except Exception as e:
            logger.warning(f"Error leve scrapeando Balanz: {type(e).__name__}")
            return None
        finally:
            if page and not page.is_closed(): await page.close()

    async def _scrape_pp_daily(self, browser: Browser, directory: Path) -> Optional[Path]:
        page = None
        filename = "PP_InformeDiario.pdf"
        filepath = directory / filename
        if filepath.exists(): return filepath
        try:
            page = await browser.new_page()
            await page.goto(settings.PP_INFORMES_URL, wait_until="domcontentloaded")
            await self._handle_cookie_consent(page)
            first_card_link = page.locator('a.CardNoticiasResearch_cardLink__wKEAu').first
            detail_page_url_path = await first_card_link.get_attribute('href')
            if not detail_page_url_path: return None
            detail_page_url = urljoin(settings.PP_INFORMES_URL, detail_page_url_path)
            await page.goto(detail_page_url)
            download_link = page.locator('a.button:has-text("Ver adjunto")').first
            pdf_url = await download_link.get_attribute('href')
            if not pdf_url: return None
            full_pdf_url = urljoin(detail_page_url, pdf_url)
            return await download_pdf_direct(full_pdf_url, filename, directory)
        except Exception as e:
            logger.warning(f"Error leve scrapeando Portfolio Personal: {type(e).__name__}")
            return None
        finally:
            if page and not page.is_closed(): await page.close()

    async def _scrape_bullmarket_for_ticker(self, browser: Browser, ticker: str, asset_type: str, directory: Path) -> Optional[Path]:
        page = None
        url_template = BULLMARKET_URL_MAP.get(asset_type)
        if not url_template: return None
        url = url_template.format(symbol=ticker) if '{symbol}' in url_template else url_template.format(ticker=ticker)
        filename = f"BullMarket_{asset_type}_{ticker}.pdf"
        filepath = directory / filename
        try:
            page = await browser.new_page()
            await page.goto(url, wait_until="load", timeout=settings.PLAYWRIGHT_DEFAULT_TIMEOUT)
            await page.wait_for_timeout(5000)
            await page.pdf(path=str(filepath), format="A4", landscape=True, print_background=True)
            logger.info(f"PDF de BullMarket para {ticker} guardado.")
            return filepath
        except Exception as e:
            logger.warning(f"Error scrapeando BullMarket para {ticker} en URL {url}: {type(e).__name__}")
            return None
        finally:
            if page and not page.is_closed(): await page.close()

    async def _scrape_bymadata_for_ticker(self, browser: Browser, ticker: str, directory: Path) -> Optional[Path]:
        page = None
        # Esta lógica para determinar el asset_type para BYMA no es ideal, pero replica la del código original.
        # Una mejora futura sería pasar el asset_type explícitamente.
        url = settings.BYMA_TECHNICAL_DETAIL_URL_TEMPLATE.format(symbol=ticker)
        filename = f"BYMA_Tecnico_{ticker}.pdf"
        filepath = directory / filename
        try:
            page = await browser.new_page()
            await page.goto(url, wait_until="domcontentloaded")
            await page.locator('div.mat-tab-label-content:has-text("SERIES HISTÓRICAS")').first.click()
            await page.wait_for_timeout(3000)
            await page.pdf(path=str(filepath), format="A4", landscape=True, print_background=True)
            logger.info(f"PDF de BYMA para {ticker} guardado.")
            return filepath
        except Exception as e:
            logger.warning(f"Error scrapeando BYMA para {ticker} en URL {url}: {type(e).__name__}")
            return None
        finally:
            if page and not page.is_closed(): await page.close()

    async def collect_and_save_reports(self, tickers_by_type: AssetTickers, target_directory: Path) -> List[Path]:
        semaphore = asyncio.Semaphore(MAX_CONCURRENT_SCRAPERS)
        pw_instance, browser = await self._launch_browser()
        collected_paths: List[Path] = []

        async def worker(task):
            async with semaphore:
                return await task

        try:
            static_tasks = [
                self._scrape_bacs_report(browser, 'diario', target_directory),
                self._scrape_bacs_report(browser, 'mensual', target_directory),
                self._scrape_balanz_daily(browser, target_directory),
                self._scrape_pp_daily(browser, target_directory),
            ]
            
            dynamic_tasks_to_run = []
            all_tickers_raw = [*tickers_by_type.bonos, *tickers_by_type.cedears, *tickers_by_type.acciones, *tickers_by_type.obligaciones_negociables, *tickers_by_type.fondos, *tickers_by_type.otros]
            unique_tickers = self._normalize_tickers(all_tickers_raw)
            
            if unique_tickers:
                for ticker in unique_tickers:
                    dynamic_tasks_to_run.append(self._scrape_bymadata_for_ticker(browser, ticker, target_directory))
            
            for asset_type, tickers in tickers_by_type.model_dump().items():
                tickers_for_type = self._normalize_tickers(tickers)
                if tickers_for_type and asset_type in BULLMARKET_URL_MAP:
                    for ticker in tickers_for_type:
                        dynamic_tasks_to_run.append(self._scrape_bullmarket_for_ticker(browser, ticker, asset_type, target_directory))

            worker_tasks = [worker(task) for task in dynamic_tasks_to_run]
            all_tasks = static_tasks + worker_tasks

            if all_tasks:
                logger.info(f"Ejecutando {len(static_tasks)} tareas estáticas y {len(worker_tasks)} tareas dinámicas (concurrencia máxima: {MAX_CONCURRENT_SCRAPERS})...")
                results = await asyncio.gather(*all_tasks, return_exceptions=True)
                for res in results:
                    if isinstance(res, Path):
                        collected_paths.append(res)
                    elif isinstance(res, Exception):
                        logger.error(f"Una tarea de scraping falló de forma controlada: {res}")
        except Exception as e:
            logger.critical(f"Error CRÍTICO en collect_and_save_reports: {e}", exc_info=True)
        finally:
            await self._close_browser(pw_instance, browser)
        
        return collected_paths

    async def combine_and_save_pdfs(self, input_paths: List[Path], output_path: Path) -> Optional[Path]:
        return await combine_pdfs(input_paths, output_path)

    async def scrape_bullmarket_acciones(self, notifier: NotificationService, otp_manager: OTPStateManager) -> List[Dict[str, Any]]:
        logger.info("Iniciando orquestación del scraping de acciones...")
        pw_instance, browser = await self._launch_browser()
        scraped_data: List[Dict[str, Any]] = []
        try:
            acciones_scraper = BullmarketAccionesScraper(browser=browser, notifier=notifier, otp_manager=otp_manager)
            scraped_data = await acciones_scraper.run_full_scrape()
        except Exception as e:
            logger.error(f"Fallo en la orquestación del scraping de acciones: {e}", exc_info=True)
        finally:
            await self._close_browser(pw_instance, browser)
        logger.info(f"Orquestación de acciones finalizada. Total de registros: {len(scraped_data)}")
        return scraped_data

    async def scrape_bullmarket_cedears(self, notifier: NotificationService, otp_manager: OTPStateManager) -> List[Dict[str, Any]]:
        logger.info("Iniciando orquestación del scraping de CEDEARs...")
        pw_instance, browser = await self._launch_browser()
        scraped_data: List[Dict[str, Any]] = []
        try:
            cedears_scraper = BullmarketCedearsScraper(browser=browser, notifier=notifier, otp_manager=otp_manager)
            scraped_data = await cedears_scraper.run_full_scrape()
        except Exception as e:
            logger.error(f"Fallo en la orquestación del scraping de CEDEARs: {e}", exc_info=True)
        finally:
            await self._close_browser(pw_instance, browser)
        logger.info(f"Orquestación de CEDEARs finalizada. Total de registros: {len(scraped_data)}")
        return scraped_data

    async def scrape_bullmarket_bonos(self, notifier: NotificationService, otp_manager: OTPStateManager) -> List[Dict[str, Any]]:
        logger.info("Iniciando orquestación del scraping de Bonos...")
        pw_instance, browser = await self._launch_browser()
        scraped_data: List[Dict[str, Any]] = []
        try:
            bonos_scraper = BullmarketBonosScraper(browser=browser, notifier=notifier, otp_manager=otp_manager)
            scraped_data = await bonos_scraper.run_full_scrape()
        except Exception as e:
            logger.error(f"Fallo en la orquestación del scraping de Bonos: {e}", exc_info=True)
        finally:
            await self._close_browser(pw_instance, browser)
        logger.info(f"Orquestación de Bonos finalizada. Total de registros: {len(scraped_data)}")
        return scraped_data
        
    async def scrape_bullmarket_opciones(self, notifier: NotificationService, otp_manager: OTPStateManager) -> List[Dict[str, Any]]:
        logger.info("Iniciando orquestación del scraping de Opciones...")
        pw_instance, browser = await self._launch_browser()
        scraped_data: List[Dict[str, Any]] = []
        try:
            opciones_scraper = BullmarketOpcionesScraper(browser=browser, notifier=notifier, otp_manager=otp_manager)
            scraped_data = await opciones_scraper.run_full_scrape()
        except Exception as e:
            logger.error(f"Fallo en la orquestación del scraping de Opciones: {e}", exc_info=True)
        finally:
            await self._close_browser(pw_instance, browser)
        logger.info(f"Orquestación de Opciones finalizada. Total de registros: {len(scraped_data)}")
        return scraped_data