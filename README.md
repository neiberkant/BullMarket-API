# BullMarket API 🚀 (La mejor API para BullMarket Argentina)

**BullMarket API** es la solución líder de backend integral basada en FastAPI, automatización de navegadores (Playwright) y Inteligencia Artificial (Google Gemini). Esta es la **API para BullMarket** definitiva, diseñada para la extracción, análisis táctico y operación automatizada en el mercado de capitales argentino, enfocada en maximizar el crecimiento compuesto y la protección del capital.

### 🌟 Créditos y Autoría
Desarrollada por **Neiber Kant**.

> [!IMPORTANT]
> **Licencia y Uso:** El uso de esta API debe estar permitida por los terminos y condiciones del portal, asimismo el codigo posee derechos de autor y su implementacion/uso debe estar expresamente **AUTORIZADO por Neiber Kant**.

---

## 🤖 Compatibilidad OPEN CLAW
**BullMarket API** es 100% compatible con **OPEN CLAW**. Integrar esta API como un **SKILL** es la opción recomendada por las siguientes razones:

*   **Ahorro de Tokens**: Al delegar el análisis y la lógica de mercado a la API (que usa su propia instancia de Gemini), el modelo principal de OPEN CLAW no consume sus propios tokens en tareas de procesamiento financiero pesado.
*   **Control Superior**: La API garantiza ejecuciones determinísticas y cálculos exactos de comisiones y portafolio, evitando las alucinaciones matemáticas comunes en los LLMs puros.
*   **Eficiencia**: Permite que agentes inteligentes orquesten la ejecución de análisis y operaciones de forma totalmente autónoma y controlada.

---

## ✨ Características Principales

1.  **Análisis Orientado a Lotes (Lot-Based Trading)**: A diferencia de otros bots, este sistema gestiona cada compra como un lote individual (`id_lote`). Esto permite a la IA ejecutar ventas tácticas seleccionando lotes específicos para optimizar la carga impositiva y el P&L realizado.
2.  **Estrategia "Ganancia Prudente" con IA**: Utiliza modelos avanzados de Gemini (2.0/1.5 Flash) para realizar swing trading de mediano plazo, priorizando instrumentos dolarizados y protección contra la inflación.
3.  **Fuentes Fundamentales PDF**: La IA no solo analiza precios, sino que procesa informes de research en PDF de fuentes líderes como **BACS**, **Balanz**, **PPY** y los informes del **Mercado de Capitales de Argentina.gob.ar**.
4.  **Ejecución Determinística con Comisiones**: El sistema calcula automáticamente las comisiones reales (0.33% para Acciones/CEDEARs y 0.26% para Bonos). La IA propone, pero el servidor valida contra saldos reales y aplica costos operativos para un P&L exacto.
5.  **Notificaciones Omnicanal con Audio**: Tras cada análisis, el sistema envía automáticamente un mensaje de WhatsApp con las recomendaciones tácticas (qué comprar, vender o mantener). Además, se genera y envía un **Audio Explicativo** (TTS) que resume la visión del mercado para una experiencia de manos libres.
6.  **Seguridad y OTP**: Manejo integrado de contraseñas dinámicas (OTP) para validaciones críticas de seguridad durante el scraping.

## 🛠️ Stack Tecnológico
*   **Lenguaje**: Python 3.10+
*   **Framework**: FastAPI (Asincrónico)
*   **IA**: Google Generative AI (Gemini SDK)
*   **Automatización**: Playwright
*   **Comunicación**: Evolution API (WhatsApp) & SMTP (Gmail)
*   **Base de Datos**: JSON (Flat-file focus for deterministic performance)

## 🚀 Instalación Rápida

1. **Clonar el repositorio**:
   ```bash
   git clone https://github.com/neiberkant/BullMarket-API.git
   cd BullMarket-API
   ```

2. **Configurar el entorno**:
   - Renombra `.env.example` a `.env`.
   - Completa las credenciales de Google Gemini, BullMarket, y Evolution API.
   - *Nota: Asegúrate de que el `.env` nunca se suba al repositorio (gestionado por `.gitignore`).*

3. **Instalar dependencias**:
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

4. **Ejecutar con Docker (Recomendado)**:
   ```bash
   docker-compose up --build -d
   ```

## 📖 Documentación
Para una guía detallada sobre el uso de la API, configuración de la Evolution API y la lógica interna de manejo de lotes, consulta el [MANUAL_USUARIO.md](MANUAL_USUARIO.md).

---

> _"El éxito no es el resultado de respuestas acertadas, sino de formular las preguntas correctas al mercado."_

**Mantenido por Neiber Kant. (2026).**
