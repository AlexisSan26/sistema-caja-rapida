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
        } else if (res.status === 429) {
            alert('⏳ Demasiados intentos. Espera un minuto e inténtalo de nuevo.');
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

function abrirCambiarPassword() {
    cerrarMenu();
    ["pwd-actual", "pwd-nueva", "pwd-repetir"].forEach(id => document.getElementById(id).value = "");
    document.getElementById("pwd-msg").textContent = "";
    document.getElementById("btn-guardar-pwd").disabled = false;
    document.getElementById("modal-cambiar-pwd").style.display = "flex";
}

function cerrarCambiarPassword() {
    document.getElementById("modal-cambiar-pwd").style.display = "none";
}

async function guardarCambiarPassword() {
    const actual = document.getElementById("pwd-actual").value.trim();
    const nueva = document.getElementById("pwd-nueva").value.trim();
    const repetir = document.getElementById("pwd-repetir").value.trim();
    const msg = document.getElementById("pwd-msg");
    const btn = document.getElementById("btn-guardar-pwd");
    msg.className = "small mb-2 text-danger";

    if (!actual || !nueva || !repetir) { msg.textContent = "Completa los tres campos."; return; }
    if (nueva.length < 6) { msg.textContent = "La contraseña nueva debe tener al menos 6 caracteres."; return; }
    if (nueva.length > 72) { msg.textContent = "La contraseña nueva es demasiado larga (máximo 72)."; return; }
    if (nueva !== repetir) { msg.textContent = "Las contraseñas nuevas no coinciden."; return; }

    btn.disabled = true;
    let exito = false;
    try {
        const res = await fetch(`${API_URL}/yo/password`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ password_actual: actual, password_nueva: nueva })
        });
        const datos = await res.json().catch(() => ({}));
        if (res.status === 429) { msg.textContent = "Demasiados intentos. Espera un minuto e intenta de nuevo."; return; }
        if (!res.ok) {
            msg.textContent = typeof datos.detail === "string" ? datos.detail : "No se pudo cambiar la contraseña. Revisa los datos.";
            return;
        }
        localStorage.setItem("saas_token", datos.access_token);
        exito = true;
        msg.className = "small mb-2 text-success";
        msg.textContent = "✅ Contraseña actualizada. Se cerró tu sesión en otros dispositivos.";
        setTimeout(cerrarCambiarPassword, 1800);
    } catch (e) {
        msg.textContent = "No se pudo conectar con el servidor. Intenta de nuevo.";
    } finally {
        if (!exito) btn.disabled = false;
    }
}