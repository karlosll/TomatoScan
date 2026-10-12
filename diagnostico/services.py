"""
Servicio de predicción compartido.

Tanto la API (views.py) como las vistas web (views_web.py) llaman a esta
función, así la lógica de inferencia + guardado vive en un solo lugar.
"""
from django.conf import settings
from PIL import Image, UnidentifiedImageError

from .ml.registro import RegistroModelos
from .models import Prediccion

TAMANO_MAXIMO_MB = 10


class ImagenInvalida(Exception):
    """El archivo subido no es una imagen utilizable."""


def evaluar_confiabilidad(resultado: dict) -> bool:
    """
    Decide si un resultado del ensemble es confiable. Debe cumplir AMBOS:
    - la clase ganadora alcanza el umbral de confianza, y
    - la fracción de modelos cuya clase top coincide con la del ensemble
      alcanza el umbral de consenso (las imágenes fuera de distribución
      suelen dividir los votos de las CNN).

    Los umbrales globales (settings.UMBRAL_CONFIANZA / UMBRAL_CONSENSO)
    pueden sobreescribirse por clase en settings.UMBRALES_POR_CLASE, para
    clases mal balanceadas en el entrenamiento.
    """
    ajuste = settings.UMBRALES_POR_CLASE.get(resultado["clase"], {})
    umbral_confianza = ajuste.get("confianza", settings.UMBRAL_CONFIANZA)
    umbral_consenso = ajuste.get("consenso", settings.UMBRAL_CONSENSO)

    if resultado["confianza"] < umbral_confianza:
        return False
    por_modelo = resultado["por_modelo"]
    coincidencias = sum(
        1 for datos in por_modelo.values() if datos["clase"] == resultado["clase"]
    )
    consenso = coincidencias / len(por_modelo) if por_modelo else 0.0
    return consenso >= umbral_consenso


def ejecutar_prediccion(archivo) -> Prediccion:
    """
    Valida el archivo, corre los modelos activos + ensemble y guarda
    la Prediccion en la base de datos. Lanza ImagenInvalida si el
    archivo no sirve.
    """
    if archivo is None:
        raise ImagenInvalida("No se recibió ninguna imagen.")
    if archivo.size > TAMANO_MAXIMO_MB * 1024 * 1024:
        raise ImagenInvalida(f"La imagen supera el máximo de {TAMANO_MAXIMO_MB} MB.")

    try:
        imagen = Image.open(archivo)
        imagen.load()
    except (UnidentifiedImageError, OSError) as exc:
        raise ImagenInvalida("El archivo no es una imagen válida.") from exc

    resultado = RegistroModelos.instancia().predecir(imagen)

    # Capa de decisión sobre el resultado ya calculado (confianza mínima +
    # consenso entre modelos). No altera el ensemble ni la auditoría: si no
    # es confiable, la presentación lo reporta como "Desconocido" con las
    # métricas en cero, pero la BD guarda los valores reales.
    es_confiable = evaluar_confiabilidad(resultado)

    archivo.seek(0)  # PIL consumió el stream; rebobinar antes de guardar
    return Prediccion.objects.create(
        imagen=archivo,
        clase_predicha=resultado["clase"],
        confianza=resultado["confianza"],
        es_confiable=es_confiable,
        probabilidades_ensemble=resultado["probabilidades_ensemble"],
        probabilidades_por_modelo=resultado["por_modelo"],
        modelos_usados=resultado["modelos_usados"],
        tiempo_inferencia_ms=resultado["tiempo_ms"],
    )
