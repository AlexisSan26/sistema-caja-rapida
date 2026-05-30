let cacheTurnos = null;
let cacheResumenes = {};

async function cargarHistorial() {
    document.getElementById("lista-historial").innerHTML = "<p class='text-center text-muted mt-3'>Cargando...</p>";
    document.getElementById("detalle-historial").innerHTML = "";
    document.getElementById("input-fecha-manual").value = "";
    try {
        const res = await fetch(`${API_URL}/historial_turnos`);
        cacheTurnos = await res.json();
        renderListaHistorial(cacheTurnos.slice(0, 10));
    } catch (e) {
        if (cacheTurnos) { renderListaHistorial(cacheTurnos.slice(0, 10)); return; }
        document.getElementById("lista-historial").innerHTML = "<p class='text-danger mt-3'>Error al cargar historial.</p>";
    }
}

function filtrarHistorialPorFecha() {
    if (!cacheTurnos) return;
    const fecha = document.getElementById("input-fecha-manual").value;
    if (!fecha) { renderListaHistorial(cacheTurnos); return; }
    const filtrados = cacheTurnos.filter(t => {
        if (!t.fecha_apertura) return false;
        return t.fecha_apertura.toString().startsWith(fecha);
    });
    renderListaHistorial(filtrados);
    document.getElementById("detalle-historial").innerHTML = "";
}

function renderListaHistorial(turnos) {
    const lista = document.getElementById("lista-historial");
    if (!turnos || turnos.length === 0) {
        lista.innerHTML = "<p class='text-center text-muted mt-3'>No hay cortes para esta fecha.</p>";
        return;
    }
    lista.innerHTML = turnos.map(t => {
        const fmt = (f, ops) => f ? new Date(f.replace(' ','T')).toLocaleDateString('es-MX', ops) : '—';
        const fmtHora = f => f ? new Date(f.replace(' ','T')).toLocaleTimeString('es-MX', { hour:'2-digit', minute:'2-digit' }) : '—';
        const diaOp   = fmt(t.fecha_apertura, { weekday:'long', day:'numeric', month:'long' });
        const diaAp   = fmt(t.fecha_apertura, { day:'2-digit', month:'short' });
        const diaCI   = fmt(t.fecha_cierre,   { day:'2-digit', month:'short' });
        const horaAp  = fmtHora(t.fecha_apertura);
        const horaCI  = fmtHora(t.fecha_cierre);
        return `<button class="list-group-item list-group-item-action" id="turno-btn-${t.id_turno}" onclick="seleccionarTurno(${t.id_turno})">
            <div class="fw-semibold mb-1">${diaOp}</div>
            <div class="d-flex justify-content-between" style="font-size:.82rem; color:#555;">
                <span>🟢 Ap: ${diaAp} ${horaAp}</span>
                <span>🔴 Ci: ${diaCI} ${horaCI}</span>
            </div>
        </button>`;
    }).join("");
}

function seleccionarTurno(idTurno) {
    if (!cacheTurnos) return;
    const turno = cacheTurnos.find(t => t.id_turno === idTurno);
    if (!turno) return;
    const fmt = (f, ops) => f ? new Date(f.replace(' ','T')).toLocaleDateString('es-MX', ops) : '—';
    const fmtHora = f => f ? new Date(f.replace(' ','T')).toLocaleTimeString('es-MX', { hour:'2-digit', minute:'2-digit' }) : '—';
    const diaOp  = fmt(turno.fecha_apertura, { weekday:'long', day:'numeric', month:'long' });
    const diaAp  = fmt(turno.fecha_apertura, { day:'2-digit', month:'short' });
    const diaCI  = fmt(turno.fecha_cierre,   { day:'2-digit', month:'short' });
    const horaAp = fmtHora(turno.fecha_apertura);
    const horaCI = fmtHora(turno.fecha_cierre);
    document.getElementById("lista-historial").innerHTML = `
        <button class="list-group-item list-group-item-action" style="border-left:4px solid #198754;" onclick="mostrarTodosLosTurnos()">
            <div class="fw-semibold mb-1">${diaOp}</div>
            <div class="d-flex justify-content-between" style="font-size:.82rem; color:#555;">
                <span>🟢 Ap: ${diaAp} ${horaAp}</span>
                <span>🔴 Ci: ${diaCI} ${horaCI}</span>
            </div>
        </button>
        <div class="text-center mt-1">
            <button class="btn btn-sm btn-link text-secondary p-0" onclick="mostrarTodosLosTurnos()">← Ver todos</button>
        </div>`;
    verDetalleHistorial(idTurno);
}

