function abrirEscanerCaja() {
    document.getElementById("escaner-caja-container").style.display = "block";
    scannerCaja = new Html5Qrcode("lector-qr-caja");
    const cfg = { fps: 30, qrbox: { width: 320, height: 120 }, formatsToSupport: [ Html5QrcodeSupportedFormats.EAN_13, Html5QrcodeSupportedFormats.EAN_8, Html5QrcodeSupportedFormats.CODE_128, Html5QrcodeSupportedFormats.UPC_A, Html5QrcodeSupportedFormats.UPC_E, Html5QrcodeSupportedFormats.QR_CODE ] };
    const unidadesFraccionales = ['kg', 'g', 'litro', 'ml', 'metro'];
    scannerCaja.start({ facingMode: "environment" }, cfg,
        async (codigo) => {
            cerrarEscanerCaja();
            const res = await fetch(`${API_URL}/producto_por_codigo/${codigo}`);
            const data = await res.json();

            if (data.encontrado) {
                const esGranel = unidadesFraccionales.includes((data.producto.unidad_medida || '').toLowerCase());
                if (esGranel) {
                    document.getElementById("producto").value = data.producto.nombre_producto;
                    document.getElementById("precio").value = data.producto.precio_sugerido;
                    document.getElementById("div-cantidad").style.visibility = "visible";
                    document.getElementById("cantidad").focus();
                    document.getElementById("cantidad").select();
                } else {
                    agregarProductoAlCarrito(data.producto.nombre_producto, data.producto.precio_sugerido, 1);
                }
            } else if (data.camino === "amarillo") {
                const sug = data.sugerencia;
                const precioStr = prompt(`"${sug.nombre_producto}" encontrado en el catálogo global.\nEscribe el precio de venta para tu tienda:`);
                if (precioStr === null) return;
                const precio = parseFloat(precioStr);
                if (isNaN(precio) || precio < 0) { mostrarError("Precio no válido."); return; }
                try {
                    await fetch(`${API_URL}/registrar_producto`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            codigo_barras: codigo,
                            nombre_producto: sug.nombre_producto,
                            precio_sugerido: precio,
                            stock_actual: 0,
                            stock_minimo: 5,
                            unidad_medida: sug.unidad_medida
                        })
                    });
                    try { await cargarProductosEnMemoria(); } catch(e){}
                    const esGranel = unidadesFraccionales.includes((sug.unidad_medida || '').toLowerCase());
                    if (esGranel) {
                        document.getElementById("producto").value = sug.nombre_producto;
                        document.getElementById("precio").value = precio;
                        document.getElementById("div-cantidad").style.visibility = "visible";
                        document.getElementById("cantidad").focus();
                        document.getElementById("cantidad").select();
                    } else {
                        agregarProductoAlCarrito(sug.nombre_producto, precio, 1);
                    }
                } catch(e) { mostrarError("Error al registrar el producto del catálogo."); }
            } else {
                const nombre = prompt(`Código ${codigo} no encontrado.\nNombre del producto:`);
                if (!nombre || !nombre.trim()) { mostrarError("Registro cancelado."); return; }
                const precioStr = prompt(`Precio de venta de "${nombre.trim()}":`);
                if (precioStr === null) { mostrarError("Registro cancelado."); return; }
                const precio = parseFloat(precioStr);
                if (isNaN(precio) || precio < 0) { mostrarError("Precio no válido."); return; }
                try {
                    await fetch(`${API_URL}/registrar_producto`, {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify({
                            codigo_barras: codigo,
                            nombre_producto: nombre.trim(),
                            precio_sugerido: precio,
                            stock_actual: 0,
                            stock_minimo: 5,
                            unidad_medida: "pieza"
                        })
                    });
                    try { await cargarProductosEnMemoria(); } catch(e) {}
                    agregarProductoAlCarrito(nombre.trim(), precio);
                } catch(e) { mostrarError("Error al registrar el producto."); }
            }
        }, () => {}
    ).catch(() => mostrarError("No se pudo acceder a la cámara."));
}

function cerrarEscanerCaja() {
    if (scannerCaja) { scannerCaja.stop().catch(() => {}); scannerCaja = null; }
    document.getElementById("escaner-caja-container").style.display = "none";
}

function abrirEscanerInventario() {
    document.getElementById("escaner-inv-container").style.display = "block";
    scannerInv = new Html5Qrcode("lector-qr-inv");
    const cfg = { fps: 25, qrbox: { width: 320, height: 120 }, formatsToSupport: [ Html5QrcodeSupportedFormats.EAN_13, Html5QrcodeSupportedFormats.EAN_8, Html5QrcodeSupportedFormats.CODE_128, Html5QrcodeSupportedFormats.UPC_A, Html5QrcodeSupportedFormats.UPC_E, Html5QrcodeSupportedFormats.QR_CODE ] };
    scannerInv.start({ facingMode: "environment" }, cfg,
        (codigo) => { cerrarEscanerInventario(); document.getElementById("buscador-inventario").value = codigo; filtrarInventario(); }, () => {}
    ).catch(() => mostrarError("No se pudo acceder a la cámara."));
}

function cerrarEscanerInventario() {
    if (scannerInv) { scannerInv.stop().catch(() => {}); scannerInv = null; }
    document.getElementById("escaner-inv-container").style.display = "none";
}

function abrirEscanerResurtido() {
    document.getElementById("escaner-resurtido-container").style.display = "block";
    scannerResurtido = new Html5Qrcode("lector-qr-resurtido");
    const cfg = { fps: 25, qrbox: { width: 320, height: 120 }, formatsToSupport: [ Html5QrcodeSupportedFormats.EAN_13, Html5QrcodeSupportedFormats.EAN_8, Html5QrcodeSupportedFormats.CODE_128, Html5QrcodeSupportedFormats.UPC_A, Html5QrcodeSupportedFormats.UPC_E, Html5QrcodeSupportedFormats.QR_CODE ] };
    scannerResurtido.start({ facingMode: "environment" }, cfg,
        async (codigo) => {
            cerrarEscanerResurtido();
            document.getElementById("producto-resurtido").value = codigo;
            manejarInputResurtido();
        }, () => {}
    ).catch(() => mostrarError("No se pudo acceder a la cámara."));
}

function cerrarEscanerResurtido() {
    if (scannerResurtido) { scannerResurtido.stop().catch(() => {}); scannerResurtido = null; }
    document.getElementById("escaner-resurtido-container").style.display = "none";
}