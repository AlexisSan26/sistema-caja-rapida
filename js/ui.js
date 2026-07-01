function esc(s) {
    if (s == null) return '';
    return String(s)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function mostrarError(msg) {
    const el = document.getElementById("aviso-error");
    el.textContent = msg || "⚠️ Sin conexión — reintentando...";
    el.style.display = "block";
    clearTimeout(timeoutError);
    timeoutError = setTimeout(() => { el.style.display = "none"; }, 4000);
}

function mostrarFechaDelDia() {
    const opciones = { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' };
    document.getElementById("fecha-actual").innerText = new Date().toLocaleDateString('es-MX', opciones);
}

function irA(pantalla) {
    cerrarEscanerCaja();
    cerrarEscanerInventario();
    cerrarEscanerResurtido();
    cerrarMenu();
    document.querySelectorAll('.pantalla').forEach(p => p.classList.remove('activa'));
    document.querySelectorAll('.menu-item').forEach(b => b.classList.remove('activo'));
    document.getElementById('pantalla-' + pantalla).classList.add('activa');
    document.getElementById('menu-' + pantalla).classList.add('activo');
    const btnFlotante = document.getElementById('btn-flotante');
    btnFlotante.style.display = pantalla === 'inventario' ? 'flex' : 'none';
    if (pantalla === 'inventario') { cargarInventario(); setTimeout(() => document.getElementById("buscador-inventario").focus(), 300); }
    if (pantalla === 'alertas') cargarAlertas();
    if (pantalla === 'fiados') cargarClientes();
    if (pantalla === 'historial') cargarHistorial();
    if (pantalla === 'entradas') cargarEntradas();
    if (pantalla === 'config') cargarConfiguracionTicket();
}

function toggleMenu() {
    const m = document.getElementById('menu-lateral');
    m.style.display = m.style.display === 'block' ? 'none' : 'block';
}

function cerrarMenu() {
    document.getElementById('menu-lateral').style.display = 'none';
}

function construirTicketHTML(datos, idTurno, momentoCierre = null) {
    const fmtFecha = (f, ops) => f ? new Date(f.replace ? f.replace(' ','T') : f).toLocaleDateString('es-MX', ops) : '—';
    const fmtHora  = f => f ? new Date(f.replace ? f.replace(' ','T') : f).toLocaleTimeString('es-MX', { hour:'2-digit', minute:'2-digit' }) : '—';
    let diaOperativo = "Día desconocido";
    if (datos.fecha_apertura) {
        const f = new Date(datos.fecha_apertura);
        if (!isNaN(f.getTime()))
            diaOperativo = f.toLocaleDateString('es-MX', { weekday: 'long', day: 'numeric', month: 'long' });
    }
    const fechaCierre = momentoCierre || (datos.fecha_cierre
        ? `${fmtFecha(datos.fecha_cierre, { day:'2-digit', month:'long' })} ${fmtHora(datos.fecha_cierre)}`
        : null);
    const subtitulo = `
        <div class="d-flex justify-content-between mt-1" style="font-size:.8rem; color:#666;">
            <span>🟢 Ap: ${fmtFecha(datos.fecha_apertura, { day:'2-digit', month:'short' })} ${fmtHora(datos.fecha_apertura)}</span>
            <span>🔴 Ci: ${fechaCierre || '—'}</span>
        </div>`;
    const encabezado = `${diaOperativo}`;

    let deduccionesHTML = "";
    if (datos.reglas_resumen) {
        for (const [nombre, total] of Object.entries(datos.reglas_resumen)) {
            if (total > 0) {
                deduccionesHTML += `<p class="text-muted mb-1">Menos ${nombre}: <strong>-$${total.toFixed(2)}</strong></p>`;
            }
        }
    }
    const bloqueReglas = deduccionesHTML !== "" ? `<hr>${deduccionesHTML}` : "";

    return `<div class="card bg-light p-3 border-dark text-start shadow-sm mt-3">
        <div class="text-center mb-3 border-bottom pb-2">
            <h6 class="mb-0 text-uppercase fw-bold text-primary">${encabezado}</h6>
            ${subtitulo}
        </div>
        <p class="h6 mb-1">Ingresos del Día: <strong>$${(datos.total_ingresos || 0).toFixed(2)}</strong></p>
        ${datos.total_fondo > 0 ? `<p class="h6 mb-1 text-primary">Fondo inicial: <strong>+$${(datos.total_fondo || 0).toFixed(2)}</strong></p>` : ''}
        <p class="h6 mb-1 text-danger">Retiros: <strong>-$${(datos.total_retiros || 0).toFixed(2)}</strong></p>
        <p class="h5 mt-2">Subtotal en Caja: <strong>$${datos.total_en_caja.toFixed(2)}</strong></p>
        ${bloqueReglas}
        <hr style="border-top: 2px solid #000;">
        <p class="h5 mb-1">Efectivo Neto a Entregar:</p>
        <p class="h2 text-success fw-bold">$${datos.total_neto.toFixed(2)}</p>
    </div>`;
}

async function cargarAlertas() {
    document.getElementById("lista-alertas").innerHTML = "<p class='text-center text-muted mt-4'>Cargando...</p>";
    try {
        const res = await fetch(`${API_URL}/alertas`);
        const alertas = await res.json();
        const badge = document.getElementById("badge-alertas");
        if (alertas.length > 0) { badge.textContent = alertas.length; badge.style.display = "inline"; }
        else { badge.style.display = "none"; }
        if (alertas.length === 0) { document.getElementById("lista-alertas").innerHTML = "<p class='text-center text-success mt-4'>✅ Todo en orden, no hay alertas.</p>"; return; }
        document.getElementById("lista-alertas").innerHTML = alertas.map(a => {
            const esCad = a.alerta === 'POR_CADUCAR';
            const color = esCad ? 'border-warning' : 'border-danger';
            const icono = esCad ? '⚠️' : '📉';
            const msg = esCad ? `Caduca: ${a.fecha_caducidad}` : `Stock: ${a.stock_actual} (mín. ${a.stock_minimo})`;
            return `<div class="card mb-2 shadow-sm ${color}" style="border-width:2px;">
                <div class="card-body py-2 px-3">
                    <div class="d-flex justify-content-between">
                        <div><span class="me-1">${icono}</span><strong>${esc(a.nombre_producto)}</strong></div>
                        <small class="text-muted">${msg}</small>
                    </div>
                    ${a.proveedor ? `<small class="text-muted">${esc(a.proveedor)}</small>` : ''}
                </div>
            </div>`;
        }).join("");
    } catch (e) { document.getElementById("lista-alertas").innerHTML = "<p class='text-danger text-center mt-4'>Error al cargar alertas.</p>"; }
}