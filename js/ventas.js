function ajustarCampos() {
    const tipo = document.getElementById("tipo").value;
    const divProducto = document.getElementById("div-producto");
    const divCantidad = document.getElementById("div-cantidad");
    const divCliente = document.getElementById("div-cliente");
    const labelMonto = document.getElementById("label-monto");
    const labelProducto = document.getElementById("label-producto");
    const btnActualizarPrecio = document.getElementById("btn-actualizar-precio");
    const inputProducto = document.getElementById("producto");
    const divBtnAgregar = document.getElementById("div-btn-agregar");
    document.getElementById("producto").value = "";
    document.getElementById("precio").value = "";
    divCliente.style.display = "none";

    carritoItems = [];
    renderCarrito();

    if (tipo === "VENTA") {
        divProducto.style.display = "block";
        divCantidad.style.visibility = "visible";
        labelProducto.innerText = "Producto:";
        labelMonto.innerText = "Precio Unitario ($):";
        inputProducto.placeholder = "Ej. Sabritas, Coca-Cola...";
        btnActualizarPrecio.style.display = "block";
        divBtnAgregar.style.display = "block";
        setTimeout(() => inputProducto.focus(), 100);
    } else if (tipo === "FIADO") {
        divProducto.style.display = "block";
        divCantidad.style.visibility = "visible";
        divCliente.style.display = "block";
        labelProducto.innerText = "Producto fiado:";
        labelMonto.innerText = "Precio ($):";
        inputProducto.placeholder = "Ej. Sabritas, Coca-Cola...";
        btnActualizarPrecio.style.display = "none";
        divBtnAgregar.style.display = "block";
        cargarClientesSelect();
        setTimeout(() => inputProducto.focus(), 100);
    } else if (tipo === "RETIRO") {
        divProducto.style.display = "block";
        divCantidad.style.visibility = "hidden";
        labelProducto.innerText = "Concepto de retiro:";
        inputProducto.placeholder = "Ej. Pago a proveedores, pasajes...";
        labelMonto.innerText = "Monto ($):";
        btnActualizarPrecio.style.display = "none";
        divBtnAgregar.style.display = "none";
    } else if (tipo === "FONDO_CAJA") {
        divProducto.style.display = "none";
        divCantidad.style.visibility = "hidden";
        labelMonto.innerText = "Monto inicial ($):";
        btnActualizarPrecio.style.display = "none";
        divBtnAgregar.style.display = "none";
        document.getElementById("producto").value = "Fondo inicial";
    }
}

async function cargarClientesSelect() {
    try {
        const res = await fetch(`${API_URL}/clientes`);
        const clientes = await res.json();
        const sel = document.getElementById("select-cliente");
        sel.innerHTML = '<option value="">— Selecciona cliente —</option>';
        clientes.forEach(c => {
            sel.innerHTML += `<option value="${c.id_cliente}">${esc(c.nombre)} (debe $${parseFloat(c.saldo_actual).toFixed(2)})</option>`;
        });
    } catch (_) {}
}

async function actualizarPrecioMaestro() {
    const nombreProducto = document.getElementById("producto").value.trim();
    const nuevoPrecio = parseFloat(document.getElementById("precio").value);
    if (!nombreProducto || isNaN(nuevoPrecio) || nuevoPrecio < 0) {
        alert("⚠️ Selecciona un producto y escribe el nuevo precio antes de presionar el botón amarillo.");
        return;
    }
    if (!confirm(`¿Actualizar el precio de "${nombreProducto}" a $${nuevoPrecio}?`)) return;
    try {
        const res = await fetch(`${API_URL}/actualizar_precio`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ nombre_producto: nombreProducto, nuevo_precio: nuevoPrecio })
        });
        const data = await res.json();
        alert(data.mensaje);
    } catch (e) { mostrarError("Error al actualizar el precio."); }
}

async function abrirTurno() {
    try {
        const res = await fetch(`${API_URL}/abrir_turno`, { method: "POST" });
        const datos = await res.json();
        idTurnoActual = datos.id_turno;
        configurarInterfazAbierta();
    } catch (e) { mostrarError("Error al conectar con el servidor."); }
}

