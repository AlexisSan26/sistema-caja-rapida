const API_URL = window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost"
    ? "http://127.0.0.1:8000"
    : /^(192\.168\.|10\.|172\.(1[6-9]|2\d|3[01])\.)/.test(window.location.hostname)
        ? `http://${window.location.hostname}:8000`
        : "https://sistema-caja-rapida.onrender.com";

const originalFetch = window.fetch;
window.fetch = async (url, options = {}) => {
    if (typeof url === 'string' && url.startsWith(API_URL) && !url.includes('/login')) {
        const token = localStorage.getItem('saas_token');
        if (token) {
            options.headers = {
                ...options.headers,
                'Authorization': `Bearer ${token}`
            };
        }
    }
    const res = await originalFetch(url, options);
    if (res.status === 401) {
        logoutSaaS();
        throw new Error('Sesión expirada');
    }
    return res;
};



// #66: la clave va atada a la OPERACIÓN EN CURSO (p. ej. el carrito), no a su contenido.
// Se guarda en localStorage para sobrevivir a una recarga y se libera cuando la operación
// cambia o termina bien. El servidor compara el contenido y rechaza (409) si no coincide.
const _clavesIdem = {};
function _nuevaClaveIdem() {
    return (window.crypto && crypto.randomUUID)
        ? crypto.randomUUID().replace(/-/g, '')
        : Date.now().toString(36) + Math.random().toString(36).slice(2, 12);
}
function claveIdempotente(operacion) {
    try {
        const guardada = localStorage.getItem('idem_' + operacion);
        if (guardada) return guardada;
        const nueva = _nuevaClaveIdem();
        localStorage.setItem('idem_' + operacion, nueva);
        return nueva;
    } catch (e) {
        return _clavesIdem[operacion] || (_clavesIdem[operacion] = _nuevaClaveIdem());
    }
}
function liberarClaveIdempotente(operacion) {
    delete _clavesIdem[operacion];
    try { localStorage.removeItem('idem_' + operacion); } catch (e) {}
}