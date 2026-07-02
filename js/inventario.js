async function cargarInventario() {
    document.getElementById("lista-inventario").innerHTML = "<p class='text-center text-muted mt-4'>Cargando...</p>";
    try {
        const [resProds, resProv] = await Promise.all([
            fetch(`${API_URL}/inventario`),
            fetch(`${API_URL}/proveedores`)
        ]);
        todosLosProductos = await resProds.json();
        const proveedores = await resProv.json();
        renderFiltrosProveedor(proveedores);
        renderInventario(todosLosProductos);
    } catch (e) {
        document.getElementById("lista-inventario").innerHTML = "<p class='text-danger text-center mt-4'>Error al cargar inventario.</p>";
    }
}

function renderFiltrosProveedor(proveedores) {
    const cont = document.getElementById("filtros-proveedor");
    let opciones = `<option value="">Filtrar por proveedor: Todos</option>`;
    proveedores.forEach(p => {
        opciones += `<option value="${esc(p)}">${esc(p)}</option>`;
    });
    cont.innerHTML = `<select class="form-select form-select-lg mb-3" onchange="setProveedor(this.value)">${opciones}</select>`;
}

function setProveedor(p) {
    proveedorFiltro = p;
    filtrarInventario();
}

function filtrarInventario() {
    const q = document.getElementById("buscador-inventario").value.toLowerCase();
    let filtrados = todosLosProductos;

    if (q) {
        filtrados = filtrados.filter(p =>
            p.nombre_producto.toLowerCase().includes(q) ||
            (p.codigo_barras && p.codigo_barras.toLowerCase().includes(q))
        );
    }

    if (proveedorFiltro) {
        filtrados = filtrados.filter(p => p.proveedor === proveedorFiltro);
    }

    renderInventario(filtrados);
}

function renderInventario(productos) {
    const cont = document.getElementById("lista-inventario");
    if (productos.length === 0) { cont.innerHTML = "<p class='text-center text-muted mt-4'>No se encontraron productos.</p>"; return; }
    cont.innerHTML = productos.map(p => {
        const stockColor = p.stock_actual <= p.stock_minimo ? 'text-danger fw-bold' : 'text-success fw-bold';
        const hoy = new Date();
        const cad = p.fecha_caducidad ? new Date(p.fecha_caducidad) : null;
        const diasCad = cad ? Math.ceil((cad - hoy) / (1000*60*60*24)) : null;
        const alertaCad = diasCad !== null && diasCad <= 7 ? `<span class="badge bg-warning text-dark ms-1">Cad: ${diasCad}d</span>` : '';
        return `<div class="card mb-2 shadow-sm" onclick="abrirDetalleProducto(${p.id_producto})" style="cursor:pointer;">
            <div class="card-body py-2 px-3">
                <div class="d-flex justify-content-between align-items-start">
                    <div><div class="fw-bold">${esc(p.nombre_producto)} ${alertaCad}</div><small class="text-muted">${esc(p.proveedor)}</small></div>
                    <div class="text-end"><div class="${stockColor}">Stock: ${p.stock_actual} ${p.unidad_medida || 'pza'}</div><small class="text-muted">$${parseFloat(p.precio_sugerido).toFixed(2)}</small></div>
                </div>
            </div>
        </div>`;
    }).join("");
}

function abrirDetalleProducto(idProducto) {
    const p = todosLosProductos.find(x => x.id_producto === idProducto);
    if (!p) return;
    productoEnEdicion = p;
    document.getElementById("sheet-nombre").textContent = p.nombre_producto;
    document.getElementById("sheet-precio").textContent = `$${parseFloat(p.precio_sugerido).toFixed(2)}`;
    document.getElementById("sheet-costo").textContent = p.precio_costo ? `$${parseFloat(p.precio_costo).toFixed(2)}` : "—";
    document.getElementById("sheet-stock").textContent = p.stock_actual;
    document.getElementById("sheet-unidad").textContent = p.unidad_medida || "pieza";
    document.getElementById("sheet-minimo").textContent = p.stock_minimo;
    document.getElementById("sheet-proveedor").textContent = p.proveedor || "—";
    document.getElementById("sheet-codigo").textContent = p.codigo_barras || "—";
    document.getElementById("sheet-caducidad").textContent = p.fecha_caducidad ? new Date(p.fecha_caducidad).toLocaleDateString('es-MX') : "—";
    document.getElementById("sheet-lectura").style.display = "block";
    document.getElementById("sheet-edicion").style.display = "none";
    document.getElementById("bottom-sheet-overlay").style.display = "block";
    setTimeout(() => document.getElementById("bottom-sheet").classList.add("visible"), 10);
}

