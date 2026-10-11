import json
from contextlib import asynccontextmanager
from pathlib import Path

import joblib
import pandas as pd
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

# --------------------------------------------------------------------------- rutas
BASE = Path(__file__).resolve().parent.parent
MODELOS = BASE / "models"
INDEX_HTML = Path(__file__).resolve().parent / "static" / "index.html"

# --------------------------------------------------------------------------- configuración
AMINOACIDOS = set("ACDEFGHIKLMNPQRSTVWY")
LONG_MIN_DURA = 3 
LONG_MAX_DURA = 5000
LONG_MIN_ENTRENAMIENTO = 50
LONG_MAX_ENTRENAMIENTO = 1000
N_VECINOS_MOSTRAR = 5

NOMBRES_CLASE_DEFECTO = {
    "1": "1 · Oxidorreductasas", "2": "2 · Transferasas", "3": "3 · Hidrolasas", "4": "4 · Liasas",
    "5": "5 · Isomerasas", "6": "6 · Ligasas", "7": "7 · Translocasas",
}

estado = {}   # modelo, referencia y metadatos, cargados al arrancar


@asynccontextmanager
async def lifespan(app: FastAPI):
    for archivo in ("modelo_knn.joblib", "referencia.csv", "modelo_knn_meta.json"):
        if not (MODELOS / archivo).exists():
            raise RuntimeError(
                f"Falta {MODELOS / archivo}. Ejecuta antes el notebook 02_modelo.ipynb hasta el final."
            )
    estado["modelo"] = joblib.load(MODELOS / "modelo_knn.joblib")
    estado["referencia"] = pd.read_csv(MODELOS / "referencia.csv")
    estado["meta"] = json.loads((MODELOS / "modelo_knn_meta.json").read_text(encoding="utf-8"))
    yield
    estado.clear()


app = FastAPI(title="Clasificador de enzimas por secuencia", version="1.0", lifespan=lifespan)


# --------------------------------------------------------------------------- modelos de datos
class Peticion(BaseModel):
    secuencia: str


class Vecino(BaseModel):
    posicion: int
    id: str
    enlace_uniprot: str
    nombre: str | None
    organismo: str | None
    ec: str | None
    clase: int
    clase_nombre: str
    distancia: float


class Respuesta(BaseModel):
    clase: int
    clase_nombre: str
    distancia_vecino_mas_cercano: float
    confianza: str | None
    longitud: int
    avisos: list[str]
    vecinos: list[Vecino]


# --------------------------------------------------------------------------- funciones
def limpiar_secuencia(texto: str) -> str:
    """Admite secuencia suelta o formato FASTA (quita la línea '>' y los espacios)."""
    lineas = [l for l in texto.strip().splitlines() if not l.startswith(">")]
    return "".join("".join(lineas).split()).upper()


def nombre_clase(clase: int) -> str:
    nombres = estado["meta"].get("clases", {})
    return nombres.get(str(clase), NOMBRES_CLASE_DEFECTO.get(str(clase), str(clase)))


def nivel_confianza(distancia: float) -> str | None:
    umbrales = estado["meta"].get("umbrales_distancia") or {}
    alta, media = umbrales.get("alta"), umbrales.get("media")
    if alta is None and media is None:
        return None
    if alta is not None and distancia <= alta:
        return "alta"
    if media is not None and distancia <= media:
        return "media"
    return "baja"


# --------------------------------------------------------------------------- endpoints
@app.get("/", include_in_schema=False)
def inicio():
    return FileResponse(INDEX_HTML)


@app.get("/info")
def info():
    """Datos del modelo cargado (para mostrar en la interfaz)."""
    return estado["meta"]


@app.post("/predict", response_model=Respuesta)
def predecir(peticion: Peticion):
    secuencia = limpiar_secuencia(peticion.secuencia)

    if len(secuencia) < LONG_MIN_DURA:
        raise HTTPException(422, "La secuencia es demasiado corta o está vacía.")
    if len(secuencia) > LONG_MAX_DURA:
        raise HTTPException(422, f"La secuencia es demasiado larga (máximo {LONG_MAX_DURA} aminoácidos).")
    invalidos = sorted(set(secuencia) - AMINOACIDOS)
    if invalidos:
        raise HTTPException(
            422,
            "La secuencia contiene caracteres que no son aminoácidos estándar: "
            + ", ".join(invalidos)
            + ". Solo se admiten las letras ACDEFGHIKLMNPQRSTVWY.",
        )

    avisos = []
    if not (LONG_MIN_ENTRENAMIENTO <= len(secuencia) <= LONG_MAX_ENTRENAMIENTO):
        avisos.append(
            f"La longitud ({len(secuencia)}) está fuera del rango con el que se entrenó el modelo "
            f"({LONG_MIN_ENTRENAMIENTO}-{LONG_MAX_ENTRENAMIENTO}); la predicción puede ser poco fiable."
        )

    modelo = estado["modelo"]
    referencia = estado["referencia"]
    knn = modelo.named_steps["knn"]

    # La secuencia se convierte en frecuencias y se buscan los vecinos más cercanos
    caracteristicas = modelo[:-1].transform([secuencia])
    distancias, indices = knn.kneighbors(caracteristicas, n_neighbors=N_VECINOS_MOSTRAR)
    clase_predicha = int(knn.predict(caracteristicas)[0])
    distancia_1 = float(distancias[0][0])

    col_id = "Entry" if "Entry" in referencia.columns else "Entry Name"
    vecinos = []
    for pos, (d, i) in enumerate(zip(distancias[0], indices[0]), start=1):
        fila = referencia.iloc[int(i)]
        ident = str(fila[col_id])
        vecinos.append(
            Vecino(
                posicion=pos,
                id=ident,
                enlace_uniprot=f"https://www.uniprot.org/uniprotkb/{ident}/entry",
                nombre=None if pd.isna(fila.get("Protein names")) else str(fila.get("Protein names")),
                organismo=None if pd.isna(fila.get("Organism")) else str(fila.get("Organism")),
                ec=None if pd.isna(fila.get("EC number")) else str(fila.get("EC number")),
                clase=int(fila["clase"]),
                clase_nombre=nombre_clase(int(fila["clase"])),
                distancia=round(float(d), 4),
            )
        )

    return Respuesta(
        clase=clase_predicha,
        clase_nombre=nombre_clase(clase_predicha),
        distancia_vecino_mas_cercano=round(distancia_1, 4),
        confianza=nivel_confianza(distancia_1),
        longitud=len(secuencia),
        avisos=avisos,
        vecinos=vecinos,
    )