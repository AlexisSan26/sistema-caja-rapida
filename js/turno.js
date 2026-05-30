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
        cuerpo.innerHTML = movimientos.map(m => {
            let badge = '';
            if (m.tipo_movimiento === 'VENTA') badge = '<span class="badge bg-success">Venta</span>';
            else if (m.tipo_movimiento === 'RETIRO') badge = '<span class="badge bg-danger">Retiro</span>';
            else if (m.tipo_movimiento === 'COBRO_FIADO') badge = '<span class="badge bg-warning text-dark">Abono</span>';
            else if (m.tipo_movimiento === 'FONDO_CAJA') badge = '<span class="badge bg-primary">Fondo</span>';

            return `<tr data-id="${m.id_movimiento}">
                <td class="text-center" style="vertical-align: middle;">
                    <div style="font-size:.85rem;">${m.hora || '--:--'}</div>
                    <div class="mt-1" style="font-size: .75rem;">${badge}</div>
                </td>
                <td class="text-center">${m.cantidad}</td>
                <td style="font-size:.9rem; vertical-align: middle;">${esc(m.producto)}</td>
                <td class="text-center">$${m.total_movimiento.toFixed(2)}</td>
                <td class="text-center">
                    <button class="btn btn-sm btn-outline-danger py-0 px-2" onclick="borrarMovimiento(${m.id_movimiento})">❌</button>
                </td>
            </tr>`;
        }).join("");
    } catch (e) { mostrarError(); }
}