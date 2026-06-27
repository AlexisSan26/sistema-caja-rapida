const API_URL = window.location.hostname === "127.0.0.1" || window.location.hostname === "localhost"
    ? "http://127.0.0.1:8000"
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