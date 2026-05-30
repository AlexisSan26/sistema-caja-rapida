let debounceResurtidoTimer = null;

async function cargarEntradas() {
    const fechaFiltro = document.getElementById("input-fecha-entradas").value;
    document.getElementById("lista-entradas").innerHTML = "<p class='text-center text-muted mt-4'>Cargando entradas...</p>";
    try {
        let url = `${API_URL}/historial_entradas`;
        if (fechaFiltro) url += `?fecha=${fechaFiltro}`;
        const res = await fetch(url);
        const entradas = await res.json();
        if (!Array.isArray(entradas) || entradas.length === 0) {
            document.getElementById("lista-entradas").innerHTML = "<p class='text-center text-muted mt-4'>No hay entradas para esta fecha.</p>";
            return;
        }
        document.getElementById("lista-entradas").innerHTML = entradas.map(e => {
            const fecha = (e.fecha && e.hora) ? `${e.fecha} ${e.hora}` : '—';
            return `<div class="card mb-2 shadow-sm">
                <div class="card-body py-2 px-3">
                    <div class="d-flex justify-content-between align-items-start">
                        <div>
                            <div class="fw-bold">${esc(e.nombre_producto || e.producto || '—')}</div>
                            <small class="text-muted">${fecha}${e.notas ? ' · ' + esc(e.notas) : ''}</small>
                        </div>
                        <div class="text-end">
                            <span class="badge bg-success">+${e.cantidad} ${e.unidad_medida || 'pza'}</span>
                        </div>
                    </div>
                </div>
            </div>`;
        }).join("");
    } catch (e) {
        document.getElementById("lista-entradas").innerHTML = "<p class='text-danger text-center mt-4'>Error al cargar entradas.</p>";
    }
}

function limpiarFiltroEntradas() {
    document.getElementById("input-fecha-entradas").value = "";
    cargarEntradas();
}

// ─── Flujo de Resurtido por Lote ─────────────────────────────────────────────

async function cargarProveedoresDatalist() {
    try {
        const res = await fetch(`${API_URL}/proveedores`);
        const provs = await res.json();
        document.getElementById("lista-proveedores").innerHTML = provs.map(p => `<option value="${esc(p)}">`).join("");
    } catch (_) {}
}

function abrirFlujoResurtido(codigoInicial = null) {
    document.getElementById("modal-resurtido").style.display = "block";
    document.getElementById("paso-1").style.display = "block";
    document.getElementById("paso-3").style.display = "none";

    loteResurtido = [];
    renderLoteResurtido();

    document.getElementById("producto-resurtido").value = codigoInicial || "";
    document.getElementById("cantidad-resurtido").value = "1";
    document.getElementById("fecha-cad-resurtido").value = "";

    cargarProveedoresDatalist();

    if (codigoInicial) manejarInputResurtido();

    setTimeout(() => document.getElementById("producto-resurtido").focus(), 200);
}

function cerrarModalResurtido() {
    document.getElementById("modal-resurtido").style.display = "none";
    cerrarEscanerResurtido();
    loteResurtido = [];
    renderLoteResurtido();
}

function volverPaso1() {
    document.getElementById("paso-3").style.display = "none";
    document.getElementById("paso-1").style.display = "block";
}

function renderLoteResurtido() {
    const contenedor = document.getElementById("div-carrito-resurtido");

    if (loteResurtido.length === 0) {
        contenedor.style.display = "none";
        return;
    }

    contenedor.style.display = "block";

    contenedor.innerHTML = `
        <div class="fw-bold mb-2 text-secondary" style="font-size:.85rem;text-transform:uppercase;letter-spacing:.5px;">Lista de productos a ingresar</div>
        <div style="border:1px solid #dee2e6;border-radius:8px;overflow:hidden;margin-bottom:1rem;">
            <table class="table table-sm mb-0" id="tabla-lote-resurtido">
                <thead class="table-light">
                    <tr>
                        <th>Producto</th>
                        <th class="text-center" style="width:60px; font-size:.8rem;">Stock</th>
                        <th class="text-center" style="width:70px; font-size:.8rem;">Entran</th>
                        <th class="text-center" style="width:36px;"></th>
                    </tr>
                </thead>
                <tbody>
                    ${loteResurtido.map((item, idx) => `
                        <tr>
                            <td style="font-size:.9rem;vertical-align:middle;">${esc(item.nombre)}</td>
                            <td class="text-center text-muted fw-bold" style="vertical-align:middle;font-size:.85rem;">
                                ${item.stock_actual}
                            </td>
                            <td class="text-center" style="vertical-align:middle;">
                                <input type="number" class="form-control form-control-sm text-center p-1"
                                    style="width:60px;display:inline-block;"
                                    value="${item.cantidad}" min="1"
                                    onchange="actualizarCantidadLote(${idx}, this.value)">
                            </td>
                            <td class="text-center" style="vertical-align:middle;">
                                <button class="btn btn-sm btn-outline-danger py-0 px-1 lh-1" onclick="quitarDelLoteResurtido(${idx})">✕</button>
                            </td>
                        </tr>
                    `).join("")}
                </tbody>
            </table>
        </div>
    `;
}

