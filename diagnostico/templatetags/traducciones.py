"""
Filtro de plantilla para mostrar los nombres de clase en español.

Uso en las plantillas:
    {% load traducciones %}
    {{ p.clase_predicha|clase_es }}
"""
from django import template

from diagnostico.nombres import traducir_clase

register = template.Library()


@register.filter(name="clase_es")
def clase_es(nombre_en):
    """Traduce un nombre de clase (inglés) al español para mostrarlo."""
    return traducir_clase(nombre_en)
