let chartVentasDia = null;

async function cargarResumenDashboardTurno() {
    if (!idTurnoActual) {
        document.getElementById("dash-venta-total").textContent = "$0.00";
        document.getElementById("dash-productos-vendidos").textContent = "0";
        document.getElementById("dash-num-ventas").textContent = "0";
        document.getElementById("dash-retiros").textContent = "$0.00";
        document.getElementById("dash-abonos-lista").innerHTML = "<p class='text-center text-muted mb-3'>No hay turno abierto.</p>";
        document.getElementById("dash-fiados-lista").innerHTML = "";
        if (chartVentasDia) { chartVentasDia.destroy(); chartVentasDia = null; }
        return;
    }
    try {
        const res = await fetch(`${API_URL}/resumen_dashboard_turno/${idTurnoActual}`);
        if (!res.ok) throw new Error("Error al cargar resumen");
        const datos = await res.json();

        document.getElementById("dash-venta-total").textContent = `$${datos.venta_total.toFixed(2)}`;
        document.getElementById("dash-productos-vendidos").textContent = datos.productos_vendidos.toFixed(0);
        document.getElementById("dash-num-ventas").textContent = datos.num_ventas;
        document.getElementById("dash-retiros").textContent = `$${datos.retiros_dia.toFixed(2)}`;

        renderAbonosDashboard(datos.abonos);
        renderFiadosDashboard(datos.fiados);
        renderGraficaVentasDia(datos.grafica);
    } catch (e) {
        mostrarError("No se pudo cargar el resumen del turno.");
    }
}

function renderAbonosDashboard(abonos) {
    const cont = document.getElementById("dash-abonos-lista");
    if (!abonos || abonos.length === 0) { cont.innerHTML = ""; return; }
    cont.innerHTML = abonos.map(a => `
        <div class="card mb-1 shadow-sm border-info" style="border-width:2px;">
            <div class="card-body py-2 px-3 d-flex justify-content-between align-items-center">
                <div>💰 Abono de <strong>${esc(a.cliente)}</strong></div>
                <div class="text-end">
                    <div class="fw-bold text-success">$${a.monto.toFixed(2)}</div>
                    <small class="text-muted">${esc(a.hora)}</small>
                </div>
            </div>
        </div>
    `).join("");
}

function renderFiadosDashboard(fiados) {
    const cont = document.getElementById("dash-fiados-lista");
    if (!fiados || fiados.length === 0) { cont.innerHTML = ""; return; }
    cont.innerHTML = fiados.map(f => `
        <div class="card mb-1 shadow-sm border-warning" style="border-width:2px;">
            <div class="card-body py-2 px-3 d-flex justify-content-between align-items-center">
                <div>📝 Se fió a <strong>${esc(f.cliente)}</strong></div>
                <div class="text-end">
                    <div class="fw-bold">${f.cantidad.toFixed(0)} productos</div>
                    <small class="text-muted">${esc(f.hora || '')}</small>
                </div>
            </div>
        </div>
    `).join("");
}

function renderGraficaVentasDia(grafica) {
    const ctx = document.getElementById("dash-grafica-ventas");
    if (chartVentasDia) { chartVentasDia.destroy(); }
    if (!grafica || grafica.length === 0) { return; }
    const labels = grafica.map(g => `${String(g.hora).padStart(2, '0')}:00`);
    const datos = grafica.map(g => g.total);
    chartVentasDia = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Ventas + Abonos ($)',
                data: datos,
                borderColor: '#198754',
                backgroundColor: '#198754',
                tension: 0.3,
                pointRadius: 4,
                pointBackgroundColor: '#198754',
                fill: false
            }]
        },
        options: {
            responsive: true,
            plugins: { legend: { display: false } },
            scales: { y: { beginAtZero: true } }
        }
    });
}

async function cargarReporteProductos() {
    const dias = document.getElementById("select-dias-reporte").value;
    const lista = document.getElementById("lista-reporte-productos");
    lista.innerHTML = "<p class='text-center text-muted mt-3'>Cargando...</p>";
    try {
        const res = await fetch(`${API_URL}/reporte_productos?dias=${dias}`);
        const productos = await res.json();
        if (!productos || productos.length === 0) {
            lista.innerHTML = "<p class='text-center text-muted mt-3'>Sin ventas en este periodo.</p>";
            return;
        }
        lista.innerHTML = productos.map((p, idx) => `
            <div class="list-group-item d-flex justify-content-between align-items-center">
                <div>
                    <span class="fw-bold text-secondary">#${idx + 1}</span>
                    <span class="ms-2">${esc(p.producto)}</span>
                </div>
                <div class="text-end">
                    <div class="fw-bold">${parseFloat(p.unidades_vendidas).toFixed(0)} und.</div>
                    <small class="text-muted">$${parseFloat(p.total_vendido).toFixed(2)}</small>
                </div>
            </div>
        `).join("");
    } catch (e) {
        lista.innerHTML = "<p class='text-danger text-center mt-3'>Error al cargar el reporte.</p>";
    }
}