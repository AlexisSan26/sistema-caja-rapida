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
            const cant = Number(e.cantidad);
            const esSalida = cant < 0;  // #102: las mermas se guardan en negativo
            const unidad = (!e.unidad_medida || e.unidad_medida === 'pieza') ? 'pza' : e.unidad_medida;
            return `<div class="card mb-2 shadow-sm">
                <div class="card-body py-2 px-3">
                    <div class="d-flex justify-content-between align-items-start">
                        <div>
                            <div class="fw-bold">${esc(e.nombre_producto || e.producto || '—')}</div>
                            <small class="text-muted">${fecha}${e.notas ? ' · ' + esc(e.notas) : ''}</small>
                        </div>
                        <div class="text-end">
                            <span class="badge ${esSalida ? 'bg-danger' : 'bg-success'}">${esSalida ? '' : '+'}${cant} ${esc(unidad)}</span>
                            ${e.precio_costo != null ? `<div class="text-muted" style="font-size:.75rem;">Costo: $${parseFloat(e.precio_costo).toFixed(2)}</div>` : ''}
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

// #51: el lote de resurtido sobrevive a recargas; borrador y clave de #66 separados por tienda y usuario
let resurtidoIntentado = false;  // se envió y no sabemos si el servidor lo guardó

function duenoResurtido() {
    try {
        const parte = localStorage.getItem('saas_token').split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
        const datos = JSON.parse(atob(parte));
        return `${datos.id_tienda}_${datos.id_usuario}`;
    } catch (e) { return null; }
}

function opEntrada() { return "entrada_" + duenoResurtido(); }

function guardarBorradorResurtido() {
    const dueno = duenoResurtido();
    if (!dueno) return;
    try {
        if (loteResurtido.length === 0) localStorage.removeItem('resurtido_borrador_' + dueno);
        else localStorage.setItem('resurtido_borrador_' + dueno, JSON.stringify({ items: loteResurtido, intentado: resurtidoIntentado }));
    } catch (e) {}
}

function leerBorradorResurtido() {
    const dueno = duenoResurtido();
    if (!dueno) return null;
    try {
        const borrador = JSON.parse(localStorage.getItem('resurtido_borrador_' + dueno));
        return borrador && Array.isArray(borrador.items) && borrador.items.length > 0 ? borrador : null;
    } catch (e) { return null; }
}

function cancelarResurtido() {
    if (loteResurtido.length > 0 && !confirm(`¿Descartar la lista con ${loteResurtido.length} producto(s)?`)) return;
    loteResurtido = [];
    cerrarModalResurtido();
}

// #51: cerrar sin descartar; no toca la lista, su borrador ni la clave de #66
function salirResurtido() {
    cerrarEscanerResurtido();
    document.getElementById("modal-resurtido").style.display = "none";
}

function abrirFlujoResurtido(codigoInicial = null) {
    document.getElementById("modal-resurtido").style.display = "block";
    document.getElementById("paso-1").style.display = "block";
    document.getElementById("paso-3").style.display = "none";

    const borrador = leerBorradorResurtido();
    resurtidoIntentado = !!(borrador && borrador.intentado);
    // #51: se recupera la lista guardada, mostrando el stock actual si ya está cargado
    loteResurtido = (borrador ? borrador.items : []).map(item => {
        const p = todosLosProductos.find(x => x.id_producto === item.id_producto);
        return p ? { ...item, stock_actual: p.stock_actual, controla_stock: p.controla_stock } : item;
    });
    if (!borrador) liberarClaveIdempotente(opEntrada());  // #66: lote nuevo = clave nueva (el recuperado conserva la suya)
    renderLoteResurtido();
    if (resurtidoIntentado) alert("⚠️ Esta lista ya se intentó guardar y no se confirmó. Antes de cambiarla, revisa el Historial de Entradas: si ya aparece, toca Cancelar para descartarla.");

    document.getElementById("producto-resurtido").value = codigoInicial || "";
    document.getElementById("cantidad-resurtido").value = "1";
    document.getElementById("fecha-cad-resurtido").value = "";
    document.getElementById("costo-resurtido").value = "";

    cargarProveedoresDatalist();

    if (codigoInicial) manejarInputResurtido();

    setTimeout(() => document.getElementById("producto-resurtido").focus(), 200);
}

function cerrarModalResurtido() {
    document.getElementById("modal-resurtido").style.display = "none";
    cerrarEscanerResurtido();
    loteResurtido = [];
    resurtidoIntentado = false;
    liberarClaveIdempotente(opEntrada());  // #66: lote descartado o terminado
    renderLoteResurtido();
}

function volverPaso1() {
    document.getElementById("paso-3").style.display = "none";
    document.getElementById("paso-1").style.display = "block";
}

function renderLoteResurtido() {
    guardarBorradorResurtido();  // #51
    const contenedor = document.getElementById("div-carrito-resurtido");

    if (loteResurtido.length === 0) {
        contenedor.style.display = "none";
        return;
    }

    contenedor.style.display = "block";

    contenedor.innerHTML = `
        <div class="fw-bold mb-2 text-secondary" style="font-size:.85rem;text-transform:uppercase;letter-spacing:.5px;">Lista de productos a ingresar</div>
        <div id="lista-lote-resurtido">
            ${loteResurtido.map((item, idx) => `
                <div class="border rounded p-2 mb-2" style="background:#fff;">
                    <div class="d-flex justify-content-between align-items-center mb-2">
                        <span style="font-size:.9rem;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:65%;" title="${esc(item.nombre)}">${esc(item.nombre)}</span>
                        <span class="text-muted" style="font-size:.8rem;">${item.controla_stock == 0 ? 'Sin control de stock' : `Stock: <b>${item.stock_actual}</b>`}</span>
                        <button class="btn btn-sm btn-outline-danger py-0 px-2 lh-1" onclick="quitarDelLoteResurtido(${idx})">✕</button>
                    </div>
                    <div class="d-flex gap-2">
                        <div class="flex-fill">
                            <div class="text-muted" style="font-size:.7rem;">Entran</div>
                            <input type="number" class="form-control form-control-sm text-center p-1"
                                value="${item.cantidad}" min="1"
                                onchange="actualizarCantidadLote(${idx}, this.value)">
                        </div>
                        <div class="flex-fill">
                            <div class="text-muted" style="font-size:.7rem;">Costo</div>
                            <input type="number" class="form-control form-control-sm text-center p-1"
                                value="${item.precio_costo != null ? item.precio_costo : ''}" min="0" step="any" placeholder="$0.00"
                                onchange="actualizarCostoLote(${idx}, this.value)">
                        </div>
                    </div>
                </div>
            `).join("")}
        </div>
    `;
}

function agregarAlLoteResurtido() {
    const nombre = document.getElementById("producto-resurtido").value.trim();
    const cantidad = parseFloat(document.getElementById("cantidad-resurtido").value);
    const fechaCad = document.getElementById("fecha-cad-resurtido").value;
    const costoInput = document.getElementById("costo-resurtido").value;
    const costo = costoInput !== "" ? parseFloat(costoInput) : null;

    if (!nombre) { alert("Escribe el nombre del producto o escanea su código."); return; }
    if (isNaN(cantidad) || cantidad <= 0) { alert("La cantidad debe ser mayor a 0."); return; }
    if (costo !== null && (isNaN(costo) || costo < 0)) { alert("El precio de costo no es válido."); return; }

    const productoLocal = todosLosProductos.find(p => p.nombre_producto === nombre || p.codigo_barras === nombre);

    if (productoLocal) {
        loteResurtido.push({
            id_producto: productoLocal.id_producto,
            nombre: productoLocal.nombre_producto,
            cantidad: cantidad,
            fecha_caducidad: fechaCad || null,
            precio_costo: costo !== null ? costo : productoLocal.precio_costo,
            stock_actual: productoLocal.stock_actual,
            controla_stock: productoLocal.controla_stock
        });
        liberarClaveIdempotente(opEntrada());  // #66: el lote cambió

        renderLoteResurtido();

        document.getElementById("producto-resurtido").value = "";
        document.getElementById("cantidad-resurtido").value = "1";
        document.getElementById("fecha-cad-resurtido").value = "";
        document.getElementById("costo-resurtido").value = "";
        document.getElementById("producto-resurtido").focus();
    } else {
        alert("⚠️ Producto no encontrado en el inventario. Verifícalo o regístralo como nuevo.");
    }
}

function quitarDelLoteResurtido(index) {
    loteResurtido.splice(index, 1);
    liberarClaveIdempotente(opEntrada());  // #66: el lote cambió
    renderLoteResurtido();
}

function actualizarCantidadLote(idx, val) {
    const n = parseFloat(val);
    if (isNaN(n) || n <= 0) {
        quitarDelLoteResurtido(idx);
        return;
    }
    loteResurtido[idx].cantidad = n;
    liberarClaveIdempotente(opEntrada());  // #66: el lote cambió
    renderLoteResurtido();
}

function actualizarCostoLote(idx, val) {
    const n = parseFloat(val);
    loteResurtido[idx].precio_costo = (val === "" || isNaN(n) || n < 0) ? null : n;
    guardarBorradorResurtido();  // #51: este cambio no vuelve a pintar la lista
    liberarClaveIdempotente(opEntrada());  // #66: el lote cambió
}

function precargarCostoResurtido(producto) {
    const inputCosto = document.getElementById("costo-resurtido");
    if (inputCosto.value === "" && producto.precio_costo != null) {
        inputCosto.value = producto.precio_costo;
    }
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
                precargarCostoResurtido(local);
            } else {
                fetch(`${API_URL}/producto_por_codigo/${val}`)
                    .then(r => r.json())
                    .then(data => {
                        if (data.encontrado) {
                            document.getElementById("producto-resurtido").value = data.producto.nombre_producto;
                            precargarCostoResurtido(data.producto);
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

        const exacto = todosLosProductos.find(p => p.nombre_producto.toLowerCase() === textoMin);
        if (exacto) precargarCostoResurtido(exacto);
    }, 80);
}

async function enviarTicketProveedor() {
    if (loteResurtido.length === 0) {
        alert("No hay productos en la lista para guardar.");
        return;
    }
    if (enviandoResurtido) return;
    enviandoResurtido = true;
    toggleBotones('button[onclick="enviarTicketProveedor()"]', true);

    try {
        const itemsLote = loteResurtido.map(item => ({
            id_producto: item.id_producto,
            cantidad: item.cantidad,
            fecha_caducidad: item.fecha_caducidad,
            precio_costo: item.precio_costo
        }));

        resurtidoIntentado = true;
        guardarBorradorResurtido();  // #51: si se recarga durante el envío, queda marcado

        const res = await fetch(`${API_URL}/entrada_mercancia_lote`, {
            method: "POST",
            headers: { "Content-Type": "application/json", "Idempotency-Key": claveIdempotente(opEntrada()) },
            body: JSON.stringify({
                items: itemsLote,
                nota_general: "Ticket de resurtido en lote"
            })
        });

        const data = await res.json().catch(() => ({}));

        if (!res.ok) {
            // #66: el lote y su clave se conservan para reintentar sin duplicar
            if (res.status >= 400 && res.status < 500 && res.status !== 409) {
                resurtidoIntentado = false;  // el servidor lo rechazó: no se guardó nada
                guardarBorradorResurtido();
            }
            mostrarError(typeof data.detail === "string" ? data.detail : (data.error || "Error al registrar el lote"));
            return;
        }

        liberarClaveIdempotente(opEntrada());
        loteResurtido = [];
        resurtidoIntentado = false;
        guardarBorradorResurtido();  // #51: borrar el borrador ANTES del aviso
        alert("✅ " + data.mensaje + (data.repetido ? " (ya estaba registrado, no se duplicó)" : ""));

        loteResurtido = [];
        renderLoteResurtido();
        cerrarModalResurtido();
        cargarInventario();

    } catch (e) {
        mostrarError("No se pudo confirmar el ticket. Toca Guardar otra vez: no se duplicará.");
    } finally {
        enviandoResurtido = false;
        toggleBotones('button[onclick="enviarTicketProveedor()"]', false);
    }
}