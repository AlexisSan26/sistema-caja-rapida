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



// #66: clave de idempotencia. Se reutiliza mientras el envío sea idéntico (reintento tras
// un corte de red) y cambia cuando el contenido cambia o la operación terminó bien.
const _clavesIdem = {};
function claveIdempotente(operacion, payload) {
    const huella = JSON.stringify(payload);
    const previa = _clavesIdem[operacion];
    if (previa && previa.huella === huella) return previa.clave;
    const clave = (window.crypto && crypto.randomUUID)
        ? crypto.randomUUID().replace(/-/g, '')
        : Date.now().toString(36) + Math.random().toString(36).slice(2, 12);
    _clavesIdem[operacion] = { huella, clave };
    return clave;
}
function liberarClaveIdempotente(operacion) { delete _clavesIdem[operacion]; }