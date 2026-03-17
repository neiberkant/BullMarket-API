# app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from pathlib import Path
import os
from typing import Optional

# Resuelve la ruta base del proyecto de forma segura.
BASE_DIR = Path(__file__).resolve().parent.parent.parent

class Settings(BaseSettings):
    PROJECT_NAME: str = "TradingAssistantAPI"
    PROJECT_VERSION: str = "1.0.0"
    PROJECT_DESCRIPTION: str = "API personal para automatización de trading, análisis y monitoreo de mercado."

    # --- Rutas de Archivos Locales ---
    DATA_PATH: Path = BASE_DIR / "data"
    SCRAPED_REPORTS_PATH: Path = DATA_PATH / "scraped_reports"
    AUDIO_REPORTS_PATH: Path = DATA_PATH / "audio_reports"
    MARKET_DATA_PATH: Path = DATA_PATH / "market_data" # NUEVO: Carpeta para los JSON de mercado
    PROMPTS_PATH: Path = BASE_DIR / "prompts"

    # --- URL Pública ---
    PUBLIC_BASE_URL_FOR_FILES: str = Field(..., description="URL base pública para acceder a los archivos generados.")

    # --- Credenciales de Servicios ---
    IOL_API_USER: Optional[str] = None
    IOL_API_PASSWORD: Optional[str] = None

    # --- ¡NUEVO! Credenciales de BullMarket Brokers ---
    BULLMARKET_EMAIL: Optional[str] = Field(None, description="Email de usuario para BullMarket Brokers.")
    BULLMARKET_PASSWORD: Optional[str] = Field(None, description="Contraseña para BullMarket Brokers.")

    GOOGLE_SHEET_ID: Optional[str] = None
    GOOGLE_DRIVE_FOLDER_ID: Optional[str] = None
    GOOGLE_API_CREDENTIALS_PATH: Optional[Path] = None

    # --- Configuración de IA (Gemini) ---
    GEMINI_API_KEY: str
    GEMINI_MODEL_NAME: str = "gemini-1.5-flash-latest"
    PROMPT_FILE_GEMINI: Path = PROMPTS_PATH / "finanzas_prompts.txt"
    GEMINI_TEMPERATURE: float = 0.5
    GEMINI_TOP_P: float = 0.9
    GEMINI_TOP_K: int = 32
    GEMINI_MAX_OUTPUT_TOKENS: int = 8192
    GEMINI_REQUEST_TIMEOUT: int = 720

    # --- Configuración de Notificaciones (Evolution API) ---
    EVOLUTION_API_URL: str
    EVOLUTION_API_KEY: str
    EVOLUTION_INSTANCE_ID: str
    WHATSAPP_RECIPIENT_NUMBER_DEFAULT: Optional[str] = None
    WHATSAPP_TIMEOUT_REQUEST: int = 30

    # --- Configuración de Notificaciones (Email) ---
    EMAIL_SMTP_SERVER: str = "smtp.gmail.com"
    EMAIL_SMTP_PORT: int = 587
    SMTP_USER: str
    SMTP_PASSWORD: str
    EMAIL_FROM_ADDRESS: str
    EMAIL_RECIPIENT_DEFAULT: Optional[str] = None
    EMAIL_USE_TLS: bool = True
    SMTP_TIMEOUT_S: int = 30

    # --- Configuración de Scrapers (Playwright) ---
    PLAYWRIGHT_HEADLESS: bool = True
    PLAYWRIGHT_DEFAULT_TIMEOUT: int = 60000

    # --- URLs de Scraping (Manteniendo tu lista completa) ---
    BACS_BASE_URL: str = "https://bacs.com.ar/"
    ARGOB_INFORMES_URL: str = "https://www.argentina.gob.ar/informes-del-mercado-de-capitales"
    BALANZ_DAILY_REPORTS_URL: str = "https://balanz.com/reportes/daily/"
    PP_INFORMES_URL: str = "https://www.portfoliopersonal.com/research/informes"
    DOLARITO_RIESGO_PAIS_URL: str = "https://www.dolarito.ar/indices/riesgo-pais"
    BULLMARKET_COMMISSIONS_URL: str = "https://help.bullmarketbrokers.com/guia/comisiones/"
    BYMA_TECHNICAL_DETAIL_URL_TEMPLATE: str = "https://open.bymadata.com.ar/#/technical-detail-bond?symbol={symbol}&settlementType=2&market=BYMA&securityType=GO"
    BULLMARKET_BONDS_URL_TEMPLATE: str = "https://www.bullmarketbrokers.com/Cotizaciones/Bonos/{symbol}"
    BULLMARKET_CEDEAX_URL_TEMPLATE: str = "https://www.bullmarketbrokers.com/Cotizaciones/Cedears/{symbol}"
    BULLMARKET_STOCKS_URL_TEMPLATE: str = "https://www.bullmarketbrokers.com/Cotizaciones/Acciones/{symbol}"
    BULLMARKET_FUNDS_URL_TEMPLATE: str = "https://www.bullmarketbrokers.com/Information/FundData?ticker={ticker}"

    # --- Configuración de Text-to-Speech (TTS) ---
    TTS_LANGUAGE_CODE: str = "es-ES"

    model_config = SettingsConfigDict(
        env_file=BASE_DIR / ".env",
        env_file_encoding='utf-8',
        extra='ignore'
    )

settings = Settings()

# Creación de directorios necesarios al iniciar
try:
    os.makedirs(settings.SCRAPED_REPORTS_PATH, exist_ok=True)
    os.makedirs(settings.AUDIO_REPORTS_PATH, exist_ok=True)
    os.makedirs(settings.MARKET_DATA_PATH, exist_ok=True) # NUEVO: Crear carpeta para JSONs
    os.makedirs(settings.PROMPTS_PATH, exist_ok=True)
except Exception as e:
    print(f"ADVERTENCIA: No se pudieron crear los directorios de datos/prompts. Error: {e}")