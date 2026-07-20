async function cargarReporteProductos() {
    const dias = document.getElementById("select-dias-reporte").value;
    const lista = document.getElementById("lista-reporte-productos");
    lista.innerHTML = "<p class='text-center text-muted mt-3'>Cargando...</p>";
    try {
        const res = await fetch(`${API_URL}/reporte_productos?dias=${dias}`);
        const productos = await res.json();
        if (!productos || productos.length === 0) {
            lista.innerHTML = "<p class='text-center text-muted mt-3'>Sin ventas en este periodo.</p>";
            return;
        }
        lista.innerHTML = productos.map((p, idx) => `
            <div class="list-group-item d-flex justify-content-between align-items-center">
                <div>
                    <span class="fw-bold text-secondary">#${idx + 1}</span>
                    <span class="ms-2">${esc(p.producto)}</span>
                </div>
                <div class="text-end">
                    <div class="fw-bold">${parseFloat(p.unidades_vendidas).toFixed(0)} und.</div>
                    <small class="text-muted">$${parseFloat(p.total_vendido).toFixed(2)}</small>
                </div>
            </div>
        `).join("");
    } catch (e) {
        lista.innerHTML = "<p class='text-danger text-center mt-3'>Error al cargar el reporte.</p>";
    }
}