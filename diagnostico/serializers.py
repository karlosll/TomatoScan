"""Serializadores de la API de diagnóstico.

La API expone el diagnóstico "visible": si la predicción no superó el
umbral de confianza (es_confiable=False), la clase se reporta como
"Desconocido" y todas las métricas van en cero, igual que en la web.
Los valores reales siguen guardados en la BD para la auditoría.
"""
from rest_framework import serializers

from .models import ModeloEntrenado, Prediccion


class ModeloEntrenadoSerializer(serializers.ModelSerializer):
    class Meta:
        model = ModeloEntrenado
        fields = ["nombre", "arquitectura", "autor", "f1_macro", "preprocesamiento"]


class PrediccionListaSerializer(serializers.ModelSerializer):
    """Versión ligera para el historial (sin los vectores completos)."""

    clase_predicha = serializers.CharField(source="clase_visible", read_only=True)
    confianza = serializers.FloatField(source="confianza_visible", read_only=True)

    class Meta:
        model = Prediccion
        fields = ["id", "imagen", "clase_predicha", "confianza", "es_confiable",
                  "tiempo_inferencia_ms", "creado_en"]


class PrediccionDetalleSerializer(serializers.ModelSerializer):
    """Versión completa: incluye probabilidades del ensemble y por modelo."""

    clase_predicha = serializers.CharField(source="clase_visible", read_only=True)
    confianza = serializers.FloatField(source="confianza_visible", read_only=True)
    probabilidades_ensemble = serializers.ListField(
        source="probabilidades_ensemble_visibles", read_only=True)
    probabilidades_por_modelo = serializers.DictField(
        source="probabilidades_por_modelo_visibles", read_only=True)

    class Meta:
        model = Prediccion
        fields = ["id", "imagen", "clase_predicha", "confianza", "es_confiable",
                  "probabilidades_ensemble", "probabilidades_por_modelo",
                  "modelos_usados", "tiempo_inferencia_ms", "creado_en"]
