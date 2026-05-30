async function cargarClientes() {
    document.getElementById("lista-clientes").innerHTML = "<p class='text-center text-muted mt-4'>Cargando...</p>";
    try {
        const res = await fetch(`${API_URL}/clientes`);
        const clientes = await res.json();
        if (clientes.length === 0) {
            document.getElementById("lista-clientes").innerHTML = "<p class='text-center text-muted mt-4'>No hay clientes registrados.</p>";
            return;
        }
        document.getElementById("lista-clientes").innerHTML = clientes.map(c => {
            const saldo = parseFloat(c.saldo_actual);
            const colorSaldo = saldo <= 0 ? 'saldo-cero' : 'saldo-deuda';
            const textoSaldo = saldo <= 0 ? 'Al corriente ✅' : `Debe $${saldo.toFixed(2)}`;
            return `<div class="card mb-2 shadow-sm tarjeta-cliente">
                <div class="card-body py-2 px-3 d-flex justify-content-between align-items-center">
                    <div onclick="abrirCuentaCliente(${c.id_cliente})" style="flex:1;cursor:pointer;">
                        <div class="fw-bold">${esc(c.nombre)}</div>
                        <small class="text-muted">${esc(c.telefono || '')}</small>
                    </div>
                    <div class="${colorSaldo} me-2">${textoSaldo}</div>
                    <button class="btn btn-sm btn-outline-danger py-0 px-2" onclick="eliminarCliente(${c.id_cliente}, '${esc(c.nombre)}')">🗑️</button>
                </div>
            </div>`;
        }).join("");
    } catch (e) {
        document.getElementById("lista-clientes").innerHTML = "<p class='text-danger text-center mt-4'>Error al cargar clientes.</p>";
    }
}

async function abrirCuentaCliente(idCliente) {
    try {
        const res = await fetch(`${API_URL}/cuenta_fiado/${idCliente}`);
        const datos = await res.json();
        clienteFiadoActual = { id_cliente: idCliente, id_cuenta: datos.id_cuenta };

        document.getElementById("bs-fiado-nombre").textContent = datos.cliente.nombre;
        document.getElementById("bs-fiado-tel").textContent = datos.cliente.telefono || "";
        const saldo = parseFloat(datos.saldo);
        document.getElementById("bs-fiado-saldo").textContent = `$${saldo.toFixed(2)}`;
        document.getElementById("bs-fiado-saldo").className = saldo <= 0 ? 'h4 mb-0 saldo-cero' : 'h4 mb-0 saldo-deuda';

        if (datos.detalle.length === 0) {
            document.getElementById("bs-fiado-detalle").innerHTML = "<p class='text-muted text-center py-2'>Sin productos fiados.</p>";
        } else {
            document.getElementById("bs-fiado-detalle").innerHTML = `
                <table class="table table-sm mb-0">
                    <thead class="table-light"><tr><th>Fecha</th><th>Producto</th><th class="text-end">Total</th></tr></thead>
                    <tbody>${datos.detalle.map(d =>
                        `<tr><td>${d.fecha}</td><td>${esc(d.producto)} x${d.cantidad}</td><td class="text-end">$${parseFloat(d.subtotal).toFixed(2)}</td></tr>`
                    ).join("")}</tbody>
                </table>`;
        }

        if (datos.abonos.length === 0) {
            document.getElementById("bs-fiado-abonos").innerHTML = "<p class='text-muted text-center py-2'>Sin abonos registrados.</p>";
        } else {
            document.getElementById("bs-fiado-abonos").innerHTML = `
                <table class="table table-sm mb-0">
                    <thead class="table-light"><tr><th>Fecha</th><th>Nota</th><th class="text-end">Monto</th></tr></thead>
                    <tbody>${datos.abonos.map(a =>
                        `<tr><td>${a.fecha}</td><td>${esc(a.nota)}</td><td class="text-end text-success">$${parseFloat(a.monto).toFixed(2)}</td></tr>`
                    ).join("")}</tbody>
                </table>`;
        }

        document.getElementById("monto-abono").value = "";
        document.getElementById("bs-fiado-overlay").style.display = "block";
        setTimeout(() => document.getElementById("bs-fiado").classList.add("visible"), 10);
    } catch (e) { mostrarError("Error al cargar la cuenta."); }
}

function cerrarBsFiado() {
    document.getElementById("bs-fiado").classList.remove("visible");
    setTimeout(() => { document.getElementById("bs-fiado-overlay").style.display = "none"; }, 300);
    clienteFiadoActual = null;
}

async function confirmarAbono() {
    if (!clienteFiadoActual) return;
    if (!idTurnoActual) { alert("Debes tener un turno abierto para registrar un abono."); return; }
    const monto = parseFloat(document.getElementById("monto-abono").value);
    if (isNaN(monto) || monto <= 0) { alert("Ingresa un monto válido."); return; }
    const idCuenta = clienteFiadoActual.id_cuenta;
    cerrarBsFiado();
    try {
        const res = await fetch(`${API_URL}/registrar_abono`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id_cuenta: idCuenta, id_turno: idTurnoActual, monto: monto })
        });
        if (!res.ok) {
            let errorMsg = "Error del servidor.";
            try {
                const errorData = await res.json();
                errorMsg = errorData.detail ? JSON.stringify(errorData.detail) : errorData.mensaje;
            } catch(e) {
                errorMsg = "Error interno (Posible falla en MySQL). Revisa los logs de Render.";
            }
            alert("❌ " + errorMsg);
            cargarClientes();
            return;
        }
        const data = await res.json();
        cargarClientes();
        actualizarLista();
        mostrarError(`✅ Abono de $${monto.toFixed(2)} registrado`);
    } catch (e) { mostrarError("Error al registrar el abono."); cargarClientes(); }
}

async function eliminarCliente(idCliente, nombre) {
    if (!confirm(`¿Eliminar a "${nombre}"?\n\nSolo se puede eliminar si no tiene saldo pendiente.`)) return;
    try {
        const res = await fetch(`${API_URL}/clientes/${idCliente}`, { method: "DELETE" });
        const data = await res.json();
        if (data.error) { alert("❌ " + data.error); return; }
        cargarClientes();
    } catch (e) { mostrarError("Error al eliminar cliente."); }
}

function abrirModalNuevoCliente() {
    document.getElementById("modal-nuevo-cliente").style.display = "block";
    document.getElementById("nuevo-cliente-nombre").value = "";
    document.getElementById("nuevo-cliente-tel").value = "";
}

function cerrarModalNuevoCliente() {
    document.getElementById("modal-nuevo-cliente").style.display = "none";
}

async function guardarNuevoCliente() {
    const nombre = document.getElementById("nuevo-cliente-nombre").value.trim();
    if (!nombre) { alert("El nombre es obligatorio."); return; }
    try {
        const res = await fetch(`${API_URL}/clientes`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ nombre, telefono: document.getElementById("nuevo-cliente-tel").value.trim() || null })
        });
        const data = await res.json();
        alert("✅ " + data.mensaje);
        cerrarModalNuevoCliente();
        cargarClientes();
    } catch (e) { mostrarError("Error al guardar el cliente."); }
}