function mostrarTodosLosTurnos() {
    document.getElementById("detalle-historial").innerHTML = "";
    renderListaHistorial(cacheTurnos ? cacheTurnos.slice(0, 10) : []);
}

async function verDetalleHistorial(idTurno) {
    document.getElementById("detalle-historial").innerHTML = "<p class='text-center mt-3'>Cargando...</p>";
    try {
        const [resResumen, resMov] = await Promise.all([
            cacheResumenes[idTurno]
                ? Promise.resolve({ json: () => cacheResumenes[idTurno], ok: true, _cached: true })
                : fetch(`${API_URL}/resumen_turno/${idTurno}`),
            fetch(`${API_URL}/movimientos_turno/${idTurno}`)
        ]);
        const datos = resResumen._cached ? cacheResumenes[idTurno] : await resResumen.json();
        if (!resResumen._cached) cacheResumenes[idTurno] = datos;
        const movimientos = await resMov.json();

        const tablaHTML = `
            <div class="mt-3">
                <div class="fw-bold text-secondary mb-2" style="font-size:.8rem;text-transform:uppercase;letter-spacing:.5px;">Movimientos del turno</div>
                <div style="border:1px solid #dee2e6;border-radius:8px;overflow:hidden;">
                    <table class="table table-sm mb-0">
                        <thead class="table-light">
                            <tr>
                                <th style="width:50px;">Hora</th>
                                <th>Producto</th>
                                <th class="text-center" style="width:45px;">Cant</th>
                                <th class="text-center" style="width:75px;">Total</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${movimientos.map(m => {
                                let badge = '';
                                if (m.tipo_movimiento === 'VENTA') badge = '<span class="badge bg-success me-1">Venta</span>';
                                else if (m.tipo_movimiento === 'RETIRO') badge = '<span class="badge bg-danger me-1">Retiro</span>';
                                else if (m.tipo_movimiento === 'COBRO_FIADO') badge = '<span class="badge bg-warning text-dark me-1">Abono</span>';
                                else if (m.tipo_movimiento === 'FONDO_CAJA') badge = '<span class="badge bg-primary me-1">Fondo</span>';

                                return `<tr>
                                    <td style="font-size:.8rem;">${m.hora || '--'}</td>
                                    <td style="font-size:.85rem;">${badge}${m.producto || '-'}</td>
                                    <td class="text-center">${m.cantidad}</td>
                                    <td class="text-center">$${parseFloat(m.total_movimiento).toFixed(2)}</td>
                                </tr>`;
                            }).join('')}
                        </tbody>
                    </table>
                </div>
            </div>`;

        document.getElementById("detalle-historial").innerHTML = construirTicketHTML(datos, idTurno) + tablaHTML;
    } catch (e) {
        document.getElementById("detalle-historial").innerHTML = "<p class='text-danger'>Error al cargar el resumen.</p>";
    }
}

function aplicarFechaCalendario(fecha) {
    if (!cacheTurnos) return;
    if (!fecha) { renderListaHistorial(cacheTurnos.slice(0, 10)); return; }
    const filtrados = cacheTurnos.filter(t => {
        if (!t.fecha_apertura) return false;
        return t.fecha_apertura.toString().startsWith(fecha);
    });
    renderListaHistorial(filtrados);
    document.getElementById("detalle-historial").innerHTML = "";
}