function cerrarBottomSheet() {
    document.getElementById("bottom-sheet").classList.remove("visible");
    setTimeout(() => { document.getElementById("bottom-sheet-overlay").style.display = "none"; }, 300);
    productoEnEdicion = null;
}

function activarModoEdicion() {
    if (!productoEnEdicion) return;
    const p = productoEnEdicion;
    document.getElementById("edit-nombre").value = p.nombre_producto;
    document.getElementById("edit-precio").value = p.precio_sugerido;
    document.getElementById("edit-costo").value = p.precio_costo || "";
    document.getElementById("edit-stock").value = p.stock_actual;
    document.getElementById("edit-minimo").value = p.stock_minimo;
    document.getElementById("edit-proveedor").value = p.proveedor || "";
    document.getElementById("edit-codigo").value = p.codigo_barras || "";
    document.getElementById("edit-unidad").value = p.unidad_medida || "pieza";
    document.getElementById("edit-caducidad").value = p.fecha_caducidad ? p.fecha_caducidad.split('T')[0] : "";
    fetch(`${API_URL}/proveedores`).then(r => r.json()).then(provs => {
        document.getElementById("lista-proveedores-edit").innerHTML = provs.map(pv => `<option value="${esc(pv)}">`).join("");
    }).catch(() => {});
    document.getElementById("sheet-lectura").style.display = "none";
    document.getElementById("sheet-edicion").style.display = "block";
}

function cancelarEdicion() {
    document.getElementById("sheet-lectura").style.display = "block";
    document.getElementById("sheet-edicion").style.display = "none";
}

async function guardarEdicion() {
    if (!productoEnEdicion) return;
    const nombre = document.getElementById("edit-nombre").value.trim();
    const precio = parseFloat(document.getElementById("edit-precio").value);
    const stock = parseFloat(document.getElementById("edit-stock").value);
    const minimo = parseFloat(document.getElementById("edit-minimo").value);
    if (!nombre) { alert("El nombre no puede estar vacío."); return; }
    if (isNaN(precio) || precio < 0) { alert("Escribe un precio válido."); return; }
    if (isNaN(stock) || stock < 0) { alert("El stock no puede ser negativo."); return; }
    if (isNaN(minimo) || minimo < 0) { alert("El stock mínimo no puede ser negativo."); return; }
    try {
        const res = await fetch(`${API_URL}/actualizar_producto/${productoEnEdicion.id_producto}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                nombre_producto: nombre, precio_sugerido: precio,
                precio_costo: parseFloat(document.getElementById("edit-costo").value) || null,
                stock_actual: stock, stock_minimo: minimo,
                proveedor: document.getElementById("edit-proveedor").value.trim() || null,
                codigo_barras: document.getElementById("edit-codigo").value.trim() || null,
                fecha_caducidad: document.getElementById("edit-caducidad").value || null,
                unidad_medida: document.getElementById("edit-unidad").value || "pieza"
            })
        });
        const data = await res.json();
        if (!res.ok) { alert("❌ Error: " + (data.detail ? JSON.stringify(data.detail) : data.mensaje)); return; }
        alert("✅ " + data.mensaje);
        cerrarBottomSheet();
        cargarInventario();
    } catch (e) { mostrarError("Error al guardar los cambios."); }
}

async function eliminarProductoActual() {
    if (!productoEnEdicion) return;
    const confirmar = confirm(`¿Estás seguro de que deseas ELIMINAR "${productoEnEdicion.nombre_producto}" del sistema?\n\nEsta acción lo ocultará del inventario y la caja, pero mantendrá el historial de ventas.`);
    if (!confirmar) return;

    try {
        const res = await fetch(`${API_URL}/eliminar_producto/${productoEnEdicion.id_producto}`, { method: "DELETE" });
        if (!res.ok) { alert("❌ Error del servidor al intentar eliminar."); return; }
        const data = await res.json();
        alert("✅ " + data.mensaje);
        cerrarBottomSheet();
        cargarInventario();
        try {
            document.getElementById("producto").value = "";
            document.getElementById("precio").value = "";
        } catch(e) {}
    } catch (e) { mostrarError("Error de conexión al eliminar el producto."); }
}

function abrirMerma() {
    if (!productoEnEdicion) return;
    document.getElementById("merma-producto-nombre").textContent = `Producto: ${productoEnEdicion.nombre_producto} (Stock: ${productoEnEdicion.stock_actual})`;
    document.getElementById("merma-cantidad").value = "";
    document.getElementById("merma-motivo").value = "merma";
    document.getElementById("merma-nota").value = "";
    document.getElementById("modal-merma").style.display = "block";
}

function cerrarMerma() {
    document.getElementById("modal-merma").style.display = "none";
}

async function confirmarMerma() {
    if (!productoEnEdicion) return;
    const cantidad = parseFloat(document.getElementById("merma-cantidad").value);
    const motivo = document.getElementById("merma-motivo").value;
    const nota = document.getElementById("merma-nota").value.trim();
    if (isNaN(cantidad) || cantidad <= 0) { alert("Escribe una cantidad válida mayor a 0."); return; }
    if (cantidad > productoEnEdicion.stock_actual) {
        if (!confirm(`⚠️ La cantidad (${cantidad}) supera el stock actual (${productoEnEdicion.stock_actual}). ¿Continuar de todas formas?`)) return;
    }
    try {
        const res = await fetch(`${API_URL}/registrar_merma`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                id_producto: productoEnEdicion.id_producto,
                cantidad: cantidad,
                motivo: motivo,
                nota: nota || null
            })
        });
        const data = await res.json();
        if (!res.ok) { alert("❌ " + (data.detail || data.mensaje || "Error al registrar merma.")); return; }
        alert("✅ " + (data.mensaje || "Merma registrada correctamente."));
        cerrarMerma();
        cerrarBottomSheet();
        cargarInventario();
    } catch (e) { mostrarError("Error al registrar la merma."); }
}

function exportarInventarioCSV() {
    if (!todosLosProductos || todosLosProductos.length === 0) {
        alert("No hay productos en el inventario para exportar.");
        return;
    }
    const cabecera = ["ID", "Nombre", "Precio", "Stock actual", "Stock mínimo", "Unidad", "Proveedor", "Código de barras", "Caducidad"];
    const filas = todosLosProductos.map(p => [
        p.id_producto || "",
        `"${(p.nombre_producto || "").replace(/"/g, '""')}"`,
        p.precio_sugerido || "0",
        p.stock_actual || "0",
        p.stock_minimo || "0",
        p.unidad_medida || "pieza",
        `"${(p.proveedor || "").replace(/"/g, '""')}"`,
        p.codigo_barras || "",
        p.fecha_caducidad || ""
    ]);
    const csv = "\uFEFF" + [cabecera.join(","), ...filas.map(f => f.join(","))].join("\r\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    const hoy = new Date().toISOString().split("T")[0];
    link.download = `inventario_${hoy}.csv`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(url);
}

