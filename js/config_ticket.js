let reglasConfig = [];
let reglaActivaIdx = null;

async function cargarConfiguracionTicket() {
    try { const r = await fetch(`${API_URL}/inventario`); todosLosProductos = await r.json(); } catch (_) {}
    try {
        const res = await fetch(`${API_URL}/configuracion_tienda`);
        const data = await res.json();
        reglasConfig = data.reglas || [];
        renderReglasConfig();
    } catch (e) { mostrarError("Error al cargar configuración"); }
}

function renderReglasConfig() {
    const cont = document.getElementById("contenedor-reglas-config");
    if (reglasConfig.length === 0) {
        cont.innerHTML = "<p class='text-muted text-center py-2'>Sin grupos. Agrega uno.</p>";
        return;
    }
    cont.innerHTML = reglasConfig.map((r, idx) => {
        const numProds = (r.ids_productos || []).length;
        return `<div class="border rounded p-3 mb-3 bg-white regla-bloque">
            <div class="d-flex justify-content-between align-items-center mb-2">
                <input type="text" class="form-control fw-bold me-2 reg-nom-cfg" style="max-width:200px;"
                    value="${esc(r.nombre)}" placeholder="Nombre del grupo">
                <button class="btn btn-sm btn-outline-danger" onclick="eliminarReglaConfig(${idx})">✕</button>
            </div>
            <label class="fw-bold mb-1" style="font-size:.85rem;">Palabras clave <span class="text-muted fw-normal">(separadas por coma)</span></label>
            <input type="text" class="form-control mb-2 reg-clav-cfg" placeholder="Ej: cigarro, time" value="${esc(r.claves || '')}">
            <button class="btn btn-sm btn-outline-secondary w-100" onclick="abrirSelectorProductos(${idx})">
                📦 Productos seleccionados: <strong>${numProds}</strong>
            </button>
        </div>`;
    }).join("");
}

function agregarFilaReglaConfig() {
    reglasConfig.push({ nombre: "", claves: "", ids_productos: [] });
    renderReglasConfig();
}

function eliminarReglaConfig(idx) {
    _sincronizarInputsReglas();
    reglasConfig.splice(idx, 1);
    renderReglasConfig();
}

function _sincronizarInputsReglas() {
    document.querySelectorAll(".regla-bloque").forEach((div, idx) => {
        if (!reglasConfig[idx]) return;
        const nom = div.querySelector(".reg-nom-cfg");
        const clav = div.querySelector(".reg-clav-cfg");
        if (nom) reglasConfig[idx].nombre = nom.value.trim();
        if (clav) reglasConfig[idx].claves = clav.value.trim();
    });
}

function abrirSelectorProductos(idx) {
    _sincronizarInputsReglas();
    reglaActivaIdx = idx;
    document.getElementById("buscador-selector-prod").value = "";
    renderListaSelectorProductos(todosLosProductos);
    document.getElementById("modal-selector-productos").style.display = "block";
}

function cerrarSelectorProductos() {
    document.getElementById("modal-selector-productos").style.display = "none";
    renderReglasConfig();
    reglaActivaIdx = null;
}

function filtrarSelectorProductos() {
    const q = document.getElementById("buscador-selector-prod").value.toLowerCase();
    const filtrados = todosLosProductos.filter(p => p.nombre_producto.toLowerCase().includes(q));
    renderListaSelectorProductos(filtrados);
}

function renderListaSelectorProductos(productos) {
    if (reglaActivaIdx === null) return;
    const idsSeleccionados = (reglasConfig[reglaActivaIdx].ids_productos || []).map(Number);
    const cont = document.getElementById("lista-selector-productos");
    cont.innerHTML = productos.map(p => {
        if (!p.id_producto) return "";
        const sel = idsSeleccionados.includes(Number(p.id_producto));
        return `<div class="d-flex align-items-center p-2 border-bottom" style="cursor:pointer;" onclick="toggleProductoSelector(${p.id_producto})">
            <span style="font-size:1.2rem;margin-right:.75rem;">${sel ? '✅' : '⬜'}</span>
            <span style="font-size:.95rem;">${esc(p.nombre_producto)}</span>
        </div>`;
    }).join("");
}

function toggleProductoSelector(idProducto) {
    if (reglaActivaIdx === null) return;
    const ids = (reglasConfig[reglaActivaIdx].ids_productos || []).map(Number);
    const pos = ids.indexOf(Number(idProducto));
    if (pos === -1) { ids.push(Number(idProducto)); } else { ids.splice(pos, 1); }
    reglasConfig[reglaActivaIdx].ids_productos = ids;
    const q = document.getElementById("buscador-selector-prod").value.toLowerCase();
    const filtrados = todosLosProductos.filter(p => p.nombre_producto.toLowerCase().includes(q));
    renderListaSelectorProductos(filtrados);
}

async function guardarConfiguracionTicket() {
    _sincronizarInputsReglas();
    const reglasFiltradas = reglasConfig.filter(r => r.nombre);
    try {
        const res = await fetch(`${API_URL}/configuracion_tienda`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ reglas: reglasFiltradas })
        });
        const data = await res.json();
        alert("✅ " + data.mensaje);
        reglasConfig = reglasFiltradas;
        renderReglasConfig();
    } catch (e) { mostrarError("Error al guardar configuración"); }
}