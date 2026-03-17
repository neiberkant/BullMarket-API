// URL base relativas ya que corremos en la misma API
const API_BASE = '/api/v1';

// Formateador de moneda
const formatCurrency = (value, currency = 'ARS') => {
    return new Intl.NumberFormat('es-AR', {
        style: 'currency',
        currency: currency,
        minimumFractionDigits: 2
    }).format(value);
};

// --- NAVIGATION LOGIC ---
document.querySelectorAll('.nav-item').forEach(item => {
    item.addEventListener('click', (e) => {
        e.preventDefault();
        // Update active class on nav
        document.querySelectorAll('.nav-item').forEach(nav => nav.classList.remove('active'));
        item.classList.add('active');

        // Update active view
        const targetId = `view-${item.dataset.target}`;
        document.querySelectorAll('.view').forEach(view => {
            view.style.display = 'none';
        });
        document.getElementById(targetId).style.display = 'block';
    });
});

// Set current date string
const dateOptions = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
document.getElementById('currentDate').textContent = new Date().toLocaleDateString('es-AR', dateOptions);


// --- API BINDINGS ---

async function refreshPortfolio() {
    try {
        const response = await fetch(`${API_BASE}/portfolio/view`);
        if (!response.ok) throw new Error('Network error');
        const data = await response.json();

        // Update Headers
        document.getElementById('cashArs').textContent = formatCurrency(data.cash_disponible_ars, 'ARS');
        document.getElementById('cashUsd').textContent = formatCurrency(data.cash_disponible_usd, 'USD');

        // Realized PnL logic
        const pnlArsEl = document.getElementById('pnlArs');
        const pnlUsdEl = document.getElementById('pnlUsd');

        pnlArsEl.textContent = formatCurrency(data.realized_pnl.ars, 'ARS');
        pnlArsEl.className = data.realized_pnl.ars >= 0 ? 'positive' : 'negative';

        pnlUsdEl.textContent = formatCurrency(data.realized_pnl.usd, 'USD');
        pnlUsdEl.className = data.realized_pnl.usd >= 0 ? 'positive' : 'negative';

        // Update Table
        const tbody = document.getElementById('positionsBody');
        tbody.innerHTML = '';

        if (!data.posiciones || data.posiciones.length === 0) {
            tbody.innerHTML = '<tr><td colspan="6" class="text-center">No hay posiciones abiertas actualmente.</td></tr>';
            return;
        }

        data.posiciones.forEach(pos => {
            const numShares = formatCurrency(pos.cantidad, pos.moneda).replace(/[^0-9,-]/g, ''); // just number formatting
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td>${pos.tipo_activo.toUpperCase()}</td>
                <td><strong>${pos.ticker}</strong></td>
                <td>${pos.moneda}</td>
                <td>${numShares}</td>
                <td>${formatCurrency(pos.precio_promedio_compra, pos.moneda)}</td>
                <td>${formatCurrency(pos.cantidad * pos.precio_promedio_compra, pos.moneda)}</td>
            `;
            tbody.appendChild(tr);
        });

    } catch (error) {
        console.error("Error fetching portfolio:", error);
    }
}

async function runScraper(type) {
    try {
        // Enviar POST a la ruta de update (fire and forget ya que es background)
        await fetch(`${API_BASE}/market/${type}/update`, { method: 'POST' });
        alert(`Scraper de ${type} iniciado en segundo plano. Los datos se actualizarán pronto.`);
    } catch (error) {
        console.error("Error trigger scraper:", error);
    }
}

// --- OTP POLLING SYSTEM ---
let currentPendingOtpRequest = null;

async function checkOtpStatus() {
    try {
        const response = await fetch(`/otp/status`);
        if (!response.ok) return;
        const data = await response.json();

        const container = document.getElementById('otpAlertContainer');
        const modal = document.getElementById('otpModalOverlay');

        if (data.pending_otp_requests && data.pending_otp_requests.length > 0) {
            currentPendingOtpRequest = data.pending_otp_requests[0]; // tomamos el primero

            // Show alert in topbar
            container.style.display = 'block';
            container.innerHTML = `
                <div class="alert-box">
                    <span>⚠️ OTP Requerido para continuar scraper.</span>
                    <button class="btn-primary" style="padding: 4px 12px; font-size: 0.8rem;" onclick="showOtpModal()">Ingresar Código</button>
                </div>
            `;
        } else {
            currentPendingOtpRequest = null;
            container.style.display = 'none';
            modal.style.display = 'none';
        }
    } catch (e) { console.error('Error polling OTP:', e); }
}

function showOtpModal() {
    document.getElementById('otpModalOverlay').style.display = 'flex';
    document.getElementById('otpValueInput').focus();
    document.getElementById('otpValueInput').value = '';
    document.getElementById('otpErrorMsg').style.display = 'none';
}

async function submitOtpCode() {
    const code = document.getElementById('otpValueInput').value.trim();
    const errorMsg = document.getElementById('otpErrorMsg');

    if (!/^\d{6}$/.test(code)) {
        errorMsg.textContent = 'El código debe tener exactamente 6 dígitos.';
        errorMsg.style.display = 'block';
        return;
    }

    if (!currentPendingOtpRequest) return;

    try {
        const payload = {
            request_id: currentPendingOtpRequest,
            otp_code: code
        };

        const response = await fetch(`/otp/submit`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            document.getElementById('otpModalOverlay').style.display = 'none';
            alert("Código enviado correctamente.");
            // Forzamos actualización de alertas
            setTimeout(checkOtpStatus, 2000);
        } else {
            throw new Error("HTTP " + response.status);
        }
    } catch (e) {
        errorMsg.textContent = 'Ocurrió un error al enviar el código.';
        errorMsg.style.display = 'block';
    }
}

// Polling for OTP requests every 5 seconds
setInterval(checkOtpStatus, 5000);


// --- TACTICAL ANALYSIS FORM ---
document.getElementById('tacticalAnalysisForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    const form = e.target;
    const formData = new FormData(form);

    document.getElementById('tacticalResultArea').style.display = 'block';
    document.getElementById('loadingTactical').style.display = 'block';
    document.getElementById('tacticalResponseContent').innerHTML = '';

    // Convert to query params or send as Form Data since the endpoint expects Form
    try {
        formData.append('enviar_a_gemini', 'true');
        formData.append('adjuntar_reporte_pdf', 'false'); // para velocidad

        // Clean up empty tickers
        const t = formData.get('tickers');
        if (!t.trim()) formData.delete('tickers');

        const response = await fetch(`${API_BASE}/analisis/tactico`, {
            method: 'POST',
            body: formData
        });

        if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || 'Error en la petición');
        }

        const data = await response.json();

        let htmlStr = ``;
        if (data.ordenes_operativa && data.ordenes_operativa.length > 0) {
            htmlStr += `<h4>Órdenes Generadas:</h4>`;
            data.ordenes_operativa.forEach(o => {
                const actionClass = o.recommendation === 'COMPRAR' ? 'buy' : o.recommendation === 'VENDER' ? 'sell' : '';
                htmlStr += `<div class="order-card ${actionClass}">
                    <div style="display:flex; justify-content:space-between;">
                        <strong>${o.ticker}</strong>
                        <span>${o.recommendation} | ${o.cantidad} a $${o.action_price}</span>
                    </div>
                    <p class="text-xs mt-2 text-secondary">${o.reasoning}</p>
                </div>`;
            });
        }

        if (data.recomendaciones_mercado && data.recomendaciones_mercado.length > 0) {
            htmlStr += `<h4 class="mt-4">Visión de Mercado:</h4>`;
            data.recomendaciones_mercado.forEach(r => {
                htmlStr += `<div style="padding-bottom:8px; border-bottom:1px solid rgba(255,255,255,0.1); margin-top:8px;">
                    <strong>${r.categoria}</strong> - ${r.ticker}
                    <p class="text-xs text-secondary mt-2">${r.justificacion}</p>
                </div>`;
            });
        }

        if (htmlStr === '') htmlStr = '<p>No data returned or Gemini skipped.</p>';
        document.getElementById('tacticalResponseContent').innerHTML = htmlStr;

        // Refresh Portfolio as it might have changed
        refreshPortfolio();

    } catch (e) {
        document.getElementById('tacticalResponseContent').innerHTML = `<p class="error-text">Error: ${e.message}</p>`;
    } finally {
        document.getElementById('loadingTactical').style.display = 'none';
    }
});


// Initialization On Load
refreshPortfolio();
checkOtpStatus();
