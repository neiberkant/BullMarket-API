# app/core/lifespan.py
from contextlib import asynccontextmanager
from fastapi import FastAPI
from playwright.async_api import async_playwright, Browser

# Variable global para el browser de Playwright
# TODO: Implementar la gestión del browser de Playwright aquí
# para iniciarlo al inicio de la app y cerrarlo al finalizar.

# async def startup_event():
#     """Eventos a ejecutar al iniciar la aplicación."""
#     print("Starting up Trading Assistant API...")
#     # TODO: Iniciar Playwright browser instance
#     # global browser_instance
#     # pw = await async_playwright().start()
#     # browser_instance = await pw.chromium.launch() # O firefox/webkit

# async def shutdown_event():
#     """Eventos a ejecutar al apagar la aplicación."""
#     print("Shutting down Trading Assistant API...")
#     # TODO: Cerrar Playwright browser instance
#     # global browser_instance
#     # if browser_instance:
#     #     await browser_instance.close()

# @asynccontextmanager
# async def lifespan(app: FastAPI):
#     """Context manager for the application lifespan."""
#     await startup_event()
#     yield
#     await shutdown_event()

# Si no se usa lifespan (FastAPI < 0.65), puedes usar eventos de startup/shutdown directamente:
# app.add_event_handler("startup", startup_event)
# app.add_event_handler("shutdown", shutdown_event)

# Por ahora, se deja como placeholder. La gestión del browser se puede hacer por instancia
# en el ScraperService si es más simple, o centralizar aquí.
# Centralizar aquí es más eficiente si muchas requests usan el mismo browser.