async function registrar() {
    const tipo = document.getElementById("tipo").value;

    if (["VENTA","FIADO"].includes(tipo)) {
        if (carritoItems.length === 0) { alert("Agrega al menos un producto a la lista antes de guardar."); return; }

        if (tipo === "FIADO") {
            const idCliente = document.getElementById("select-cliente").value;
            if (!idCliente) { alert("Selecciona un cliente para el fiado."); return; }
            try {
                const resCuenta = await fetch(`${API_URL}/cuenta_fiado/${idCliente}`);
                const dataCuenta = await resCuenta.json();
                for (const item of carritoItems) {
                    await fetch(`${API_URL}/agregar_fiado`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            id_cuenta: dataCuenta.id_cuenta,
                            id_turno: idTurnoActual,
                            producto: item.nombre,
                            cantidad: item.cantidad,
                            precio: item.precio
                        })
                    });
                }
                alert(`✅ Fiado registrado para ${dataCuenta.cliente.nombre} (${carritoItems.length} producto${carritoItems.length > 1 ? 's' : ''})`);
            } catch (e) { mostrarError("Error al registrar el fiado."); return; }
        } else {
            try {
                const res = await fetch(`${API_URL}/registrar_venta_lote`, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        id_turno: idTurnoActual,
                        items: carritoItems.map(i => ({
                            producto: i.nombre,
                            cantidad: i.cantidad,
                            precio_unitario: i.precio
                        }))
                    })
                });
                if (!res.ok) { mostrarError("Error al guardar la venta."); return; }
            } catch (e) { mostrarError("Error al guardar. Verifica tu conexión."); return; }
        }
        carritoItems = [];
        renderCarrito();
        localStorage.removeItem('carrito_borrador');
        document.getElementById("producto").value = "";
        document.getElementById("precio").value = "";
        document.getElementById("cantidad").value = "1";
        document.getElementById("producto").focus();
        actualizarLista();
        return;
    }

    const montoVal = parseFloat(document.getElementById("precio").value);
    let cantidadVal = parseFloat(document.getElementById("cantidad").value);
    let nombreProducto = document.getElementById("producto").value.trim();
    if (isNaN(montoVal) || montoVal < 0) { alert("Por favor ingresa un monto válido."); return; }
    if (tipo === "RETIRO" && !nombreProducto) { alert("Favor de poner el concepto o motivo del retiro."); return; }
    if (tipo === "FONDO_CAJA") nombreProducto = "Fondo inicial";
    cantidadVal = 1;
    try {
        const res = await fetch(`${API_URL}/registrar_movimiento`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ id_turno: idTurnoActual, tipo_movimiento: tipo, producto: nombreProducto, cantidad: cantidadVal, precio_unitario: montoVal })
        });
        if (res.ok) {
            document.getElementById("producto").value = "";
            document.getElementById("precio").value = "";
            document.getElementById("cantidad").value = "1";
            ajustarCampos();
            actualizarLista();
        } else { mostrarError("El servidor rechazó el registro."); }
    } catch (e) { mostrarError("Error al guardar. Verifica tu conexión."); }
}

async function borrarMovimiento(idMovimiento) {
    if (!confirm("⚠️ ¿Estás seguro de cancelar este registro?\nEsta acción no se puede deshacer.")) return;
    const fila = document.querySelector(`tr[data-id="${idMovimiento}"]`);
    if (fila) fila.remove();
    idsEnTabla.delete(idMovimiento);
    try {
        const res = await fetch(`${API_URL}/borrar_movimiento/${idMovimiento}`, { method: "DELETE" });
        if (!res.ok) {
            mostrarError("Error al cancelar el movimiento.");
            actualizarLista();
        }
    } catch (e) {
        mostrarError("Error de conexión al cancelar.");
        actualizarLista();
    }
}

function mostrarTicket(datos) {
    const cierre = new Date().toLocaleString('es-MX', { hour: '2-digit', minute: '2-digit', day: '2-digit', month: '2-digit' });
    document.getElementById("resultado-corte").innerHTML = construirTicketHTML(datos, null, cierre);
}

