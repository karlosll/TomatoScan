"""
Traducción de los nombres de clase al español (capa de presentación).

Los modelos y `class_names.json` trabajan SIEMPRE en inglés: ese es el
contrato (el orden alfabético de las 5 clases define el softmax de salida)
y así se guardan en la BD para la auditoría del informe. Aquí solo se
traduce lo que ve el usuario final; nunca al revés.

Punto único de verdad: si se agrega o renombra una clase, se cambia aquí
y se refleja en toda la web (plantillas + vistas) sin tocar nada más.
"""

NOMBRES_ES = {
    "Bacterial Spot": "Mancha bacteriana",
    "Early Blight": "Tizón temprano",
    "Healthy": "Hoja sana",
    "Late Blight": "Tizón tardío",
    "Yellow Leaf Curl Virus": "Virus del rizado amarillo",
}

# Etiqueta de presentación cuando la confianza del ensemble no alcanza el
# umbral (settings.UMBRAL_CONFIANZA): el diagnóstico se reporta como
# desconocido y las métricas visibles se muestran en cero. No es una clase
# del contrato: nunca entra a class_names.json ni al softmax.
CLASE_DESCONOCIDA = "Desconocido"


def traducir_clase(nombre_en: str) -> str:
    """Devuelve el nombre en español; si no está mapeado, deja el original."""
    return NOMBRES_ES.get(nombre_en, nombre_en)
