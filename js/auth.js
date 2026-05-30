async function loginSaaS() {
    const usr = document.getElementById('login-user-saas').value.trim();
    const pwd = document.getElementById('login-pass-saas').value.trim();
    if(!usr || !pwd) return alert("Ingresa usuario y contraseña.");

    try {
        const res = await originalFetch(`${API_URL}/login`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({username: usr, password: pwd})
        });
        if (res.ok) {
            const data = await res.json();
            localStorage.setItem('saas_token', data.access_token);
            document.getElementById('modal-login-saas').style.display = 'none';
            window.location.reload();
        } else {
            alert('❌ Usuario o contraseña incorrectos.');
        }
    } catch(e) {
        alert('❌ Error al conectar con el servidor.');
    }
}

function logoutSaaS() {
    localStorage.removeItem('saas_token');
    document.getElementById('modal-login-saas').style.display = 'flex';
    cerrarMenu();
}