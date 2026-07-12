let gruposMovimientosActual = [];
let grupoMenuActual = null;

async function verificarEstadoInicial() {
    try {
        const res = await fetch(`${API_URL}/turno_actual`);
        const datos = await res.json();
        if (datos.estado === "ABIERTO") {
            idTurnoActual = datos.id_turno;
            configurarInterfazAbierta();
        } else {
            document.getElementById("panel-apertura").style.display = "block";
            document.getElementById("btn-abrir").style.display = "inline-block";
            document.getElementById("texto-turno").innerText = "No hay turno abierto";
            document.getElementById("texto-turno").className = "text-muted";
        }
    } catch (e) {
        mostrarError("⚠️ No se pudo conectar al servidor.");
        document.getElementById("btn-abrir").style.display = "inline-block";
    }
}

function configurarInterfazAbierta() {
    document.getElementById("panel-apertura").style.display = "none";
    document.getElementById("panel-ventas").style.display = "block";
    document.getElementById("panel-lista").style.display = "block";
    document.getElementById("panel-corte").style.display = "block";
    document.getElementById("btn-abrir").style.display = "none";
    document.getElementById("resultado-corte").innerHTML = "";
    document.getElementById("tipo").value = "VENTA";
    document.getElementById("div-btn-agregar").style.display = "block";
    carritoItems = [];
    try {
        const borrador = localStorage.getItem('carrito_borrador');
        if (borrador) {
            const items = JSON.parse(borrador);
            if (Array.isArray(items) && items.length > 0) {
                const recuperar = confirm(`📋 Hay un borrador con ${items.length} producto(s) sin guardar. ¿Deseas recuperarlo?`);
                if (recuperar) carritoItems = items;
                else localStorage.removeItem('carrito_borrador');
            }
        }
    } catch(e) { localStorage.removeItem('carrito_borrador'); }
    renderCarrito();
    actualizarLista();
    cargarProductosEnMemoria();
    if (intervaloActualizacion) clearInterval(intervaloActualizacion);
    intervaloActualizacion = setInterval(sincronizarTodo, 8000);
    setTimeout(() => document.getElementById("producto").focus(), 200);
}

function abrirMenuMovimiento(clave) {
    const grupo = gruposMovimientosActual.find(g => g.clave === clave);
    if (!grupo) return;
    grupoMenuActual = grupo;
    document.getElementById("bs-mov-titulo").innerText =
        `${badgeTipo(grupo.tipo).replace(/<[^>]+>/g, '')} · ${grupo.hora || ''}`;
    document.getElementById("bs-mov-btn-reimprimir").style.display = grupo.tipo === 'VENTA' ? 'block' : 'none';
    document.getElementById("bs-mov-overlay").style.display = "block";
    setTimeout(() => document.getElementById("bs-mov").style.transform = "translateY(0)", 10);
}

function cerrarMenuMovimiento() {
    document.getElementById("bs-mov").style.transform = "translateY(100%)";
    setTimeout(() => { document.getElementById("bs-mov-overlay").style.display = "none"; }, 300);
    grupoMenuActual = null;
}

function reimprimirDesdeMenu() {
    if (!grupoMenuActual) return;
    const total = grupoMenuActual.items.reduce((acc, m) => acc + m.total_movimiento, 0);
    reimprimirTicket(grupoMenuActual.items, total, grupoMenuActual.metodo_pago || "efectivo");
    cerrarMenuMovimiento();
}

async function borrarDesdeMenu() {
    if (!grupoMenuActual) return;
    const grupo = grupoMenuActual;
    cerrarMenuMovimiento();

    const esLote = grupo.items.length > 1 && grupo.id_lote;
    if (!confirm(esLote
        ? `⚠️ ¿Cancelar este ticket completo (${grupo.items.length} productos)?\nEsta acción no se puede deshacer.`
        : "⚠️ ¿Estás seguro de cancelar este registro?\nEsta acción no se puede deshacer.")) return;

    const tarjeta = document.querySelector(`.mov-card[data-clave="${grupo.clave}"]`);
    if (tarjeta) tarjeta.remove();
    grupo.items.forEach(m => idsEnTabla.delete(m.id_movimiento));

    try {
        const url = esLote
            ? `${API_URL}/borrar_lote/${grupo.id_lote}`
            : `${API_URL}/borrar_movimiento/${grupo.items[0].id_movimiento}`;
        const res = await fetch(url, { method: "DELETE" });
        if (!res.ok) { mostrarError("Error al cancelar."); actualizarLista(); }
    } catch (e) {
        mostrarError("Error de conexión al cancelar.");
        actualizarLista();
    }
}

async function cargarProductosEnMemoria() {
    try {
        const res = await fetch(`${API_URL}/inventario`);
        todosLosProductos = await res.json();
    } catch (e) { console.warn("No se pudo cargar productos en memoria"); }
}

async function sincronizarTodo() {
    if (!idTurnoActual) return;
    try {
        const res = await fetch(`${API_URL}/turno_actual`);
        const datos = await res.json();
        if (datos.estado !== "ABIERTO") {
            try {
                const resResumen = await fetch(`${API_URL}/resumen_turno/${idTurnoActual}`);
                const datosResumen = await resResumen.json();
                mostrarTicket(datosResumen);
            } catch (_) {}
            alert("El turno ha sido cerrado desde otro dispositivo.");
            resetearInterfazCerrada();
            return;
        }
        actualizarLista();
    } catch (e) { mostrarError(); }
}

