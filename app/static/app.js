// Lisozima humana para demostración
const EJEMPLO = "KVFERCELARTLKRLGMDGYRGISLANWMCLAKWESGYNTRATNYNAGDRSTDYGIFQINSRYWCNDGKTPGAVNACHLSCSALLQDNIADAVACAKRVVRDPQGIRAWVAWRNRCQNRDVRQYVQGCGV";


const $ = (id) => document.getElementById(id);
const caja = $("secuencia");

function longitudLimpia(texto) {
    return texto.split(/\r?\n/).filter(l => !l.startsWith(">")).join("").replace(/\s+/g, "").length;
}
function actualizarContador() {
    const n = longitudLimpia(caja.value);
    $("contador").textContent = n ? n + " aminoácidos" : "";
}
caja.addEventListener("input", actualizarContador);

$("btn-ejemplo").addEventListener("click", () => { caja.value = EJEMPLO; actualizarContador(); });
$("btn-limpiar").addEventListener("click", () => {
    caja.value = ""; actualizarContador();
    $("resultado").classList.add("oculto"); $("error").classList.add("oculto");
});

function mostrarError(mensaje) {
    $("resultado").classList.add("oculto");
    $("error").textContent = mensaje;
    $("error").classList.remove("oculto");
}

function celda(fila, contenido) {
    const td = document.createElement("td");
    if (contenido instanceof Node) td.appendChild(contenido); else td.textContent = contenido ?? "—";
    fila.appendChild(td);
}

function pintar(r) {
    $("error").classList.add("oculto");
    $("clase").textContent = r.clase_nombre;

    const conf = $("confianza");
    conf.className = "etiqueta";
    if (r.confianza) { conf.textContent = "confianza " + r.confianza; conf.classList.add(r.confianza); }
    else { conf.textContent = ""; }

    $("detalle").textContent = "Distancia coseno al vecino más cercano: " + r.distancia_vecino_mas_cercano.toFixed(4) +
        " · longitud: " + r.longitud + " aminoácidos";

    const avisos = $("avisos"); avisos.replaceChildren();
    r.avisos.forEach(a => { const d = document.createElement("div"); d.className = "aviso"; d.textContent = a; avisos.appendChild(d); });
    if (r.confianza === "baja") {
        const d = document.createElement("div"); d.className = "aviso";
        d.textContent = "No hay proteínas muy parecidas en la base de datos: la predicción es poco fiable.";
        avisos.appendChild(d);
    }

    const cuerpo = $("vecinos"); cuerpo.replaceChildren();
    r.vecinos.forEach(v => {
        const tr = document.createElement("tr");
        if (v.posicion === 1) tr.className = "primero";
        celda(tr, v.posicion);
        const a = document.createElement("a");
        a.href = v.enlace_uniprot; a.target = "_blank"; a.rel = "noopener noreferrer"; a.textContent = v.id;
        celda(tr, a);
        celda(tr, v.nombre); celda(tr, v.organismo); celda(tr, v.ec);
        celda(tr, v.clase_nombre); celda(tr, v.distancia.toFixed(4));
        cuerpo.appendChild(tr);
    });
    $("resultado").classList.remove("oculto");
}

$("btn-predecir").addEventListener("click", async () => {
    const texto = caja.value.trim();
    if (!texto) { mostrarError("Escribe o pega una secuencia primero."); return; }
    const boton = $("btn-predecir");
    boton.disabled = true; boton.textContent = "Clasificando…";
    try {
        const resp = await fetch("/predict", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ secuencia: texto }),
        });
        const datos = await resp.json();
        if (!resp.ok) { mostrarError(typeof datos.detail === "string" ? datos.detail : "Petición no válida."); return; }
        pintar(datos);
    } catch (e) {
        mostrarError("No se pudo conectar con el servidor. ¿Está uvicorn en marcha?");
    } finally {
        boton.disabled = false; boton.textContent = "Clasificar";
    }
});

fetch("/info").then(r => r.json()).then(m => {
    const partes = ["Modelo: kNN con " + m.representacion + ", k=" + m.k_vecinos];
    if (m.f1_macro_test != null) partes.push("F1 macro en test: " + m.f1_macro_test);
    if (m.n_proteinas_referencia) partes.push(m.n_proteinas_referencia + " proteínas de referencia");
    $("pie").textContent = partes.join(" · ");
}).catch(() => { });