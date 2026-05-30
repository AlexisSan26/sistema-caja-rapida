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

// ─── Init ─────────────────────────────────────────────────────────────────
window.onload = function () {
    if (!localStorage.getItem('saas_token')) {
        document.getElementById('modal-login-saas').style.display = 'flex';
    } else {
        document.getElementById('modal-login-saas').style.display = 'none';
        mostrarFechaDelDia();
        verificarEstadoInicial();
        setTimeout(cargarAlertas, 2000);
    }
};