// ─── Alta de Producto Nuevo (desde flujo de resurtido) ────────────────────────

function irAltaNueva() {
    const busqueda = document.getElementById("producto-resurtido").value.trim();
    document.getElementById("nuevo-nombre").value = isNaN(busqueda) ? busqueda : "";
    document.getElementById("nuevo-codigo").value = (!isNaN(busqueda) && busqueda) ? busqueda : "";
    document.getElementById("nuevo-precio").value = "";
    document.getElementById("nuevo-stock").value = "0";
    document.getElementById("nuevo-minimo").value = "5";
    document.getElementById("nuevo-proveedor").value = "";
    document.getElementById("nuevo-caducidad").value = "";
    document.getElementById("nuevo-unidad").value = "pieza";

    document.getElementById("paso-1").style.display = "none";
    document.getElementById("paso-3").style.display = "block";
}

async function guardarProductoNuevo() {
    const nombre = document.getElementById("nuevo-nombre").value.trim();
    const precio = parseFloat(document.getElementById("nuevo-precio").value);
    if (!nombre) { alert("El nombre del producto es obligatorio."); return; }
    if (isNaN(precio) || precio < 0) { alert("Escribe un precio válido."); return; }
    try {
        const res = await fetch(`${API_URL}/registrar_producto`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                codigo_barras: document.getElementById("nuevo-codigo").value.trim() || null,
                nombre_producto: nombre, precio_sugerido: precio,
                precio_costo: parseFloat(document.getElementById("nuevo-costo").value) || null,
                stock_actual: parseFloat(document.getElementById("nuevo-stock").value) || 0,
                stock_minimo: parseFloat(document.getElementById("nuevo-minimo").value) || 5,
                proveedor: document.getElementById("nuevo-proveedor").value.trim() || null,
                fecha_caducidad: document.getElementById("nuevo-caducidad").value || null,
                unidad_medida: document.getElementById("nuevo-unidad").value || "pieza"
            })
        });
        const data = await res.json();
        alert("✅ " + (data.mensaje || "Producto registrado"));

        document.getElementById("producto-resurtido").value = nombre;
        volverPaso1();
        cargarInventario();
    } catch (e) { mostrarError("Error al guardar el producto."); }
}
