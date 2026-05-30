// ── Config ───────────────────────────────────────────────────
const API = 'https://sistema-caja-rapida.onrender.com';

// ── Estado ───────────────────────────────────────────────────
let TOKEN = localStorage.getItem('caja_rapida_admin_token') || null;
let modalResetId = null;
let modalDelId   = null;
let tiendas = [];
let modalEditTiendaId = null;
let modalEditUsuarioId = null;

// ── Login ────────────────────────────────────────────────────
document.addEventListener('keydown', e => {
  if (e.key === 'Enter' && document.getElementById('login-screen').style.display !== 'none') {
    hacerLogin();
  }
});

async function hacerLogin() {
  const user = document.getElementById('inp-user').value.trim();
  const pass = document.getElementById('inp-pass').value;
  const btn  = document.getElementById('btn-login');
  const err  = document.getElementById('login-error');

  if (!user || !pass) { mostrarError('Completa los campos'); return; }

  btn.disabled = true;
  btn.innerHTML = '<span class="spinner"></span>';
  err.style.display = 'none';

  try {
    const r = await fetch(`${API}/login`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: user, password: pass })
    });
    const data = await r.json();

    if (!r.ok) throw new Error(data.detail || 'Error de autenticación');
    if (data.rol !== 'superadmin') throw new Error('Este usuario no tiene acceso de superadmin');

    TOKEN = data.access_token;

    const tiempoExpiracion = Date.now() + (2 * 24 * 60 * 60 * 1000);
    localStorage.setItem('caja_rapida_admin_token', TOKEN);
    localStorage.setItem('caja_rapida_admin_expira', tiempoExpiracion);

    document.getElementById('login-screen').style.display = 'none';
    document.getElementById('app-shell').style.display = 'block';
    iniciarApp();
  } catch (e) {
    mostrarError(e.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = 'Entrar';
  }
}

function mostrarError(msg) {
  const el = document.getElementById('login-error');
  el.textContent = msg;
  el.style.display = 'block';
}

function logout() {
  TOKEN = null;
  localStorage.removeItem('caja_rapida_admin_token');
  localStorage.removeItem('caja_rapida_admin_expira');
  document.getElementById('app-shell').style.display = 'none';
  document.getElementById('login-screen').style.display = 'flex';
  document.getElementById('inp-pass').value = '';
}

// ── App init ─────────────────────────────────────────────────
function iniciarApp() {
  cargarVentasHoy();
  cargarTiendas();
  cargarUsuarios();
  cargarSuscripciones();
}

// ── Tabs ─────────────────────────────────────────────────────
function cambiarTab(tab) {
  document.querySelectorAll('.section').forEach(s => s.classList.remove('activa'));
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('activo'));
  document.getElementById(`sec-${tab}`).classList.add('activa');
  document.getElementById(`tab-${tab}`).classList.add('activo');
}