function agregarAlLoteResurtido() {
    const nombre = document.getElementById("producto-resurtido").value.trim();
    const cantidad = parseFloat(document.getElementById("cantidad-resurtido").value);
    const fechaCad = document.getElementById("fecha-cad-resurtido").value;

    if (!nombre) { alert("Escribe el nombre del producto o escanea su código."); return; }
    if (isNaN(cantidad) || cantidad <= 0) { alert("La cantidad debe ser mayor a 0."); return; }

    const productoLocal = todosLosProductos.find(p => p.nombre_producto === nombre || p.codigo_barras === nombre);

    if (productoLocal) {
        loteResurtido.push({
            id_producto: productoLocal.id_producto,
            nombre: productoLocal.nombre_producto,
            cantidad: cantidad,
            fecha_caducidad: fechaCad || null,
            stock_actual: productoLocal.stock_actual
        });

        renderLoteResurtido();

        document.getElementById("producto-resurtido").value = "";
        document.getElementById("cantidad-resurtido").value = "1";
        document.getElementById("fecha-cad-resurtido").value = "";
        document.getElementById("producto-resurtido").focus();
    } else {
        alert("⚠️ Producto no encontrado en el inventario. Verifícalo o regístralo como nuevo.");
    }
}

function quitarDelLoteResurtido(index) {
    loteResurtido.splice(index, 1);
    renderLoteResurtido();
}

function actualizarCantidadLote(idx, val) {
    const n = parseFloat(val);
    if (isNaN(n) || n <= 0) {
        quitarDelLoteResurtido(idx);
        return;
    }
    loteResurtido[idx].cantidad = n;
    renderLoteResurtido();
}

async function manejarInputResurtido() {
    const texto = document.getElementById("producto-resurtido").value;
    if (!texto) return;

    const esCodigoBarras = /^\d{4,}$/.test(texto.trim());
    if (esCodigoBarras) {
        clearTimeout(debounceResurtidoTimer);
        debounceResurtidoTimer = setTimeout(() => {
            const val = document.getElementById("producto-resurtido").value.trim();
            if (!/^\d{4,}$/.test(val)) return;

            const local = todosLosProductos.find(p => p.codigo_barras === val);
            if (local) {
                document.getElementById("producto-resurtido").value = local.nombre_producto;
            } else {
                fetch(`${API_URL}/producto_por_codigo/${val}`)
                    .then(r => r.json())
                    .then(data => {
                        if (data.encontrado) {
                            document.getElementById("producto-resurtido").value = data.producto.nombre_producto;
                        } else {
                            if (confirm("Producto no encontrado. ¿Deseas registrarlo en el inventario?")) {
                                document.getElementById("nuevo-codigo").value = val;
                                irAltaNueva();
                            }
                        }
                    }).catch(() => mostrarError("Error al buscar por código."));
            }
        }, 80);
        return;
    }

    clearTimeout(debounceResurtidoTimer);
    debounceResurtidoTimer = setTimeout(() => {
        const textoActual = document.getElementById("producto-resurtido").value;
        if (!textoActual || /^\d{4,}$/.test(textoActual.trim())) return;
        const textoMin = textoActual.toLowerCase();

        const resultados = todosLosProductos.filter(p =>
            p.nombre_producto.toLowerCase().includes(textoMin) ||
            (p.codigo_barras && p.codigo_barras.includes(textoMin))
        ).slice(0, 20);

        const datalist = document.getElementById("lista-productos-resurtido");
        datalist.innerHTML = resultados.map(p => `<option value="${esc(p.nombre_producto)}">`).join("");
    }, 80);
}

async function enviarTicketProveedor() {
    if (loteResurtido.length === 0) {
        alert("No hay productos en la lista para guardar.");
        return;
    }

    try {
        const itemsLote = loteResurtido.map(item => ({
            id_producto: item.id_producto,
            cantidad: item.cantidad,
            fecha_caducidad: item.fecha_caducidad
        }));

        const res = await fetch(`${API_URL}/entrada_mercancia_lote`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                items: itemsLote,
                nota_general: "Ticket de resurtido en lote"
            })
        });

        const data = await res.json();

        if (!res.ok) {
            throw new Error(data.error || "Error al registrar el lote");
        }

        alert("✅ " + data.mensaje);

        loteResurtido = [];
        renderLoteResurtido();
        cerrarModalResurtido();
        cargarInventario();

    } catch (e) {
        mostrarError("Error al registrar el ticket completo.");
    }
}