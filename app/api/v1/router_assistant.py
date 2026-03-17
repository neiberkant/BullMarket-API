# app/api/v1/router_assistant.py

import logging
import uuid
import asyncio
import re
import datetime
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks, status, Form, File, UploadFile
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr
from pathlib import Path
from typing import List, Optional, Dict, Any
from enum import Enum

# Importar modelos, servicios y utilidades
from app.models.assistant_models import (
    ReportRequest, ReportResponse, AssetTickers, 
    TacticalAnalysisResponse, OrdenOperativa, PortfolioState, RecomendacionMercado,
    LoteCompra, PortfolioPosition
)
from app.services.scraper_service import ScraperService
from app.services.analysis_service import AnalysisService
from app.services.notification_service import NotificationService
from app.services.data_service import DataService
from app.core.state_manager import otp_manager
from app.utils.file_utils import save_upload_file
from app.core.config import settings

logger = logging.getLogger(__name__)

# --- Routers ---
assistant_router = APIRouter(prefix="/assistant", tags=["Trading Assistant Reports"])
market_data_router = APIRouter(prefix="/market", tags=["Market Data Monitoring"])
analysis_router = APIRouter(prefix="/analisis", tags=["On-Demand Analysis"])
otp_router = APIRouter(prefix="/otp", tags=["OTP Helper"])


# --- Lógica de Generación de Reportes ---
async def run_report_generation_flow(
    request_id: str,
    request_data: ReportRequest,
    uploaded_files: List[UploadFile],
    scraper: ScraperService,
    analyzer: AnalysisService,
    notifier: NotificationService,
):
    log_prefix = f"[{request_id}]"
    logger.info(f"{log_prefix} Iniciando flujo de reporte en segundo plano...")
    
    workspace_dir = settings.DATA_PATH / "temp" / request_id
    workspace_dir.mkdir(parents=True, exist_ok=True)
    
    try:
        saved_complementary_paths_tasks = [save_upload_file(file, workspace_dir) for file in uploaded_files]
        saved_complementary_paths = [path for path in await asyncio.gather(*saved_complementary_paths_tasks) if path]
        
        # Esta es la funcionalidad principal de este endpoint, siempre se ejecuta con los tickers provistos.
        scraped_pdf_paths = await scraper.collect_and_save_reports(
            tickers_by_type=request_data.tickers_by_type,
            target_directory=workspace_dir
        )
        
        all_pdfs_to_analyze = saved_complementary_paths + scraped_pdf_paths
        if not all_pdfs_to_analyze:
            raise ValueError("No se encontraron PDFs para analizar (ni subidos ni scrapeados).")
            
        combined_pdf_path_for_analysis = await scraper.combine_and_save_pdfs(
            input_paths=all_pdfs_to_analyze,
            output_path=workspace_dir / f"fuentes_combinadas_{request_id}.pdf"
        )
        
        if not combined_pdf_path_for_analysis:
            raise ValueError("No se pudo generar el PDF combinado.")

        logger.info(f"{log_prefix} PDF combinado generado. Enviando a Gemini para análisis...")
        all_tickers_raw = [
            *request_data.tickers_by_type.bonos, *request_data.tickers_by_type.cedears,
            *request_data.tickers_by_type.acciones, *request_data.tickers_by_type.obligaciones_negociables,
            *request_data.tickers_by_type.fondos, *request_data.tickers_by_type.otros
        ]
        flat_tickers = list(scraper._normalize_tickers(all_tickers_raw))
        
        analysis_result = await analyzer.analyze_and_generate_recommendation(
             combined_pdf_path=combined_pdf_path_for_analysis,
             portfolio_data=[],
             tickers=flat_tickers,
             user_identifier=request_id
        )

        logger.info(f"{log_prefix} Análisis de Gemini recibido. Enviando notificaciones...")
        await notifier.send_analysis_notification(
            request_id=request_id,
            analysis_results=analysis_result,
            whatsapp_recipient=request_data.whatsapp_recipient_override,
            email_recipient=request_data.email_recipient_override,
        )
        
        logger.info(f"{log_prefix} Flujo de reporte completado exitosamente.")

    except Exception as e:
        logger.critical(f"{log_prefix} Error crítico en el flujo de reporte: {e}", exc_info=True)


