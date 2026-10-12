"""
Registro de modelos (ML).

Carga los 4 modelos .keras UNA sola vez por proceso y expone:
- predecir(imagen_pil) -> resultados por modelo + ensemble ponderado por F1.

Contrato del equipo (definido en el notebook de entrenamiento):
- Entrada: imagen RGB 224x224x3, píxeles crudos [0-255] (float32).
- Cada modelo normaliza POR DENTRO (capa Rescaling / preprocess horneado).
- Salida: softmax de 5 posiciones en el orden fijo de CLASS_NAMES.

Si algún modelo NO horneó su normalización, se declara en la BD
(campo `preprocesamiento`) y aquí se aplica el preprocess_input
correspondiente antes de inferir (plan B).
"""
import json
import logging
import threading
import time
from pathlib import Path

import numpy as np
from django.conf import settings
from PIL import Image

logger = logging.getLogger(__name__)

IMG_SIZE = 224  # del contrato del equipo


def _aplicar_preprocesamiento(lote: np.ndarray, tipo: str) -> np.ndarray:
    """Aplica preprocesamiento externo solo si el modelo lo requiere (plan B)."""
    if tipo == "crudo":
        return lote  # el modelo normaliza por dentro (contrato)

    # Imports locales: solo se pagan si algún modelo se desvió del contrato
    if tipo == "vgg16":
        from tensorflow.keras.applications.vgg16 import preprocess_input
    elif tipo == "resnet50":
        from tensorflow.keras.applications.resnet50 import preprocess_input
    elif tipo == "mobilenet_v2":
        from tensorflow.keras.applications.mobilenet_v2 import preprocess_input
    elif tipo == "efficientnet":
        from tensorflow.keras.applications.efficientnet import preprocess_input
    else:
        raise ValueError(f"Preprocesamiento desconocido: {tipo}")
    return preprocess_input(lote.copy())


class RegistroModelos:
    """Singleton por proceso. Carga perezosa y thread-safe de los modelos."""

    _instancia = None
    _lock = threading.Lock()

    def __init__(self):
        self._modelos = {}        # nombre -> tf.keras.Model
        self._metadatos = {}      # nombre -> {"peso": f1, "preprocesamiento": str}
        self._class_names = None
        self._cargado = False

    @classmethod
    def instancia(cls) -> "RegistroModelos":
        with cls._lock:
            if cls._instancia is None:
                cls._instancia = cls()
            return cls._instancia

    # ------------------------------------------------------------------
    # Carga
    # ------------------------------------------------------------------
    def _cargar(self):
        """Carga class_names.json y todos los modelos activos de la BD."""
        if self._cargado:
            return
        with self._lock:
            if self._cargado:  # doble verificación por si otro hilo cargó
                return

            import tensorflow as tf  # import pesado: diferido hasta aquí
            from diagnostico.models import ModeloEntrenado

            modelos_dir = Path(settings.MODELOS_DIR)

            with open(modelos_dir / "class_names.json", encoding="utf-8") as f:
                self._class_names = json.load(f)

            activos = ModeloEntrenado.objects.filter(activo=True)
            if not activos.exists():
                raise RuntimeError(
                    "No hay modelos activos registrados. Carga los .keras y "
                    "regístralos con: python manage.py registrar_modelos"
                )

            for registro in activos:
                ruta = modelos_dir / registro.archivo
                if not ruta.exists():
                    raise RuntimeError(
                        f"El modelo '{registro.nombre}' está registrado pero su "
                        f"archivo no existe: {ruta}. Copia el .keras a esa carpeta "
                        f"y vuelve a correr: python manage.py registrar_modelos"
                    )
                logger.info("Cargando modelo %s desde %s", registro.nombre, ruta)
                modelo = tf.keras.models.load_model(ruta, compile=False)

                # Verificación del contrato: salida (None, 5)
                n_salidas = modelo.output_shape[-1]
                if n_salidas != len(self._class_names):
                    raise RuntimeError(
                        f"El modelo '{registro.nombre}' tiene {n_salidas} salidas "
                        f"pero el contrato define {len(self._class_names)} clases."
                    )

                self._modelos[registro.nombre] = modelo
                self._metadatos[registro.nombre] = {
                    "peso": registro.f1_macro,
                    "preprocesamiento": registro.preprocesamiento,
                }

            self._cargado = True
            logger.info("Registro listo: %s", list(self._modelos))

    # ------------------------------------------------------------------
    # Inferencia
    # ------------------------------------------------------------------
    @staticmethod
    def _preparar_lote(imagen: Image.Image) -> np.ndarray:
        """PIL -> lote (1, 224, 224, 3) float32 con píxeles crudos [0-255]."""
        if imagen.mode in ("RGBA", "LA", "PA") or (
            imagen.mode == "P" and "transparency" in imagen.info
        ):
            # PNG con transparencia: aplanar sobre fondo blanco; convert("RGB")
            # directo lo dejaría negro y sesgaría la predicción.
            imagen = imagen.convert("RGBA")
            fondo = Image.new("RGBA", imagen.size, (255, 255, 255, 255))
            imagen = Image.alpha_composite(fondo, imagen)
        imagen = imagen.convert("RGB").resize((IMG_SIZE, IMG_SIZE), Image.BILINEAR)
        arreglo = np.asarray(imagen, dtype=np.float32)
        return np.expand_dims(arreglo, axis=0)

    def predecir(self, imagen: Image.Image) -> dict:
        """
        Ejecuta todos los modelos activos y el ensemble.

        Retorna:
        {
          "clase": str, "confianza": float,
          "probabilidades_ensemble": [float x5],
          "por_modelo": {nombre: {"clase": str, "probabilidades": [...]}},
          "modelos_usados": [...],
          "tiempo_ms": int,
          "class_names": [...],
        }
        """
        self._cargar()
        inicio = time.perf_counter()

        lote_crudo = self._preparar_lote(imagen)

        por_modelo = {}
        suma_ponderada = np.zeros(len(self._class_names), dtype=np.float64)
        suma_pesos = 0.0

        for nombre, modelo in self._modelos.items():
            meta = self._metadatos[nombre]
            lote = _aplicar_preprocesamiento(lote_crudo, meta["preprocesamiento"])
            probs = modelo.predict(lote, verbose=0)[0].astype(np.float64)

            por_modelo[nombre] = {
                "clase": self._class_names[int(probs.argmax())],
                "probabilidades": [round(float(p), 6) for p in probs],
            }
            suma_ponderada += meta["peso"] * probs
            suma_pesos += meta["peso"]

        # Soft voting ponderado por F1 macro
        ensemble = suma_ponderada / suma_pesos
        idx = int(ensemble.argmax())
        tiempo_ms = int((time.perf_counter() - inicio) * 1000)

        return {
            "clase": self._class_names[idx],
            "confianza": round(float(ensemble[idx]), 6),
            "probabilidades_ensemble": [round(float(p), 6) for p in ensemble],
            "por_modelo": por_modelo,
            "modelos_usados": list(self._modelos),
            "tiempo_ms": tiempo_ms,
            "class_names": self._class_names,
        }
