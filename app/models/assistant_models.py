# app/models/assistant_models.py
from pydantic import BaseModel, Field, EmailStr
from typing import List, Optional, Dict, Any, Union

# --- Modelo para la Estructura de Tickers ---
class AssetTickers(BaseModel):
    """Define la estructura para recibir tickers de activos categorizados por tipo."""
    bonos: List[str] = Field(default_factory=list, description="Lista de tickers para Bonos.")
    cedears: List[str] = Field(default_factory=list, description="Lista de tickers para Cedears.")
    acciones: List[str] = Field(default_factory=list, description="Lista de tickers para Acciones.")
    obligaciones_negociables: List[str] = Field(default_factory=list, description="Lista de tickers para Obligaciones Negociables (ONs).")
    fondos: List[str] = Field(default_factory=list, description="Lista de tickers para Fondos Comunes de Inversión (FCIs).")
    otros: List[str] = Field(default_factory=list, description="Otros tickers no categorizados.")

# --- Modelo para la Solicitud de Reporte ---
class ReportRequest(BaseModel):
    """Define los datos esperados para iniciar la generación de un reporte."""
    tickers_by_type: AssetTickers
    whatsapp_recipient_override: Optional[str] = None
    email_recipient_override: Optional[EmailStr] = None

# --- Modelos para una Respuesta de Notificación ---
class NotificationResult(BaseModel):
    success: bool
    message: str

class NotificationStatus(BaseModel):
    recipient: Optional[str] = None
    text_messages: List[NotificationResult] = Field(default_factory=list)
    audio_files: List[NotificationResult] = Field(default_factory=list)
    document_files: List[NotificationResult] = Field(default_factory=list)

# --- Modelo de Respuesta de Reporte ---
class ReportResponse(BaseModel):
    status: str
    message: str
    request_id: str
    analysis_summary: Optional[str] = None
    collected_pdf_count: int = 0
    final_report_filename: Optional[str] = None
    final_report_public_url: Optional[str] = None
    whatsapp_status: Optional[NotificationStatus] = None
    email_status: Optional[NotificationStatus] = None
    error_details: Optional[str] = None

# --- ¡INICIO DE MODELOS ACTUALIZADOS PARA GESTIÓN DE PORTAFOLIO! ---

# Modelo para un Lote de Compra individual
class LoteCompra(BaseModel):
    id_lote: str = Field(..., description="Identificador único para este lote de compra.")
    cantidad: float
    precio_compra: float
    timestamp_compra: str # Formato ISO 8601, ej: "2025-06-10T11:00:00.000Z"

# Modelo para una Posición dentro del Portafolio (compuesta por lotes)
class PortfolioPosition(BaseModel):
    ticker: str
    moneda: str
    liquidacion: str
    lotes_compra: List[LoteCompra] = Field(default_factory=list)
    # --- Campos para facilitar la visualización en el frontend ---
    cantidad: float = 0.0
    precio_promedio_compra: float = 0.0
    tipo_activo: str = "acciones"  # Valor por defecto seguro

# Modelo para el Estado Completo del Portafolio
class PortfolioState(BaseModel):
    cash_disponible_ars: float
    cash_disponible_usd: float
    posiciones: List[PortfolioPosition] = Field(default_factory=list)
    realized_pnl: Dict[str, float] = Field(default_factory=lambda: {"ars": 0.0, "usd": 0.0})

# Modelo para una Orden de Operativa generada por la IA
class OrdenOperativa(BaseModel):
    ticker: str
    moneda: str
    liquidacion: str
    recommendation: str  # COMPRAR, VENDER, MANTENER
    action_price: Optional[float] = Field(None, description="Precio al que se debe ejecutar la acción")
    cantidad: float
    id_lote_a_vender: Optional[str] = Field(None, description="ID del lote a vender (solo para ventas)")
    timestamp_utc: Optional[str] = Field(None, description="Formato ISO 8601, ej: '2025-06-12T17:05:15.123Z'")
    reasoning: str
    confidence_score: float

# Modelo para una Recomendación de Mercado
class RecomendacionMercado(BaseModel):
    categoria: str
    ticker: str
    justificacion: str

# Modelo de Respuesta Final del Endpoint Táctico (alineado con el nuevo prompt)
class TacticalAnalysisResponse(BaseModel):
    request_id: str
    status: str
    message: str
    fecha_generacion_reporte: Optional[str] = None
    fecha_informes_base: Optional[str] = None
    ordenes_operativa: List[OrdenOperativa] = Field(default_factory=list)
    recomendaciones_mercado: List[RecomendacionMercado] = Field(default_factory=list)
    portafolio_actualizado: Optional[PortfolioState] = None
    error_details: Optional[str] = None


# --- Modelos Antiguos (se mantienen por compatibilidad si son usados en otros lugares) ---
class OrderRequest(BaseModel):
    simbolo: str
    tipo: str
    cantidad: float
    tipo_orden: str
    plazo: str
    precio: Optional[float] = None

class OrderResponse(BaseModel):
    status: str
    order_id: Optional[str] = None
    message: str
    details: Optional[Dict[str, Any]] = None

class PortfolioAsset(BaseModel):
    activo: str
    cantidad: float = 0.0
    precio_compra: float = 0.0
    comisiones: float = 0.0
    valor_actual_unidad: Optional[float] = None
    valor_total_actual: Optional[float] = None
    ganancia_perdida: Optional[float] = None