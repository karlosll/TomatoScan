"""
Modelos de base de datos del sistema de diagnóstico.

Dos tablas principales:
- ModeloEntrenado: registro de cada arquitectura del equipo (archivo .keras,
  F1 macro obtenido en test, tipo de preprocesamiento). Sirve como fuente de
  verdad para el registro de modelos en memoria y para los pesos del ensemble.
- Prediccion: cada diagnóstico realizado, con la imagen, el resultado del
  ensemble y las probabilidades completas de cada modelo (JSONB).
"""
import uuid

from django.db import models


class ModeloEntrenado(models.Model):
    """Una arquitectura entrenada por un miembro del equipo."""

    class Preprocesamiento(models.TextChoices):
        # 'crudo' = la normalización está horneada dentro del modelo (contrato).
        # Las demás opciones son el plan B por si un compañero no la horneó.
        CRUDO = "crudo", "Imagen cruda [0-255] (normalización interna)"
        MOBILENET_V2 = "mobilenet_v2", "preprocess_input de MobileNetV2"
        VGG16 = "vgg16", "preprocess_input de VGG16"
        RESNET50 = "resnet50", "preprocess_input de ResNet50"
        EFFICIENTNET = "efficientnet", "preprocess_input de EfficientNet"

    nombre = models.SlugField(
        max_length=50, unique=True,
        help_text="Identificador corto, ej: mobilenetv2",
    )
    arquitectura = models.CharField(max_length=100)
    autor = models.CharField(max_length=100, blank=True)
    archivo = models.CharField(
        max_length=255,
        help_text="Ruta del .keras relativa a settings.MODELOS_DIR, "
                  "ej: mobilenetv2_tomato.keras",
    )
    preprocesamiento = models.CharField(
        max_length=20,
        choices=Preprocesamiento.choices,
        default=Preprocesamiento.CRUDO,
    )
    f1_macro = models.FloatField(
        help_text="F1 macro en el conjunto de test; se usa como peso del ensemble.",
    )
    activo = models.BooleanField(
        default=True,
        help_text="Si está desactivado, no participa en las predicciones.",
    )
    creado_en = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "modelo entrenado"
        verbose_name_plural = "modelos entrenados"
        ordering = ["nombre"]

    def __str__(self):
        return f"{self.nombre} ({self.arquitectura}, F1={self.f1_macro:.3f})"


class Prediccion(models.Model):
    """Un diagnóstico sobre una imagen de hoja de tomate."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    imagen = models.ImageField(upload_to="hojas/%Y/%m/")
    creado_en = models.DateTimeField(auto_now_add=True)

    # Resultado del ensemble
    clase_predicha = models.CharField(max_length=50)
    confianza = models.FloatField(help_text="Probabilidad de la clase ganadora (0-1).")
    es_confiable = models.BooleanField(
        default=True,
        help_text="False si la confianza no superó settings.UMBRAL_CONFIANZA "
                  "(posible imagen fuera de distribución).",
    )

    # Vector softmax del ensemble, en el orden del contrato (5 posiciones)
    probabilidades_ensemble = models.JSONField()

    # Probabilidades de cada modelo individual:
    # {"mobilenetv2": [0.1, ...], "vgg16": [...], ...}
    probabilidades_por_modelo = models.JSONField()

    # Metadatos útiles para el informe
    modelos_usados = models.JSONField(
        help_text="Lista de nombres de modelos que participaron.",
    )
    tiempo_inferencia_ms = models.PositiveIntegerField()

    class Meta:
        verbose_name = "predicción"
        verbose_name_plural = "predicciones"
        ordering = ["-creado_en"]
        indexes = [
            models.Index(fields=["clase_predicha"]),
            models.Index(fields=["creado_en"]),
        ]

    def __str__(self):
        return f"{self.clase_predicha} ({self.confianza:.1%}) — {self.creado_en:%Y-%m-%d %H:%M}"

    # ------------------------------------------------------------------
    # Propiedades de presentación: si la predicción no superó el umbral,
    # el diagnóstico se reporta como "Desconocido" y las métricas visibles
    # van en cero. Los campos reales quedan intactos en la BD (auditoría
    # del informe académico); estas propiedades son lo ÚNICO que deben usar
    # las vistas, la API y los reportes para mostrar resultados.
    # ------------------------------------------------------------------
    @property
    def clase_visible(self):
        from .nombres import CLASE_DESCONOCIDA
        return self.clase_predicha if self.es_confiable else CLASE_DESCONOCIDA

    @property
    def confianza_visible(self):
        return self.confianza if self.es_confiable else 0.0

    @property
    def probabilidades_ensemble_visibles(self):
        if self.es_confiable:
            return self.probabilidades_ensemble
        return [0.0] * len(self.probabilidades_ensemble or [])

    @property
    def probabilidades_por_modelo_visibles(self):
        if self.es_confiable:
            return self.probabilidades_por_modelo
        from .nombres import CLASE_DESCONOCIDA
        return {
            nombre: {
                "clase": CLASE_DESCONOCIDA,
                "probabilidades": [0.0] * len(datos.get("probabilidades", [])),
            }
            for nombre, datos in (self.probabilidades_por_modelo or {}).items()
        }