async function hacerCorte() {
    if (!idTurnoActual) return;
    if (!confirm("⚠️ ¿Estás seguro de que deseas CERRAR LA CAJA y hacer el corte?\n\nYa no podrás agregar más ventas a este turno.")) return;
    try {
        const res = await fetch(`${API_URL}/corte_caja/${idTurnoActual}`, { method: "POST" });
        const datos = await res.json();
        if (!res.ok) { mostrarError(datos.detail || "Error al cerrar la caja."); return; }
        mostrarTicket(datos);
        alert("Turno Cerrado Correctamente");
        resetearInterfazCerrada();
    } catch (e) { mostrarError("Error al cerrar la caja."); }
}

function agregarProductoAlCarrito(nombre, precio, cantidad = 1) {
    const existente = carritoItems.find(i => i.nombre === nombre);
    if (existente) {
        existente.cantidad += cantidad;
    } else {
        carritoItems.push({ nombre, cantidad, precio: parseFloat(precio) });
    }
    renderCarrito();
}

function agregarALista() {
    const tipo = document.getElementById("tipo").value;
    if (!["VENTA","FIADO"].includes(tipo)) return;
    const nombre = document.getElementById("producto").value.trim();
    const precio = parseFloat(document.getElementById("precio").value);
    const cantidad = parseFloat(document.getElementById("cantidad").value) || 1;
    if (!nombre) { mostrarError("Escribe el nombre del producto."); return; }
    if (isNaN(precio) || precio < 0) { mostrarError("Escribe un precio válido."); return; }
    agregarProductoAlCarrito(nombre, precio, cantidad);
    document.getElementById("producto").value = "";
    document.getElementById("precio").value = "";
    document.getElementById("cantidad").value = "1";
    document.getElementById("producto").focus();
}

function quitarDelCarrito(idx) {
    carritoItems.splice(idx, 1);
    renderCarrito();
}

function renderCarrito() {
    const divCarrito = document.getElementById("div-carrito");
    const cuerpo = document.getElementById("cuerpo-carrito");
    const totalEl = document.getElementById("total-carrito");
    if (carritoItems.length === 0) {
        divCarrito.style.display = "none";
        totalEl.textContent = "$0.00";
        const barraSticky = document.getElementById("barra-total-sticky");
        if (barraSticky) barraSticky.style.display = "none";
        localStorage.removeItem('carrito_borrador');
        return;
    }
    divCarrito.style.display = "block";
    let total = 0;
    cuerpo.innerHTML = carritoItems.map((item, idx) => {
        const subtotal = item.cantidad * item.precio;
        total += subtotal;
        return `<tr>
            <td style="font-size:.9rem;vertical-align:middle;">${esc(item.nombre)}</td>
            <td class="text-center" style="vertical-align:middle;">
                <input type="number" class="form-control form-control-sm text-center p-1"
                    style="width:56px;display:inline-block;"
                    value="${item.cantidad}" min="0.01" step="any"
                    onchange="actualizarCantidadCarrito(${idx}, this.value)">
            </td>
            <td class="text-center" style="vertical-align:middle;font-size:.9rem;">$${item.precio.toFixed(2)}</td>
            <td class="text-center" style="vertical-align:middle;">
                <button class="btn btn-sm btn-outline-danger py-0 px-1 lh-1" onclick="quitarDelCarrito(${idx})">✕</button>
            </td>
        </tr>`;
    }).join("");
    totalEl.textContent = `$${total.toFixed(2)}`;
    const contadorEl = document.getElementById("contador-productos-carrito");
    if (contadorEl) {
        const totalUnidades = carritoItems.reduce((acc, i) => acc + i.cantidad, 0);
        contadorEl.textContent = totalUnidades % 1 === 0 ? totalUnidades : totalUnidades.toFixed(2);
    }
    const barraSticky = document.getElementById("barra-total-sticky");
    const stickyArticulos = document.getElementById("sticky-articulos");
    const stickyTotal = document.getElementById("sticky-total");
    if (barraSticky && stickyArticulos && stickyTotal) {
        const totalArticulos = carritoItems.reduce((acc, i) => acc + i.cantidad, 0);
        stickyArticulos.textContent = `${totalArticulos} artículo${totalArticulos !== 1 ? 's' : ''}`;
        stickyTotal.textContent = `$${total.toFixed(2)}`;
        barraSticky.style.display = "flex";
    }
    try { localStorage.setItem('carrito_borrador', JSON.stringify(carritoItems)); } catch(e) {}
}

