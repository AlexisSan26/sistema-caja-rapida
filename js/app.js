// ─── Variables globales ───────────────────────────────────────────────────
let idTurnoActual = null;
let productosMemoria = [];
let intervaloActualizacion = null;
let idsEnTabla = new Set();
let todosLosProductos = [];
let proveedorFiltro = "";
let scannerCaja = null;
let scannerInv = null;
let scannerResurtido = null;
let productoEnEdicion = null;
let clienteFiadoActual = null;
let carritoItems = [];
let loteResurtido = [];
let timeoutError = null;
let nombreTienda = "";
let nombreUsuario = "";

// ─── Init ─────────────────────────────────────────────────────────────────
window.onload = function () {
    if (!localStorage.getItem('saas_token')) {
        document.getElementById('modal-login-saas').style.display = 'flex';
    } else {
        document.getElementById('modal-login-saas').style.display = 'none';
        mostrarFechaDelDia();
        cargarDatosUsuario();
        verificarEstadoInicial();
        setTimeout(cargarAlertas, 2000);
    }
};

async function cargarDatosUsuario() {
    try {
        const res = await fetch(`${API_URL}/yo`);
        const data = await res.json();
        nombreTienda = data.nombre_tienda || "";
        nombreUsuario = data.username || "";
        const el = document.getElementById("info-tienda-usuario");
        if (el) el.textContent = `${nombreTienda} · ${nombreUsuario}`;
    } catch(e) {}
}