@assistant_router.post("/generar-reporte", response_model=ReportResponse, status_code=status.HTTP_202_ACCEPTED)
async def generar_reporte_y_analisis(
    background_tasks: BackgroundTasks,
    bonos: Optional[str] = Form(None),
    cedears: Optional[str] = Form(None),
    acciones: Optional[str] = Form(None),
    obligaciones_negociables: Optional[str] = Form(None),
    fondos: Optional[str] = Form(None),
    otros_tickers: Optional[str] = Form(None),
    whatsapp_recipient_override: Optional[str] = Form(None),
    email_recipient_override: Optional[EmailStr] = Form(None),
    analisis_complementarios: List[UploadFile] = File([]),
    scraper: ScraperService = Depends(ScraperService),
    analyzer: AnalysisService = Depends(AnalysisService),
    notifier: NotificationService = Depends(NotificationService),
):
    request_id = f"report_{uuid.uuid4().hex[:8]}"
    logger.info(f"[{request_id}] Solicitud de reporte recibida.")
    
    try:
        tickers_data = AssetTickers(
            bonos=[bonos] if bonos else [],
            cedears=[cedears] if cedears else [],
            acciones=[acciones] if acciones else [],
            obligaciones_negociables=[obligaciones_negociables] if obligaciones_negociables else [],
            fondos=[fondos] if fondos else [],
            otros=[otros_tickers] if otros_tickers else []
        )
        request_data = ReportRequest(
            tickers_by_type=tickers_data,
            whatsapp_recipient_override=whatsapp_recipient_override,
            email_recipient_override=email_recipient_override
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Error al procesar datos: {e}")

    background_tasks.add_task(
        run_report_generation_flow, request_id, request_data, analisis_complementarios, scraper, analyzer, notifier
    )
    return ReportResponse(status="accepted", message="Solicitud de reporte y análisis aceptada.", request_id=request_id)


def apply_orders_to_portfolio(current_portfolio: PortfolioState, orders: List[OrdenOperativa]) -> PortfolioState:
    """
    Aplica una lista de órdenes operativas al estado actual del portafolio.
    Calcula comisiones y actualiza cash, posiciones y PnL realizado.
    """
    new_portfolio = current_portfolio.model_copy(deep=True)
    
    for orden in orders:
        ticker = orden.ticker.upper()
        # Determinar comisión según tipo de activo (inferido)
        # Costo Total: Acciones/CEDEARs 0.33%, Bonos 0.26%
        is_bond = any(x in ticker for x in ["AL30", "GD30", "AL29", "AE38", "S31O5", "S27F6", "S10N5"]) or len(ticker) > 5
        comision_rate = 0.0026 if is_bond else 0.0033
        
        monto_bruto = orden.cantidad * (orden.action_price or 0.0)
        costos = monto_bruto * comision_rate
        
        if orden.recommendation == "COMPRAR":
            # Restar del cash (monto + costos)
            if orden.moneda == "ARS":
                new_portfolio.cash_disponible_ars -= (monto_bruto + costos)
            else:
                new_portfolio.cash_disponible_usd -= (monto_bruto + costos)
            
            # Agregar o actualizar posición
            posicion = next((p for p in new_portfolio.posiciones if p.ticker == ticker and p.moneda == orden.moneda and p.liquidacion == orden.liquidacion), None)
            if not posicion:
                posicion = PortfolioPosition(ticker=ticker, moneda=orden.moneda, liquidacion=orden.liquidacion, lotes_compra=[])
                new_portfolio.posiciones.append(posicion)
            
            new_lote = LoteCompra(
                id_lote=f"{ticker}_BUY_{datetime.datetime.now().strftime('%Y%m%dT%H%M%S')}",
                cantidad=orden.cantidad,
                precio_compra=orden.action_price or 0.0,
                timestamp_compra=datetime.datetime.now().isoformat()
            )
            posicion.lotes_compra.append(new_lote)

        elif orden.recommendation == "VENDER" and orden.id_lote_a_vender:
            # Sumar al cash (monto - costos)
            if orden.moneda == "ARS":
                new_portfolio.cash_disponible_ars += (monto_bruto - costos)
            else:
                new_portfolio.cash_disponible_usd += (monto_bruto - costos)
                
            # Buscar y eliminar lote
            for p in new_portfolio.posiciones:
                if p.ticker == ticker:
                    lote = next((l for l in p.lotes_compra if l.id_lote == orden.id_lote_a_vender), None)
                    if lote:
                        # Calcular PnL realizado
                        ganancia_bruta = (orden.action_price - lote.precio_compra) * lote.cantidad
                        pnl_neto = ganancia_bruta - costos 
                        
                        if orden.moneda == "ARS":
                            new_portfolio.realized_pnl["ars"] += pnl_neto
                        else:
                            new_portfolio.realized_pnl["usd"] += pnl_neto
                            
                        p.lotes_compra.remove(lote)
                    break
    
    # Limpiar posiciones vacías
    new_portfolio.posiciones = [p for p in new_portfolio.posiciones if len(p.lotes_compra) > 0]
    
    return new_portfolio

@assistant_router.get("/portfolio/view", response_model=PortfolioState, summary="Ver Portafolio Actual (Alias)")
async def view_portfolio_state_alias(data_service: DataService = Depends(DataService)):
    """Versión simplificada para el dashboard principal."""
    return await data_service.read_portfolio()

@assistant_router.post("/portfolio/run", response_model=TacticalAnalysisResponse, summary="Ejecutar Acción Automatizada sobre Portafolio")
async def run_automated_portfolio_action(
    data_service: DataService = Depends(DataService),
    scraper: ScraperService = Depends(ScraperService),
    analyzer: AnalysisService = Depends(AnalysisService),
    notifier: NotificationService = Depends(NotificationService),
):
    """
    Toma el portafolio actual, descarga los datos de mercado más recientes para todos los activos
    y le pide a Gemini que ejecute acciones de compra/venta para maximizar ganancias.
    """
    request_id = f"auto_run_{uuid.uuid4().hex[:8]}"; log_prefix = f"[{request_id}]"
    logger.info(f"{log_prefix} Iniciando ejecución automática de portafolio.")
    
    try:
        # 1. Leer portafolio actual
        current_portfolio = await data_service.read_portfolio()
        
        # 2. Recolectar datos de mercado (todas las categorías disponibles hoy)
        all_market_data = []
        # Identificar tickers en el portafolio para priorizarlos
        portfolio_tickers = {p.ticker for p in current_portfolio.posiciones}
        
        for tipo in ["acciones", "cedears", "bonos"]:
            try:
                data = await data_service.read_daily_data(data_type=tipo)
                # Filtramos Pesos/USD y 24hs/CI
                filtered = [r for r in data if r.get("moneda") in ["Pesos", "Dólares"] and r.get("liquidacion") in ["24hs", "CI"]]
                
                # OPTIMIZACIÓN DE TOKENS (Equilibrio entre Cobertura y Cuota):
                # 1. Mantener todos los que están en el portafolio (esencial para analizar qué vender)
                in_portfolio = [r for r in filtered if r.get("simbolo") in portfolio_tickers]
                # 2. Tomar las mejores oportunidades del resto (para compra)
                not_in_portfolio = [r for r in filtered if r.get("simbolo") not in portfolio_tickers]
                
                # Ordenar por 'monto' (volumen operado) DESC para asegurar que tickers como MELI o grandes CEDEARs entren.
                not_in_portfolio.sort(key=lambda x: x.get("monto", 0), reverse=True)
                
                # Tomamos hasta 400 de cada categoría. Total ~1200 registros (aprox 60k-80k tokens, seguro para el límite de 250k).
                not_in_portfolio = not_in_portfolio[:400]
                
                all_market_data.extend(in_portfolio)
                all_market_data.extend(not_in_portfolio)
            except Exception as e:
                logger.error(f"{log_prefix} Error al leer datos de {tipo}: {e}")

        if not all_market_data:
             return TacticalAnalysisResponse(request_id=request_id, status="no_data", message="No hay datos de mercado cargados para hoy. Corre los scrapers primero.")

        # 3. Ejecutar análisis táctico con Gemini
        logger.info(f"{log_prefix} Evaluando {len(all_market_data)} activos optimizados contra el portafolio.")
        try:
            gemini_response_dict = await analyzer.run_tactical_analysis(
                historical_data=all_market_data,
                portfolio_state=current_portfolio,
                fundamental_report_path=None,
                user_identifier=request_id
            )
        except Exception as gemini_err:
            logger.error(f"{log_prefix} Fallo en la llamada a Gemini: {gemini_err}")
            return TacticalAnalysisResponse(request_id=request_id, status="error", message=f"Error en la IA: {str(gemini_err)}")

        if not gemini_response_dict or "ordenes_operativa" not in gemini_response_dict:
             return TacticalAnalysisResponse(request_id=request_id, status="error", message="La IA no devolvió un formato válido (faltan órdenes). Reintenta en 1 minuto.")

        # 4. Procesar y Guardar (Backend-side Portfolio update)
        try:
            raw_ordenes = gemini_response_dict.get("ordenes_operativa", [])
            for o in raw_ordenes:
                if not o.get("timestamp_utc"):
                    o["timestamp_utc"] = datetime.datetime.now().isoformat()
            
            ordenes = [OrdenOperativa(**o) for o in raw_ordenes]
            recomendaciones = [RecomendacionMercado(**r) for r in gemini_response_dict.get("recomendaciones_mercado", [])]
            
            # APLICAR ÓRDENES AL PORTAFOLIO LOCALMENTE
            new_portfolio_state = apply_orders_to_portfolio(current_portfolio, ordenes)
            
            # Guardamos el nuevo estado
            await data_service.save_portfolio(new_portfolio_state)
            
            return TacticalAnalysisResponse(
                request_id=request_id,
                status="success",
                message=f"Ejecución automática completada. Se generaron {len(ordenes)} órdenes.",
                fecha_generacion_reporte=gemini_response_dict.get("fecha_generacion_reporte"),
                fecha_informes_base=gemini_response_dict.get("fecha_informes_base"),
                ordenes_operativa=ordenes,
                recomendaciones_mercado=recomendaciones,
                portafolio_actualizado=new_portfolio_state
            )
        except Exception as parse_err:
            logger.error(f"{log_prefix} Error al procesar respuesta o actualizar portafolio: {parse_err}")
            return TacticalAnalysisResponse(request_id=request_id, status="error", message=f"Error en procesamiento: {str(parse_err)}")

    except Exception as e:
        logger.critical(f"{log_prefix} Error en ejecución automática: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --- SECCIONES DE MONITOREO DE MERCADO ---

async def run_full_acciones_scrape(scraper: ScraperService, data_service: DataService, notifier: NotificationService):
    logger.info("Iniciando barrido completo de acciones..."); 
    scraped_data = await scraper.scrape_bullmarket_acciones(notifier=notifier, otp_manager=otp_manager)
    if scraped_data: await data_service.append_daily_data(data_type="acciones", new_data=scraped_data)
    logger.info(f"Barrido de acciones completado. Registros procesados: {len(scraped_data)}")

@market_data_router.post("/acciones/update", status_code=status.HTTP_202_ACCEPTED, summary="Actualizar Datos de Acciones")
async def update_acciones_data(background_tasks: BackgroundTasks, scraper: ScraperService = Depends(ScraperService), data_service: DataService = Depends(DataService), notifier: NotificationService = Depends(NotificationService)):
    background_tasks.add_task(run_full_acciones_scrape, scraper, data_service, notifier)
    return {"status": "accepted", "message": "Solicitud de actualización de acciones aceptada."}

@market_data_router.get("/acciones/view", response_model=List[Dict[str, Any]], summary="Ver Datos de Acciones")
async def view_acciones_data(data_service: DataService = Depends(DataService)):
    return await data_service.read_daily_data(data_type="acciones")

async def run_full_cedears_scrape(scraper: ScraperService, data_service: DataService, notifier: NotificationService):
    logger.info("Iniciando barrido completo de CEDEARs...");
    scraped_data = await scraper.scrape_bullmarket_cedears(notifier=notifier, otp_manager=otp_manager)
    if scraped_data: await data_service.append_daily_data(data_type="cedears", new_data=scraped_data)
    logger.info(f"Barrido de CEDEARs completado. Registros procesados: {len(scraped_data)}")

@market_data_router.post("/cedears/update", status_code=status.HTTP_202_ACCEPTED, summary="Actualizar Datos de CEDEARs")
async def update_cedears_data(background_tasks: BackgroundTasks, scraper: ScraperService = Depends(ScraperService), data_service: DataService = Depends(DataService), notifier: NotificationService = Depends(NotificationService)):
    background_tasks.add_task(run_full_cedears_scrape, scraper, data_service, notifier)
    return {"status": "accepted", "message": "Solicitud de actualización de CEDEARs aceptada."}

@market_data_router.get("/cedears/view", response_model=List[Dict[str, Any]], summary="Ver Datos de CEDEARs")
async def view_cedears_data(data_service: DataService = Depends(DataService)):
    return await data_service.read_daily_data(data_type="cedears")

async def run_full_bonos_scrape(scraper: ScraperService, data_service: DataService, notifier: NotificationService):
    logger.info("Iniciando barrido completo de Bonos...");
    scraped_data = await scraper.scrape_bullmarket_bonos(notifier=notifier, otp_manager=otp_manager)
    if scraped_data: await data_service.append_daily_data(data_type="bonos", new_data=scraped_data)
    logger.info(f"Barrido de Bonos completado. Registros procesados: {len(scraped_data)}")

@market_data_router.post("/bonos/update", status_code=status.HTTP_202_ACCEPTED, summary="Actualizar Datos de Bonos")
async def update_bonos_data(background_tasks: BackgroundTasks, scraper: ScraperService = Depends(ScraperService), data_service: DataService = Depends(DataService), notifier: NotificationService = Depends(NotificationService)):
    background_tasks.add_task(run_full_bonos_scrape, scraper, data_service, notifier)
    return {"status": "accepted", "message": "Solicitud de actualización de Bonos aceptada."}

@market_data_router.get("/bonos/view", response_model=List[Dict[str, Any]], summary="Ver Datos de Bonos")
async def view_bonos_data(data_service: DataService = Depends(DataService)):
    return await data_service.read_daily_data(data_type="bonos")

async def run_full_opciones_scrape(scraper: ScraperService, data_service: DataService, notifier: NotificationService):
    logger.info("Iniciando barrido completo de Opciones...");
    scraped_data = await scraper.scrape_bullmarket_opciones(notifier=notifier, otp_manager=otp_manager)
    if scraped_data: await data_service.append_daily_data(data_type="opciones", new_data=scraped_data)
    logger.info(f"Barrido de Opciones completado. Registros procesados: {len(scraped_data)}")

@market_data_router.post("/opciones/update", status_code=status.HTTP_202_ACCEPTED, summary="Actualizar Datos de Opciones")
async def update_opciones_data(background_tasks: BackgroundTasks, scraper: ScraperService = Depends(ScraperService), data_service: DataService = Depends(DataService), notifier: NotificationService = Depends(NotificationService)):
    background_tasks.add_task(run_full_opciones_scrape, scraper, data_service, notifier)
    return {"status": "accepted", "message": "Solicitud de actualización de Opciones aceptada."}

@market_data_router.get("/opciones/view", response_model=List[Dict[str, Any]], summary="Ver Datos de Opciones")
async def view_opciones_data(data_service: DataService = Depends(DataService)):
    return await data_service.read_daily_data(data_type="opciones")


# --- SECCIÓN DE ANÁLISIS TÁCTICO ON-DEMAND (GESTIÓN DE PORTAFOLIO) ---
class TipoActivo(str, Enum):
    acciones = "acciones"; cedears = "cedears"; bonos = "bonos"; opciones = "opciones"
class Moneda(str, Enum):
    pesos = "Pesos"; dolares = "Dólares"; dolares_ccl = "Dólares CCL"
class Liquidacion(str, Enum):
    ci = "CI"; tf = "24hs"

@analysis_router.post("/tactico", response_model=TacticalAnalysisResponse, summary="Ejecutar Gestión de Portafolio Táctico")
async def perform_tactical_analysis(
    tipo_activo: TipoActivo = Form(..., description="Tipo de activo a analizar."),
    moneda: Moneda = Form(..., description="Moneda de la cotización."),
    liquidacion: Liquidacion = Form(..., description="Plazo de liquidación."),
    tickers: Optional[List[str]] = Form(None, description="Lista de tickers específicos a analizar (opcional). Si se omite, se analiza todo el mercado para el tipo de activo."),
    enviar_a_gemini: bool = Form(True, description="Marcar si se debe enviar la información a Gemini para análisis."),
    adjuntar_reporte_pdf: bool = Form(False, description="Marcar si se deben scrapear y adjuntar los reportes PDF fundamentales."),
    prompt_personalizado: Optional[str] = Form(None, description="Prompt personalizado para sobrescribir el de por defecto."),
    email_destinatario: Optional[str] = Form(None, description="Email para enviar la notificación. Si se deja vacío, no se envía."),
    whatsapp_destinatario: Optional[str] = Form(None, description="Número de WhatsApp para enviar la notificación. Si se deja vacío, no se envía."),
    data_service: DataService = Depends(DataService),
    scraper: ScraperService = Depends(ScraperService),
    analyzer: AnalysisService = Depends(AnalysisService),
    notifier: NotificationService = Depends(NotificationService),
):
    request_id = f"portfolio_mgmt_{uuid.uuid4().hex[:8]}"; log_prefix = f"[{request_id}]"

    cleaned_tickers = [t.strip().upper() for t in tickers if t.strip()] if tickers else []
    tickers_str = ", ".join(cleaned_tickers) if cleaned_tickers else f"todo el mercado de {tipo_activo.value}"
    logger.info(f"{log_prefix} Solicitud de gestión de portafolio recibida para: {tickers_str}.")
    
    try:
        current_portfolio = await data_service.read_portfolio()
        market_data = await data_service.read_daily_data(data_type=tipo_activo.value)
        
        filtered_data = [r for r in market_data if r.get("moneda") == moneda.value and r.get("liquidacion") == liquidacion.value]
        if cleaned_tickers:
            filtered_data = [r for r in filtered_data if r.get("simbolo", "").strip() in cleaned_tickers]
        
        if not filtered_data:
            return TacticalAnalysisResponse(request_id=request_id, status="no_data", message="No se encontraron datos de mercado para los filtros especificados.")

        pdf_path_for_analysis = None
        if adjuntar_reporte_pdf:
            workspace_dir = settings.DATA_PATH / "temp" / request_id; workspace_dir.mkdir(parents=True, exist_ok=True)
            
            tickers_to_scrape_by_type = AssetTickers()
            if cleaned_tickers:
                logger.info(f"Se adjuntarán reportes PDF para {len(cleaned_tickers)} tickers.")
                setattr(tickers_to_scrape_by_type, tipo_activo.value, cleaned_tickers)
            else:
                logger.info("Adjuntando solo reportes de research generales (no se especificaron tickers para el scraping individual).")
            
            pdf_paths = await scraper.collect_and_save_reports(
                tickers_by_type=tickers_to_scrape_by_type, 
                target_directory=workspace_dir
            )
            
            if pdf_paths:
                pdf_path_for_analysis = await scraper.combine_and_save_pdfs(
                    input_paths=pdf_paths, 
                    output_path=workspace_dir / f"reporte_fundamental_{request_id}.pdf"
                )
        
        if not enviar_a_gemini:
            return TacticalAnalysisResponse(request_id=request_id, status="skipped", message="Análisis con Gemini omitido.")
        
        logger.info(f"{log_prefix} Ejecutando análisis táctico con {len(filtered_data)} registros de mercado.")
        gemini_response_dict = await analyzer.run_tactical_analysis(
            historical_data=filtered_data, portfolio_state=current_portfolio,
            fundamental_report_path=pdf_path_for_analysis, user_identifier=request_id, custom_prompt=prompt_personalizado
        )
        
        # --- INICIO DE LA CORRECCIÓN DE ROBUSTEZ ---
        if not isinstance(gemini_response_dict, dict):
            error_msg = f"La respuesta de Gemini no es un diccionario, sino de tipo {type(gemini_response_dict).__name__}."
            logger.error(f"{log_prefix} {error_msg} Respuesta recibida: {str(gemini_response_dict)[:500]}")
            raise HTTPException(status_code=500, detail=error_msg)

        required_keys = ["ordenes_operativa", "recomendaciones_mercado"]
        if not all(key in gemini_response_dict for key in required_keys):
            missing_keys = [key for key in required_keys if key not in gemini_response_dict]
            error_msg = f"La respuesta de Gemini no tuvo el formato esperado. Faltan las claves: {', '.join(missing_keys)}."
            logger.error(f"{log_prefix} {error_msg} Claves recibidas: {list(gemini_response_dict.keys())}")
            raise HTTPException(status_code=500, detail=error_msg)
        # --- FIN DE LA CORRECCIÓN DE ROBUSTEZ ---
        # ACTUALIZACIÓN EN EL BACKEND (No dependemos de Gemini para el portafolio)
        try:
            raw_ordenes = gemini_response_dict.get("ordenes_operativa", [])
            for o in raw_ordenes:
                if not o.get("timestamp_utc"):
                    o["timestamp_utc"] = datetime.datetime.now().isoformat()
                    
            ordenes = [OrdenOperativa(**o) for o in raw_ordenes]
            recomendaciones = [RecomendacionMercado(**r) for r in gemini_response_dict.get("recomendaciones_mercado", [])]
            
            new_portfolio_state = apply_orders_to_portfolio(current_portfolio, ordenes)
            await data_service.save_portfolio(new_portfolio_state)
            
            if whatsapp_destinatario or email_destinatario:
                # El mensaje de notificación puede necesitar el portafolio actualizado
                temp_dict = gemini_response_dict.copy()
                temp_dict["portafolio_actualizado"] = new_portfolio_state.model_dump()
                await notifier.send_tactical_notification(
                    request_id=request_id,
                    full_analysis_response=temp_dict,
                    whatsapp_recipient=whatsapp_destinatario,
                    email_recipient=email_destinatario
                )
            
            return TacticalAnalysisResponse(
                request_id=request_id,
                status="completed",
                message="Gestión de portafolio completada con éxito. Actualizado localmente.",
                fecha_generacion_reporte=gemini_response_dict.get("fecha_generacion_reporte"),
                fecha_informes_base=gemini_response_dict.get("fecha_informes_base"),
                ordenes_operativa=ordenes,
                recomendaciones_mercado=recomendaciones,
                portafolio_actualizado=new_portfolio_state
            )
        except Exception as e:
            logger.error(f"{log_prefix} Error al procesar la decisión de la IA o actualizar portafolio: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        logger.critical(f"{log_prefix} Error fatal en el endpoint de gestión de portafolio: {e}", exc_info=True)
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=str(e))

@analysis_router.get("/portfolio/view", response_model=PortfolioState, summary="Ver Portafolio Actual")
async def view_portfolio_state(data_service: DataService = Depends(DataService)):
    return await data_service.read_portfolio()

# --- SECCIÓN DE MANEJO DE OTP ---
@otp_router.get("/form/{request_id}", response_class=HTMLResponse)
async def get_otp_form(request_id: str):
    submit_url = f"/otp/submit"
    html_content = f"""
    <!DOCTYPE html><html lang="es"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0"><title>Código de Verificación</title><style>body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;display:flex;justify-content:center;align-items:center;height:100vh;background-color:#f4f7f9;margin:0}}.container{{background:white;padding:40px;border-radius:12px;box-shadow:0 8px 24px rgba(0,0,0,0.1);text-align:center;width:90%;max-width:400px}}h1{{color:#333}}p{{color:#666}}input[type='text']{{width:100%;padding:12px;margin:20px 0;border:1px solid #ccc;border-radius:6px;font-size:24px;text-align:center;letter-spacing:10px}}button{{width:100%;padding:14px;background-color:#007bff;color:white;border:none;border-radius:6px;font-size:18px;cursor:pointer;transition:background-color .3s}}button:hover{{background-color:#0056b3}}#message{{margin-top:20px;font-weight:bold}}</style></head>
    <body><div class="container"><h1>Código de Verificación</h1><p>Ingresa el código de 6 dígitos que recibiste para continuar.</p><form id="otpForm"><input type="text" id="otpCode" name="otp_code" maxlength="6" pattern="\\d{{6}}" required autocomplete="one-time-code"><button type="submit">Enviar</button></form><div id="message"></div></div>
    <script>
        document.getElementById('otpForm').addEventListener('submit', async function(e) {{
            e.preventDefault();
            const otpCode = document.getElementById('otpCode').value;
            const messageDiv = document.getElementById('message');
            if (!/^\\d{{6}}$/.test(otpCode)) {{ messageDiv.textContent = 'Por favor, ingresa un código de 6 dígitos.'; messageDiv.style.color = 'red'; return; }}
            const response = await fetch('{submit_url}', {{ method: 'POST', headers: {{ 'Content-Type': 'application/json' }}, body: JSON.stringify({{ request_id: "{request_id}", otp_code: otpCode }}) }});
            const result = await response.json();
            if (response.ok) {{ messageDiv.textContent = result.message; messageDiv.style.color = 'green'; document.getElementById('otpCode').disabled = true; document.querySelector('button').disabled = true; setTimeout(() => window.close(), 2000); }} else {{ messageDiv.textContent = 'Error: ' + (result.detail || 'Ocurrió un error.'); messageDiv.style.color = 'red'; }}
        }});
    </script></body></html>
    """
    return HTMLResponse(content=html_content)

class OTPSubmitRequest(BaseModel):
    request_id: str
    otp_code: str

@otp_router.post("/submit")
async def submit_otp(request: OTPSubmitRequest):
    if not re.match(r"^\d{6}$", request.otp_code):
        raise HTTPException(status_code=400, detail="El formato del código OTP es inválido.")
    await otp_manager.set_otp(request.request_id, request.otp_code)
    return {"message": "¡Gracias! Código recibido. El proceso continuará automáticamente."}

@otp_router.get("/status")
async def get_otp_status():
    """Retorna los requests de OTP que están en estado WAITING y necesitan atención."""
    waiting_requests = await otp_manager.get_pending_requests()
    return {"pending_otp_requests": waiting_requests}