function actualizarCantidadCarrito(idx, val) {
    const n = parseFloat(val);
    if (isNaN(n) || n <= 0) { quitarDelCarrito(idx); return; }
    carritoItems[idx].cantidad = n;
    renderCarrito();
}

let debounceTimer = null;
let codigoRechazado = false;

async function manejarInputProducto() {
    if (!["VENTA","FIADO"].includes(document.getElementById("tipo").value)) return;
    const texto = document.getElementById("producto").value;
    const divCantidad = document.getElementById("div-cantidad");
    if (!texto) {
        codigoRechazado = false;
        divCantidad.style.visibility = "visible";
        return;
    }
    if (codigoRechazado) return;

    const unidadesFraccionales = ['kg', 'g', 'litro', 'ml', 'metro'];

    const esCodigoBarras = /^\d{4,}$/.test(texto.trim());
    if (esCodigoBarras) {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
            const val = document.getElementById("producto").value.trim();
            if (!/^\d{4,}$/.test(val)) return;
            const local = todosLosProductos.find(p => p.codigo_barras === val);
            if (local) {
                const esGranel = unidadesFraccionales.includes((local.unidad_medida || '').toLowerCase());
                if (esGranel) {
                    document.getElementById("producto").value = local.nombre_producto;
                    document.getElementById("precio").value = local.precio_sugerido;
                    document.getElementById("div-cantidad").style.visibility = "visible";
                    document.getElementById("cantidad").focus();
                    document.getElementById("cantidad").select();
                } else {
                    agregarProductoAlCarrito(local.nombre_producto, local.precio_sugerido);
                    document.getElementById("producto").value = "";
                    document.getElementById("precio").value = "";
                    document.getElementById("cantidad").value = "1";
                    document.getElementById("producto").focus();
                }
            } else {
                fetch(`${API_URL}/producto_por_codigo/${val}`)
                    .then(r => r.json())
                    .then(async (data) => {
                        if (data.encontrado) {
                            // CAMINO VERDE
                            const esGranel = unidadesFraccionales.includes((data.producto.unidad_medida || '').toLowerCase());
                            if (esGranel) {
                                document.getElementById("producto").value = data.producto.nombre_producto;
                                document.getElementById("precio").value = data.producto.precio_sugerido;
                                document.getElementById("div-cantidad").style.visibility = "visible";
                                document.getElementById("cantidad").focus();
                                document.getElementById("cantidad").select();
                            } else {
                                agregarProductoAlCarrito(data.producto.nombre_producto, data.producto.precio_sugerido);
                                document.getElementById("producto").value = "";
                                document.getElementById("precio").value = "";
                                document.getElementById("cantidad").value = "1";
                                document.getElementById("producto").focus();
                            }
                        } else if (data.camino === "amarillo") {
                            // CAMINO AMARILLO
                            const sug = data.sugerencia;
                            const precioStr = prompt(`"${sug.nombre_producto}" encontrado en el catálogo global.\\nEscribe el precio de venta para tu tienda:`);
                            if (precioStr === null) {
                                codigoRechazado = true;
                                mostrarError("Borra el código del input para continuar.");
                                return;
                            }
                            const precio = parseFloat(precioStr);
                            if (isNaN(precio) || precio < 0) { mostrarError("Precio no válido."); return; }
                            try {
                                await fetch(`${API_URL}/registrar_producto`, {
                                    method: "POST",
                                    headers: { "Content-Type": "application/json" },
                                    body: JSON.stringify({
                                        codigo_barras: val,
                                        nombre_producto: sug.nombre_producto,
                                        precio_sugerido: precio,
                                        stock_actual: 0,
                                        stock_minimo: 5,
                                        unidad_medida: sug.unidad_medida
                                    })
                                });
                                try { await cargarProductosEnMemoria(); } catch(e) {}
                                const esGranel = unidadesFraccionales.includes((sug.unidad_medida || '').toLowerCase());
                                if (esGranel) {
                                    document.getElementById("producto").value = sug.nombre_producto;
                                    document.getElementById("precio").value = precio;
                                    document.getElementById("div-cantidad").style.visibility = "visible";
                                    document.getElementById("cantidad").focus();
                                    document.getElementById("cantidad").select();
                                } else {
                                    agregarProductoAlCarrito(sug.nombre_producto, precio, 1);
                                    document.getElementById("producto").value = "";
                                    document.getElementById("precio").value = "";
                                    document.getElementById("cantidad").value = "1";
                                    document.getElementById("producto").focus();
                                }
                            } catch(e) { mostrarError("Error al registrar el producto del catálogo."); }
                        } else {
                            // CAMINO ROJO
                            const nombre = prompt(`Código ${val} no encontrado.\\nNombre del producto:`);
                            if (!nombre || !nombre.trim()) {
                                codigoRechazado = true;
                                mostrarError("Borra el código del input para continuar.");
                                return;
                            }
                            const precioStr = prompt(`Precio de venta de "${nombre.trim()}":`);
                            if (precioStr === null) { mostrarError("Registro cancelado."); return; }
                            const precio = parseFloat(precioStr);
                            if (isNaN(precio) || precio < 0) { mostrarError("Precio no válido."); return; }
                            try {
                                await fetch(`${API_URL}/registrar_producto`, {
                                    method: "POST",
                                    headers: { "Content-Type": "application/json" },
                                    body: JSON.stringify({
                                        codigo_barras: val,
                                        nombre_producto: nombre.trim(),
                                        precio_sugerido: precio,
                                        stock_actual: 0,
                                        stock_minimo: 5,
                                        unidad_medida: "pieza"
                                    })
                                });
                                try { await cargarProductosEnMemoria(); } catch(e) {}
                                agregarProductoAlCarrito(nombre.trim(), precio);
                                document.getElementById("producto").value = "";
                                document.getElementById("precio").value = "";
                                document.getElementById("cantidad").value = "1";
                                document.getElementById("producto").focus();
                            } catch(e) { mostrarError("Error al registrar el producto."); }
                        }
                    }).catch(() => mostrarError("Error al buscar por código."));
            }
        }, 400);
        return;
    }

    clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => {
        const textoActual = document.getElementById("producto").value;
        if (!textoActual || /^\d{4,}$/.test(textoActual.trim())) return;
        const textoMin = textoActual.trim().toLowerCase();

        const resultados = todosLosProductos.filter(p =>
            p.nombre_producto.toLowerCase().includes(textoMin) ||
            (p.codigo_barras && p.codigo_barras.includes(textoMin))
        ).slice(0, 20);

        const datalist = document.getElementById("lista-productos");
        datalist.innerHTML = resultados.map(p => `<option value="${esc(p.nombre_producto)}">`).join("");

        const coincidencia = resultados.find(p => p.nombre_producto === textoActual.trim());
        if (coincidencia) {
            const esGranel = unidadesFraccionales.includes((coincidencia.unidad_medida || '').toLowerCase());
            if (esGranel) {
                document.getElementById("precio").value = coincidencia.precio_sugerido;
                divCantidad.style.visibility = "visible";
                document.getElementById("cantidad").focus();
                document.getElementById("cantidad").select();
            } else {
                document.getElementById("precio").value = coincidencia.precio_sugerido;
                divCantidad.style.visibility = "visible";
            }
        } else {
            divCantidad.style.visibility = "visible";
        }
    }, 80);
}

