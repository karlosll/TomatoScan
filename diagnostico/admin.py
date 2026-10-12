"""
Configuración del panel de administración.

NOTA: el admin de Django está DESACTIVADO ("django.contrib.admin" no está
en INSTALLED_APPS); el acceso al sistema es con el login propio (/login/).
Este archivo se conserva por si se quiere reactivar el panel: bastaría
devolver la app a INSTALLED_APPS y su ruta a config/urls.py.
"""
from django.contrib import admin

from .models import ModeloEntrenado, Prediccion


@admin.register(ModeloEntrenado)
class ModeloEntrenadoAdmin(admin.ModelAdmin):
    list_display = ["nombre", "arquitectura", "autor", "f1_macro",
                    "preprocesamiento", "activo"]
    list_editable = ["activo"]
    list_filter = ["activo", "preprocesamiento"]


@admin.register(Prediccion)
class PrediccionAdmin(admin.ModelAdmin):
    list_display = ["id", "clase_predicha", "confianza",
                    "tiempo_inferencia_ms", "creado_en"]
    list_filter = ["clase_predicha", "creado_en"]
    readonly_fields = [f.name for f in Prediccion._meta.fields]
    date_hierarchy = "creado_en"

    def has_add_permission(self, request):
        return False  # las predicciones solo se crean por la API
