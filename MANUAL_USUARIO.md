# Manual de Usuario - BullMarket API (La API para BullMarket líder en Argentina) 🇦🇷

Este manual detalla el funcionamiento técnico, la configuración de integraciones y la lógica de negocio de la API.

---

## 1. Configuración de Evolution API (WhatsApp)

La Evolution API se utiliza para enviar notificaciones en tiempo real y gestionar el logueo que requiere códigos OTP.

### Pasos para el Logueo:
1.  **Instancia**: Debes tener una instancia creada en tu servidor de Evolution API (ej: `TradingBot`).
2.  **Variables de Entorno**:
    *   `EVOLUTION_API_URL`: La URL base de tu servidor (https://api.tuservidor.com).
    *   `EVOLUTION_API_KEY`: El token de seguridad global o de instancia.
    *   `EVOLUTION_INSTANCE_ID`: El nombre de la instancia conectada.
3.  **Vinculación**: Asegúrate de que el número de WhatsApp esté vinculado escaneando el código QR desde el panel de Evolution API.
4.  **Uso en la API**: La API enviará automáticamente un mensaje de WhatsApp cuando BullMarket solicite un código 2FA/OTP. El mensaje contendrá un link a un formulario interno para que el usuario ingrese el código recibido por SMS o Email.

---

## 2. Lógica de IA: Manejo de Compra y Venta por Lotes

El sistema utiliza un modelo de **gestión de portafolio granular**. En lugar de ver una posición como una masa indiferenciada (ej: 100 acciones de GGAL), la API las trata como **Lotes de Compra**.

### ¿Cómo funciona?
*   **Compra**: Cada vez que la IA decide comprar, se crea un objeto `LoteCompra` con un `id_lote` único, `precio_compra` y `timestamp`.
*   **Análisis Táctico**: La IA (Gemini) recibe el historial completo de estos lotes. Esto le permite ser extremadamente precisa. Puede decidir:
    *   *"Vender el lote COMPRA_G_123 porque ya alcanzó un 15% de ganancia, pero mantener el lote COMPRA_G_456 que está en pérdida para promediar."*
*   **Eficiencia Impositiva**: La venta por lotes específicos permite al usuario elegir qué lotes liquidar primero, optimizando el cálculo de ganancias de capital.
*   **Determinismo**: El cálculo del "Realized P&L" se realiza en el backend restando el costo del lote específico contra el precio de venta propuesto por la IA.

---

## 3. Fuentes de Información y Comisiones

Para garantizar un análisis profesional y un cálculo exacto del capital, la API implementa lo siguiente:

### Fuentes Fundamentales (Análisis PDF):
La IA procesa en tiempo real informes de research para complementar los datos de precios. Las fuentes integradas son:
*   **BACS**: Informes diarios de renta fija y variable.
*   **Balanz**: Reportes de "Daily" y estrategia de mercado.
*   **PPY (Portfolio Personal Inversiones)**: Informes de research y estrategia.
*   **Argentina.gob.ar**: Informes oficiales del Mercado de Capitales.

### Estructura de Comisiones:
El backend aplica automáticamente los costos operativos de BullMarket para que el portafolio refleje la realidad neta:
*   **Acciones y CEDEARs**: 0.33% (incluye derechos de mercado e IVA sobre comisión).
*   **Bonos y Renta Fija**: 0.26%.

---

## 4. Guía de Endpoints y Acceso

### ¿Cómo ingresar y probar la API?
Una vez que el servidor esté corriendo (localmente en `http://localhost:8000` o en tu servidor configurado), puedes acceder a la interfaz interactiva para probar cada endpoint:

*   **Swagger UI (Recomendado)**: [http://localhost:8000/docs](http://localhost:8000/docs) - Permite probar los endpoints en tiempo real.
*   **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc) - Documentación técnica limpia y detallada.

### Listado de Endpoints Principales:

#### 🤖 Módulo Assistant (`/assistant`)
Este módulo centraliza la interacción inteligente con el portafolio y el análisis fundamental.
*   `POST /assistant/generar-reporte`: **Generar Reporte Integral**. Recibe una lista de tickers (Bonos, CEDEARS, Acciones) y genera un análisis de Gemini basado en reportes PDF scrapeados y archivos subidos por el usuario.
*   `GET /assistant/portfolio/view`: **Ver Portafolio**. Retorna el estado actual del portafolio: efectivo disponible, posiciones abiertas y lotes de compra.
*   `POST /assistant/portfolio/run`: **Ejecución Automática**. El comando principal que lee el mercado, aplica la estrategia de la IA y genera órdenes de compra/venta automáticas.

#### 📊 Módulo Market Data (`/market`)
Utilizado para mantener actualizada la base de datos de precios local.
*   `POST /market/acciones/update`: Scrapea y actualiza los precios de acciones líderes y generales de BullMarket.
*   `POST /market/cedears/update`: Scrapea y actualiza los precios de todos los CEDEARs (ARS/USD).
*   `POST /market/bonos/update`: Scrapea y actualiza los precios de bonos soberanos y corporativos.
*   `GET /market/{tipo}/view`: Permite consultar los datos recolectados (ej: `/market/acciones/view`).

#### 🧠 Módulo Análisis On-Demand (`/analisis`)
Para consultas específicas fuera del flujo automático.
*   `POST /analisis/tactico`: Permite solicitar a Gemini un análisis técnico/táctico sobre un grupo específico de activos basándose en moneda y plazo de liquidación.

#### 🔑 Módulo de Seguridad OTP (`/otp`)
*   `GET /otp/form/{request_id}`: Interfaz web para que el usuario ingrese manualmente el código OTP cuando el bot lo requiere para loguearse en BullMarket.
*   `GET /otp/status`: Consulta si hay solicitudes de OTP pendientes de ingreso.

---

## 5. Integración con OPEN CLAW

Esta API es **100% compatible con OPEN CLAW**. Para usarla, simplemente importa la especificación OpenAPI (disponible en `/docs`) dentro de un Skill de OPEN CLAW.

### ¿Por qué es mejor usar la API con OPEN CLAW?
Integrar la **BullMarket API** como Skill ofrece ventajas críticas sobre el uso de modelos de lenguaje genéricos:
1.  **Cero Consumo de Tokens del Modelo Base**: La API procesa toda la lógica financiera y el análisis de mercado de forma independiente. OPEN CLAW solo necesita enviar una instrucción simple, ahorrando miles de tokens en su modelo principal.
2.  **Lógica Controlada y Determinística**: La API maneja las matemáticas de comisiones, balances y lotes de forma exacta mediante código, evitando que el modelo de IA "alucine" con los números de tu cuenta.
3.  **Capacidades Especializadas**: Control total sobre el portafolio, generación de audios gTTS y gestión de alertas críticas vía WhatsApp.

---
### 📜 Licencia y Autorización
Aunque el uso de esta API es **GRATUITO**, el código está protegido por derechos de autor. Su uso debe estar expresamente **autorizado por Neiber Kant**.

**Créditos: Neiber Kant. Dr. Luna Galli**