function manejarEnterProducto(event) {
    if (event.key === "Enter") {
        event.preventDefault();
        const tipo = document.getElementById("tipo").value;
        if (!["VENTA","FIADO"].includes(tipo)) return;

        const texto = document.getElementById("producto").value.trim();

        if (/^\d{4,}$/.test(texto)) {
            clearTimeout(debounceTimer);
            const unidadesFraccionales = ['kg', 'g', 'litro', 'ml', 'metro'];

            const local = todosLosProductos.find(p => p.codigo_barras === texto);
            if (local) {
                const esGranel = unidadesFraccionales.includes((local.unidad_medida || '').toLowerCase());
                if (esGranel) {
                    document.getElementById("producto").value = local.nombre_producto;
                    document.getElementById("precio").value = local.precio_sugerido;
                    document.getElementById("div-cantidad").style.visibility = "visible";
                    document.getElementById("cantidad").focus();
                    document.getElementById("cantidad").select();
                } else {
                    agregarProductoAlCarrito(local.nombre_producto, local.precio_sugerido);
                    document.getElementById("producto").value = "";
                    document.getElementById("precio").value = "";
                    document.getElementById("cantidad").value = "1";
                    document.getElementById("producto").focus();
                }
                return;
            }

            fetch(`${API_URL}/producto_por_codigo/${texto}`)
                .then(r => r.json())
                .then(async (data) => {
                    if (data.encontrado) {
                        const esGranel = unidadesFraccionales.includes((data.producto.unidad_medida || '').toLowerCase());
                        if (esGranel) {
                            document.getElementById("producto").value = data.producto.nombre_producto;
                            document.getElementById("precio").value = data.producto.precio_sugerido;
                            document.getElementById("div-cantidad").style.visibility = "visible";
                            document.getElementById("cantidad").focus();
                            document.getElementById("cantidad").select();
                        } else {
                            agregarProductoAlCarrito(data.producto.nombre_producto, data.producto.precio_sugerido);
                            document.getElementById("producto").value = "";
                            document.getElementById("precio").value = "";
                            document.getElementById("cantidad").value = "1";
                            document.getElementById("producto").focus();
                        }
                    } else if (data.camino === "amarillo") {
                        const sug = data.sugerencia;
                        const precioStr = prompt(`"${sug.nombre_producto}" encontrado en el catálogo global.\nEscribe el precio de venta para tu tienda:`);
                        if (precioStr === null) {
                            codigoRechazado = true;
                            mostrarError("Borra el código del input para continuar.");
                            return;
                        }
                        const precio = parseFloat(precioStr);
                        if (isNaN(precio) || precio < 0) { mostrarError("Precio no válido."); return; }
                        try {
                            await fetch(`${API_URL}/registrar_producto`, {
                                method: "POST",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({
                                    codigo_barras: texto,
                                    nombre_producto: sug.nombre_producto,
                                    precio_sugerido: precio,
                                    stock_actual: 0,
                                    stock_minimo: 5,
                                    unidad_medida: sug.unidad_medida
                                })
                            });
                            try { await cargarProductosEnMemoria(); } catch(e) {}
                            const esGranel = unidadesFraccionales.includes((sug.unidad_medida || '').toLowerCase());
                            if (esGranel) {
                                document.getElementById("producto").value = sug.nombre_producto;
                                document.getElementById("precio").value = precio;
                                document.getElementById("div-cantidad").style.visibility = "visible";
                                document.getElementById("cantidad").focus();
                                document.getElementById("cantidad").select();
                            } else {
                                agregarProductoAlCarrito(sug.nombre_producto, precio, 1);
                                document.getElementById("producto").value = "";
                                document.getElementById("precio").value = "";
                                document.getElementById("cantidad").value = "1";
                                document.getElementById("producto").focus();
                            }
                        } catch(e) { mostrarError("Error al registrar el producto del catálogo."); }
                    } else {
                        const nombre = prompt(`Código ${texto} no encontrado.\\nNombre del producto:`);
                        if (!nombre || !nombre.trim()) {
                            codigoRechazado = true;
                            mostrarError("Borra el código del input para continuar.");
                            return;
                        }
                        const precioStr = prompt(`Precio de venta de "${nombre.trim()}":`);
                        if (precioStr === null) { mostrarError("Registro cancelado."); return; }
                        const precio = parseFloat(precioStr);
                        if (isNaN(precio) || precio < 0) { mostrarError("Precio no válido."); return; }
                        try {
                            await fetch(`${API_URL}/registrar_producto`, {
                                method: "POST",
                                headers: { "Content-Type": "application/json" },
                                body: JSON.stringify({
                                    codigo_barras: texto,
                                    nombre_producto: nombre.trim(),
                                    precio_sugerido: precio,
                                    stock_actual: 0,
                                    stock_minimo: 5,
                                    unidad_medida: "pieza"
                                })
                            });
                            try { await cargarProductosEnMemoria(); } catch(e) {}
                            agregarProductoAlCarrito(nombre.trim(), precio);
                            document.getElementById("producto").value = "";
                            document.getElementById("precio").value = "";
                            document.getElementById("cantidad").value = "1";
                            document.getElementById("producto").focus();
                        } catch(e) { mostrarError("Error al registrar el producto."); }
                    }
                })
                .catch(() => mostrarError("Error al buscar por código."));
            return;
        }

        agregarALista();
    }
}