// ── API helper ───────────────────────────────────────────────
async function api(method, path, body) {
  const opts = {
    method,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${TOKEN}`
    }
  };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(`${API}${path}`, opts);
  const data = await r.json();
  if (!r.ok) throw new Error(data.detail || JSON.stringify(data));
  return data;
}

// ── Toast ────────────────────────────────────────────────────
let toastTimer;
function toast(msg, tipo = 'ok') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = tipo;
  el.style.display = 'block';
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.style.display = 'none', 3000);
}

// ── Modales ──────────────────────────────────────────────────
function abrirModal(id) { document.getElementById(id).classList.add('visible'); }
function cerrarModal(id) { document.getElementById(id).classList.remove('visible'); }

// ════════════════════════════════════════
// VENTAS HOY
// ════════════════════════════════════════
async function cargarVentasHoy() {
  try {
    const rows = await api('GET', '/admin/ventas_hoy');
    let totalVentas = 0, totalNeto = 0, totalTiendas = rows.length;
    let tiendas_activas = 0;

    rows.forEach(r => {
      totalVentas += r.ventas_hoy;
      totalNeto   += r.neto_hoy;
      if (r.activa) tiendas_activas++;
    });

    document.getElementById('totales-dia').innerHTML = `
      <div class="card-stat">
        <div class="stat-label">Venta total hoy</div>
        <div class="stat-val">$${fmt(totalVentas)}</div>
      </div>
      <div class="card-stat">
        <div class="stat-label">Neto total hoy</div>
        <div class="stat-val">$${fmt(totalNeto)}</div>
      </div>
      <div class="card-stat">
        <div class="stat-label">Tiendas activas</div>
        <div class="stat-val">${tiendas_activas} / ${totalTiendas}</div>
      </div>
    `;

    document.getElementById('ventas-tiendas').innerHTML = rows.map(r => `
      <div class="tienda-venta-card">
        <div class="tvc-nombre">
          <span class="pill ${r.activa ? 'pill-ok' : 'pill-off'}">${r.activa ? 'activa' : 'inactiva'}</span>
          ${esc(r.nombre_comercial)}
        </div>
        <div class="tvc-grid">
          <div class="tvc-item">
            <div class="tvc-label">Ventas</div>
            <div class="tvc-val verde">$${fmt(r.ventas_hoy)}</div>
          </div>
          <div class="tvc-item">
            <div class="tvc-label">Retiros</div>
            <div class="tvc-val rojo">$${fmt(r.retiros_hoy)}</div>
          </div>
          <div class="tvc-item">
            <div class="tvc-label">Neto</div>
            <div class="tvc-val">$${fmt(r.neto_hoy)}</div>
          </div>
        </div>
      </div>
    `).join('');
  } catch (e) {
    toast('Error cargando ventas: ' + e.message, 'error');
  }
}

// ════════════════════════════════════════
// TIENDAS
// ════════════════════════════════════════
async function cargarTiendas() {
  try {
    tiendas = await api('GET', '/admin/tiendas');
    renderTiendas();
    poblarSelectTiendas();
  } catch (e) {
    toast('Error cargando tiendas: ' + e.message, 'error');
  }
}

function renderTiendas() {
  document.getElementById('tbl-tiendas').innerHTML = tiendas.map(t => `
    <tr>
      <td><span style="font-family:var(--mono);color:var(--muted)">#${t.id_tienda}</span></td>
      <td><strong>${esc(t.nombre_comercial)}</strong></td>
      <td><span class="pill ${t.activa ? 'pill-ok' : 'pill-off'}">${t.activa ? 'activa' : 'inactiva'}</span></td>
      <td style="color:var(--muted)">${t.total_usuarios}</td>
      <td style="color:var(--muted)">${t.turnos_hoy}</td>
      <td>
        ${t.activa
          ? `<button class="btn-tbl btn-desact" onclick="toggleTienda(${t.id_tienda}, false)">Desactivar</button>`
          : `<button class="btn-tbl btn-activar" onclick="toggleTienda(${t.id_tienda}, true)">Activar</button>`
        }
        <button class="btn-tbl btn-reset" onclick="abrirEditarTienda(${t.id_tienda}, '${esc(t.nombre_comercial)}')">✏️ Editar</button>
        <button class="btn-tbl btn-activar" onclick="verInventarioTienda(${t.id_tienda})">📦 Inventario</button>
      </td>
    </tr>
  `).join('');
}

function poblarSelectTiendas() {
  const sel = document.getElementById('nu-tienda');
  sel.innerHTML = tiendas.filter(t => t.activa).map(t =>
    `<option value="${t.id_tienda}">${esc(t.nombre_comercial)}</option>`
  ).join('');
}

async function crearTienda() {
  const nombre = document.getElementById('nueva-tienda-nombre').value.trim();
  if (!nombre) { toast('Escribe un nombre', 'error'); return; }
  try {
    await api('POST', '/admin/tiendas', { nombre_comercial: nombre });
    document.getElementById('nueva-tienda-nombre').value = '';
    toast('✅ Tienda creada');
    await cargarTiendas();
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

async function toggleTienda(id, activar) {
  const endpoint = activar ? 'activar' : 'desactivar';
  try {
    await api('PUT', `/admin/tiendas/${id}/${endpoint}`);
    toast(`Tienda ${activar ? 'activada' : 'desactivada'}`);
    await cargarTiendas();
    await cargarVentasHoy();
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

// ════════════════════════════════════════
// USUARIOS
// ════════════════════════════════════════
async function cargarUsuarios() {
  try {
    const usuarios = await api('GET', '/admin/usuarios');
    document.getElementById('tbl-usuarios').innerHTML = usuarios.map(u => `
      <tr>
        <td><span style="font-family:var(--mono);color:var(--muted)">#${u.id_usuario}</span></td>
        <td><strong>${esc(u.username)}</strong></td>
        <td><span class="pill ${u.rol === 'superadmin' ? 'pill-adm' : 'pill-caj'}">${u.rol}</span></td>
        <td style="color:var(--muted)">${esc(u.nombre_comercial)}</td>
        <td style="display:flex;gap:.4rem;flex-wrap:wrap">
          <button class="btn-tbl btn-reset" onclick="abrirReset(${u.id_usuario}, '${esc(u.username)}')">🔑 Reset pw</button>
          <button class="btn-tbl btn-reset" onclick="abrirEditarUsuario(${u.id_usuario}, '${esc(u.username)}', ${u.id_tienda}, '${esc(u.rol)}')">✏️ Editar</button>
          <button class="btn-tbl btn-del"   onclick="abrirEliminar(${u.id_usuario}, '${esc(u.username)}')">🗑️ Eliminar</button>
        </td>
      </tr>
    `).join('');
  } catch (e) {
    toast('Error cargando usuarios: ' + e.message, 'error');
  }
}

async function crearUsuario() {
  const username = document.getElementById('nu-username').value.trim();
  const password = document.getElementById('nu-password').value;
  const id_tienda = parseInt(document.getElementById('nu-tienda').value);
  const rol = document.getElementById('nu-rol').value;

  if (!username || !password) { toast('Completa username y contraseña', 'error'); return; }
  if (password.length < 4) { toast('Contraseña muy corta (mín 4 caracteres)', 'error'); return; }

  try {
    await api('POST', '/admin/usuarios', { username, password, id_tienda, rol });
    document.getElementById('nu-username').value = '';
    document.getElementById('nu-password').value = '';
    toast('✅ Usuario creado');
    cargarUsuarios();
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

function abrirReset(id, uname) {
  modalResetId = id;
  document.getElementById('modal-reset-uname').value = uname;
  document.getElementById('modal-reset-pass').value = '';
  abrirModal('modal-reset');
}

async function confirmarReset() {
  const pass = document.getElementById('modal-reset-pass').value;
  if (!pass || pass.length < 4) { toast('Contraseña muy corta', 'error'); return; }
  try {
    await api('PUT', `/admin/usuarios/${modalResetId}/reset_password`, { nuevo_password: pass });
    cerrarModal('modal-reset');
    toast('✅ Contraseña actualizada');
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

function abrirEliminar(id, uname) {
  modalDelId = id;
  document.getElementById('modal-del-uname').textContent = uname;
  abrirModal('modal-del-user');
}

async function confirmarEliminarUsuario() {
  try {
    await api('DELETE', `/admin/usuarios/${modalDelId}`);
    cerrarModal('modal-del-user');
    toast('Usuario eliminado');
    cargarUsuarios();
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

// ════════════════════════════════════════
// MÓDULO 1: EDITAR TIENDA
// ════════════════════════════════════════
function abrirEditarTienda(id, nombre) {
  modalEditTiendaId = id;
  document.getElementById('et-nombre').value = nombre;
  abrirModal('modal-editar-tienda');
}

async function confirmarEditarTienda() {
  const nombre = document.getElementById('et-nombre').value.trim();
  if (!nombre) { toast('El nombre no puede estar vacío', 'error'); return; }
  try {
    await api('PUT', `/admin/tiendas/${modalEditTiendaId}/editar`, { nombre_comercial: nombre });
    cerrarModal('modal-editar-tienda');
    toast('✅ Tienda actualizada');
    await cargarTiendas();
    await cargarSuscripciones();
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

// ════════════════════════════════════════
// MÓDULO 1: EDITAR USUARIO
// ════════════════════════════════════════
function abrirEditarUsuario(id, username, idTienda, rol) {
  modalEditUsuarioId = id;
  document.getElementById('eu-username').value = username;
  document.getElementById('eu-rol').value = rol;
  const sel = document.getElementById('eu-tienda');
  sel.innerHTML = tiendas.map(t =>
    `<option value="${t.id_tienda}" ${t.id_tienda === idTienda ? 'selected' : ''}>${esc(t.nombre_comercial)}</option>`
  ).join('');
  abrirModal('modal-editar-usuario');
}

async function confirmarEditarUsuario() {
  const id_tienda = parseInt(document.getElementById('eu-tienda').value);
  const rol = document.getElementById('eu-rol').value;
  try {
    await api('PUT', `/admin/usuarios/${modalEditUsuarioId}/editar`, { id_tienda, rol });
    cerrarModal('modal-editar-usuario');
    toast('✅ Usuario actualizado');
    cargarUsuarios();
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

// ════════════════════════════════════════
// MÓDULO 2: REPORTE POR FECHAS
// ════════════════════════════════════════
async function cargarReporte() {
  const inicio = document.getElementById('rep-inicio').value;
  const fin    = document.getElementById('rep-fin').value;
  if (!inicio || !fin) { toast('Selecciona fecha inicio y fin', 'error'); return; }
  if (inicio > fin)    { toast('La fecha inicio no puede ser mayor que la fin', 'error'); return; }
  try {
    const data = await api('GET', `/admin/ventas_reporte?fecha_inicio=${inicio}&fecha_fin=${fin}`);
    let sumVentas = 0, sumNeto = 0;
    data.tiendas.forEach(r => { sumVentas += r.total_ventas; sumNeto += r.total_neto; });
    document.getElementById('rep-totales').innerHTML = `
      <div class="card-stat">
        <div class="stat-label">Total ventas</div>
        <div class="stat-val">$${fmt(sumVentas)}</div>
      </div>
      <div class="card-stat">
        <div class="stat-label">Neto total</div>
        <div class="stat-val">$${fmt(sumNeto)}</div>
      </div>
      <div class="card-stat">
        <div class="stat-label">Período</div>
        <div class="stat-val" style="font-size:1rem;margin-top:.2rem;">${inicio} → ${fin}</div>
      </div>
    `;
    document.getElementById('rep-tiendas').innerHTML = data.tiendas.map(r => `
      <div class="tienda-venta-card">
        <div class="tvc-nombre">
          <span class="pill ${r.activa ? 'pill-ok' : 'pill-off'}">${r.activa ? 'activa' : 'inactiva'}</span>
          ${esc(r.nombre_comercial)}
        </div>
        <div class="tvc-grid">
          <div class="tvc-item"><div class="tvc-label">Ventas</div><div class="tvc-val verde">$${fmt(r.total_ventas)}</div></div>
          <div class="tvc-item"><div class="tvc-label">Retiros</div><div class="tvc-val rojo">$${fmt(r.total_retiros)}</div></div>
          <div class="tvc-item"><div class="tvc-label">Neto</div><div class="tvc-val">$${fmt(r.total_neto)}</div></div>
          <div class="tvc-item"><div class="tvc-label">Turnos</div><div class="tvc-val">${r.total_turnos}</div></div>
        </div>
      </div>
    `).join('');
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

// ════════════════════════════════════════
// MÓDULO 3: SUSCRIPCIONES
// ════════════════════════════════════════
async function cargarSuscripciones() {
  try {
    const rows = await api('GET', '/admin/tiendas');
    const detalle = await Promise.all(
      rows.map(t => api('GET', `/admin/tiendas/${t.id_tienda}/suscripcion`).catch(() => null))
    );
    document.getElementById('tbl-suscripciones').innerHTML = `
      <div class="tbl-wrap">
        <table>
          <thead>
            <tr>
              <th>Tienda</th>
              <th>Estado</th>
              <th>Día corte</th>
              <th>Mensualidad</th>
              <th>Acción</th>
            </tr>
          </thead>
          <tbody>
            ${detalle.filter(Boolean).map(s => `
              <tr>
                <td><strong>${esc(s.nombre_comercial)}</strong></td>
                <td><span class="pill ${s.estado_pago === 'AL_DIA' ? 'pill-ok' : 'pill-off'}">${s.estado_pago === 'AL_DIA' ? 'Al día' : 'Atrasado'}</span></td>
                <td style="color:var(--muted)">Día ${s.dia_corte}</td>
                <td style="color:var(--accent)">$${fmt(s.monto_mensual)}</td>
                <td><button class="btn-tbl btn-reset" onclick="abrirEditarSuscripcion(${s.id_tienda}, ${s.dia_corte}, ${s.monto_mensual}, '${s.estado_pago}')">✏️ Editar</button></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    `;
  } catch (e) {
    toast('Error cargando suscripciones: ' + e.message, 'error');
  }
}

let suscripcionTiendaId = null;

function abrirEditarSuscripcion(id, diaCorte, monto, estado) {
  suscripcionTiendaId = id;
  document.getElementById('sus-dia').value    = diaCorte;
  document.getElementById('sus-monto').value  = monto;
  document.getElementById('sus-estado').value = estado;
  abrirModal('modal-suscripcion');
}

async function confirmarEditarSuscripcion() {
  const dia_corte      = parseInt(document.getElementById('sus-dia').value);
  const monto_mensual  = parseFloat(document.getElementById('sus-monto').value);
  const estado_pago    = document.getElementById('sus-estado').value;
  if (isNaN(dia_corte) || dia_corte < 1 || dia_corte > 31) { toast('Día de corte debe ser entre 1 y 31', 'error'); return; }
  if (isNaN(monto_mensual) || monto_mensual < 0) { toast('Monto inválido', 'error'); return; }
  try {
    await api('PUT', `/admin/tiendas/${suscripcionTiendaId}/suscripcion`, { dia_corte, monto_mensual, estado_pago });
    cerrarModal('modal-suscripcion');
    toast('✅ Suscripción actualizada');
    cargarSuscripciones();
  } catch (e) {
    toast('Error: ' + e.message, 'error');
  }
}

// ════════════════════════════════════════
// MÓDULO 4: INVENTARIO (MODO DIOS)
// ════════════════════════════════════════
async function verInventarioTienda(idTienda) {
  document.getElementById('modal-inv-tienda-nombre').textContent = '📦 Cargando inventario...';
  document.getElementById('modal-inv-tbody').innerHTML = '<tr><td colspan="4" style="text-align:center;color:var(--muted);padding:1.5rem;">Cargando...</td></tr>';
  abrirModal('modal-inventario');
  try {
    const data = await api('GET', `/admin/tienda/${idTienda}/inventario`);
    document.getElementById('modal-inv-tienda-nombre').textContent = `📦 Inventario — ${data.nombre_comercial} (${data.total_productos} productos)`;
    document.getElementById('modal-inv-tbody').innerHTML = data.productos.map(p => {
      const stockBajo = p.stock_actual <= p.stock_minimo;
      return `<tr>
        <td>
          <strong>${esc(p.nombre_producto)}</strong>
          <span style="font-family:var(--mono);font-size:.7rem;color:var(--muted);margin-left:.4rem;">${esc(p.unidad_medida || 'pieza')}</span>
        </td>
        <td style="font-family:var(--mono);color:var(--muted);font-size:.75rem;">${esc(p.codigo_barras || '—')}</td>
        <td style="color:var(--accent);">$${fmt(p.precio_sugerido)}</td>
        <td style="color:${stockBajo ? 'var(--accent2)' : 'var(--text)'};font-weight:${stockBajo ? '700' : '400'};">${p.stock_actual}</td>
      </tr>`;
    }).join('');
  } catch (e) {
    document.getElementById('modal-inv-tienda-nombre').textContent = '📦 Inventario';
    document.getElementById('modal-inv-tbody').innerHTML = `<tr><td colspan="4" style="color:var(--accent2);text-align:center;padding:1rem;">Error: ${esc(e.message)}</td></tr>`;
  }
}

// ── Utils ────────────────────────────────────────────────────
function fmt(n) { return Number(n || 0).toFixed(2).replace(/\B(?=(\d{3})+(?!\d))/g, ','); }
function esc(s) {
  return String(s || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
}

// Cerrar modal con clic en overlay
document.querySelectorAll('.modal-overlay').forEach(m => {
  m.addEventListener('click', e => { if (e.target === m) m.classList.remove('visible'); });
});

// Auto-login condicionado estrictamente a los 2 días
document.addEventListener('DOMContentLoaded', () => {
  const expira = localStorage.getItem('caja_rapida_admin_expira');

  if (TOKEN && expira && Date.now() < parseInt(expira)) {
    document.getElementById('login-screen').style.display = 'none';
    document.getElementById('app-shell').style.display = 'block';
    iniciarApp();
  } else {
    logout();
  }
});