function resetearInterfazCerrada() {
    if (intervaloActualizacion) clearInterval(intervaloActualizacion);
    intervaloActualizacion = null;
    idTurnoActual = null;
    idsEnTabla.clear();
    document.getElementById("panel-apertura").style.display = "block";
    document.getElementById("btn-abrir").style.display = "inline-block";
    document.getElementById("btn-abrir").innerText = "Abrir Caja (Nuevo Turno)";
    document.getElementById("panel-ventas").style.display = "none";
    document.getElementById("panel-lista").style.display = "none";
    document.getElementById("panel-corte").style.display = "none";
    document.getElementById("texto-turno").innerText = "No hay turno abierto";
    document.getElementById("texto-turno").className = "text-muted";
}

function badgeTipo(tipo) {
    if (tipo === 'VENTA') return '<span class="badge bg-success">Venta</span>';
    if (tipo === 'RETIRO') return '<span class="badge bg-danger">Retiro</span>';
    if (tipo === 'COBRO_FIADO') return '<span class="badge bg-warning text-dark">Abono</span>';
    if (tipo === 'FONDO_CAJA') return '<span class="badge bg-primary">Fondo</span>';
    return '';
}

function badgeMetodoPago(metodo) {
    const iconos = { efectivo: '💵 Efectivo', tarjeta: '💳 Tarjeta', transferencia: '📲 Transferencia' };
    return `<span class="text-muted">${iconos[metodo] || ''}</span>`;
}

function claseTipo(tipo) {
    if (tipo === 'VENTA') return ' mov-venta';
    if (tipo === 'RETIRO') return ' mov-retiro';
    if (tipo === 'COBRO_FIADO') return ' mov-abono';
    if (tipo === 'FONDO_CAJA') return ' mov-fondo';
    return '';
}

function descripcionMovimiento(g) {
    if (g.tipo === 'FONDO_CAJA') return 'Fondo en caja';
    return esc(g.items[0].producto || '');
}

function agruparMovimientos(movimientos) {
    const grupos = new Map();
    for (const m of movimientos) {
        const clave = m.id_lote || `mov_${m.id_movimiento}`;
        if (!grupos.has(clave)) grupos.set(clave, { clave, id_lote: m.id_lote || null, tipo: m.tipo_movimiento, hora: m.hora, metodo_pago: m.metodo_pago, items: [] });
        grupos.get(clave).items.push(m);
    }
    return [...grupos.values()];
}

async function actualizarLista() {
    if (!idTurnoActual) return;
    try {
        const res = await fetch(`${API_URL}/movimientos_turno/${idTurnoActual}`);
        const movimientos = await res.json();
        const cuerpo = document.getElementById("tabla-cuerpo");
        const nuevosIds = new Set(movimientos.map(m => m.id_movimiento));
        const cambio = nuevosIds.size !== idsEnTabla.size || [...nuevosIds].some(id => !idsEnTabla.has(id));
        if (!cambio) return;
        idsEnTabla = nuevosIds;
        gruposMovimientosActual = agruparMovimientos(movimientos);

        cuerpo.innerHTML = gruposMovimientosActual.map(g => {
            const total = g.items.reduce((acc, m) => acc + m.total_movimiento, 0);
            const totalUnidades = g.items.reduce((acc, m) => acc + parseFloat(m.cantidad), 0);
            const esVenta = g.tipo === 'VENTA';
            const filas = esVenta ? g.items.map(m => `
                <div class="mov-item">
                    <span>${m.cantidad} x ${esc(m.producto)}</span>
                    <span>$${m.total_movimiento.toFixed(2)}</span>
                </div>`).join("") : `<div class="mov-item"><span>${descripcionMovimiento(g)}</span></div>`;
            const infoDerecha = esVenta ? badgeMetodoPago(g.metodo_pago) : '';
            const claseExtra = claseTipo(g.tipo);
            const pie = esVenta
                ? `<span>${totalUnidades} unidad${totalUnidades == 1 ? '' : 'es'}</span><span>Total: $${total.toFixed(2)}</span>`
                : `<span></span><span>Total: $${total.toFixed(2)}</span>`;

            if (!esVenta) {
                const infoDerechaMov = g.tipo === 'COBRO_FIADO' ? badgeMetodoPago(g.metodo_pago) : '';
                return `<div class="mov-card${claseExtra}" data-clave="${g.clave}" onclick="abrirMenuMovimiento('${g.clave}')">
                    <div class="mov-header">
                        <span>${badgeTipo(g.tipo)} &nbsp; ${g.hora || '--:--'}</span>
                        <span>${infoDerechaMov}</span>
                    </div>
                    <div class="mov-footer">
                        <span class="mov-desc-normal">${descripcionMovimiento(g)}</span><span>Total: $${total.toFixed(2)}</span>
                    </div>
                </div>`;
            }

            return `<div class="mov-card${claseExtra}" data-clave="${g.clave}" onclick="abrirMenuMovimiento('${g.clave}')">
                <div class="mov-header">
                    <span>${badgeTipo(g.tipo)} &nbsp; ${g.hora || '--:--'}</span>
                    <span>${infoDerecha}</span>
                </div>
                ${filas}
                <div class="mov-footer">${pie}</div>
            </div>`;
        }).join("");
    } catch (e) { mostrarError(); }
}