"""
Vistas web (HTML) del sistema de diagnóstico.

Páginas:
- /            -> formulario de subida
- /resultado/<id>/ -> diagnóstico completo con desglose por modelo
- /historial/  -> listado de predicciones anteriores
"""
import logging

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from .forms import RegistroUsuarioForm
from .models import ModeloEntrenado, Prediccion
from .services import ImagenInvalida, ejecutar_prediccion

logger = logging.getLogger(__name__)


def registro(request):
    """
    Alta pública de usuarios. Tras registrarse, inicia sesión automáticamente
    y va directo al formulario de diagnóstico. Si ya tiene sesión, lo redirige.
    """
    if request.user.is_authenticated:
        return redirect(settings.LOGIN_REDIRECT_URL)

    if request.method == "POST":
        form = RegistroUsuarioForm(request.POST)
        if form.is_valid():
            usuario = form.save()
            login(request, usuario)
            messages.success(request, f"¡Bienvenido, {usuario.username}! Tu cuenta fue creada.")
            return redirect(settings.LOGIN_REDIRECT_URL)
    else:
        form = RegistroUsuarioForm()

    return render(request, "diagnostico/registro.html", {"form": form})


def home(request):
    """Página de inicio pública: presenta el sistema e invita a iniciar sesión."""
    modelos = list(ModeloEntrenado.objects.filter(activo=True))
    mejor_f1 = max((m.f1_macro for m in modelos), default=0)

    # Barras de la sección "Varios modelos, un veredicto": F1 macro real de
    # cada CNN, ordenado de mayor a menor. La barra del ensemble se muestra a
    # la altura del mejor modelo (cota honesta: combina los votos ponderados y
    # rinde al menos como su mejor integrante; no inventamos un F1 medido).
    barras_modelos = [
        {"arquitectura": m.arquitectura, "pct": round(m.f1_macro * 100, 1)}
        for m in sorted(modelos, key=lambda m: m.f1_macro, reverse=True)
    ]

    return render(request, "diagnostico/home.html", {
        "total_modelos": len(modelos),
        "mejor_f1_pct": round(mejor_f1 * 100, 1),
        "total_predicciones": Prediccion.objects.count(),
        "barras_modelos": barras_modelos,
    })


@login_required
def subir_imagen(request):
    """Página principal: formulario para subir la foto de la hoja."""
    if request.method == "POST":
        try:
            prediccion = ejecutar_prediccion(request.FILES.get("imagen"))
        except ImagenInvalida as e:
            messages.error(request, str(e))
        except Exception:
            logger.exception("Error durante la inferencia")
            messages.error(request, "Error interno al ejecutar los modelos. Intenta de nuevo.")
        else:
            return redirect("web-resultado", pk=prediccion.pk)

    modelos = ModeloEntrenado.objects.filter(activo=True)
    return render(request, "diagnostico/subir.html", {"modelos": modelos})


@login_required
def ver_resultado(request, pk):
    """
    Muestra el diagnóstico en detalle:
    - veredicto del ensemble (clase + distribución de las 5 clases),
    - cómo analizó CADA CNN (su distribución completa, no solo su voto),
    - la matriz del promedio ponderado (qué aportó cada modelo al ensemble).
    """
    prediccion = get_object_or_404(Prediccion, pk=pk)

    import json
    from pathlib import Path

    from django.conf import settings

    with open(Path(settings.MODELOS_DIR) / "class_names.json", encoding="utf-8") as f:
        class_names = json.load(f)

    def alpha(prob):
        """Intensidad del sombreado tipo mapa de calor (celdas de la matriz)."""
        return round(prob * 0.6, 3)

    # Ensemble en orden de clase (para la matriz) y ordenado por % (para las
    # barras). Se usan las propiedades *_visibles: si la predicción no superó
    # el umbral, todas las métricas mostradas van en cero.
    ensemble_ordenado = [
        {"clase": c, "pct": round(p * 100, 1), "prob": p, "alpha": alpha(p)}
        for c, p in zip(class_names, prediccion.probabilidades_ensemble_visibles)
    ]
    filas_ensemble = [
        (d["clase"], d["pct"])
        for d in sorted(ensemble_ordenado, key=lambda d: d["prob"], reverse=True)
    ]

    # Pesos actuales de los modelos que participaron (F1 macro normalizado).
    # Es la ponderación vigente del ensemble; si cambian los F1, cambia el peso.
    modelos_bd = {
        m.nombre: m
        for m in ModeloEntrenado.objects.filter(nombre__in=prediccion.modelos_usados)
    }
    suma_f1 = sum(m.f1_macro for m in modelos_bd.values()) or 1.0

    # Análisis por modelo: distribución completa de las 5 clases + su peso.
    analisis_modelos = []
    for nombre, datos in prediccion.probabilidades_por_modelo_visibles.items():
        m = modelos_bd.get(nombre)
        f1 = m.f1_macro if m else 0.0
        probs = datos["probabilidades"]
        distribucion = [
            {
                "clase": clase,
                "pct": round(prob * 100, 1),
                "prob": prob,
                "alpha": alpha(prob),
                "es_top": clase == datos["clase"],
            }
            for clase, prob in zip(class_names, probs)
        ]
        analisis_modelos.append({
            "nombre": nombre,
            "arquitectura": m.arquitectura if m else nombre,
            "autor": m.autor if m else "",
            "f1": round(f1, 4),
            "peso_pct": round(f1 / suma_f1 * 100, 1),
            "clase_top": datos["clase"],
            "confianza_top": round(max(probs) * 100, 1) if probs else 0,
            "coincide": prediccion.es_confiable and datos["clase"] == prediccion.clase_predicha,
            "distribucion": distribucion,
        })

    # Ordenar de mayor a menor peso para leer la jerarquía del comité
    analisis_modelos.sort(key=lambda a: a["f1"], reverse=True)

    return render(request, "diagnostico/resultado.html", {
        "p": prediccion,
        "class_names": class_names,
        "filas_ensemble": filas_ensemble,
        "ensemble_ordenado": ensemble_ordenado,
        "analisis_modelos": analisis_modelos,
        "confianza_pct": round(prediccion.confianza_visible * 100, 1),
        "umbral_pct": round(settings.UMBRAL_CONFIANZA * 100, 1),
    })


def _filtrar_predicciones(request, base=None):
    """
    Aplica los filtros del historial (enfermedad, confianza, fechas) a un
    queryset. Compartido por la vista `historial` y el reporte PDF para que
    ambos muestren exactamente el mismo conjunto.

    Retorna (queryset_filtrado, nivel_confianza, desde, hasta).
    """
    qs = Prediccion.objects.all() if base is None else base

    enfermedades = request.GET.getlist("enfermedad")
    if enfermedades:
        qs = qs.filter(clase_predicha__in=enfermedades)

    nivel = request.GET.get("confianza", "")
    if nivel == "alto":
        qs = qs.filter(confianza__gt=0.8)
    elif nivel == "medio":
        qs = qs.filter(confianza__gte=0.5, confianza__lte=0.8)
    elif nivel == "bajo":
        qs = qs.filter(confianza__lt=0.5)

    desde = request.GET.get("desde", "")
    hasta = request.GET.get("hasta", "")
    if desde:
        qs = qs.filter(creado_en__date__gte=desde)
    if hasta:
        qs = qs.filter(creado_en__date__lte=hasta)

    return qs, nivel, desde, hasta


def _descripcion_filtros(request, nivel, desde, hasta):
    """Texto legible de los filtros aplicados, para el subtítulo del PDF."""
    from .nombres import traducir_clase

    partes = []
    enfermedades = request.GET.getlist("enfermedad")
    if enfermedades:
        partes.append("Enfermedad: " + ", ".join(traducir_clase(c) for c in enfermedades))
    etiquetas = {"alto": "Alta (>80%)", "medio": "Media (50-80%)", "bajo": "Baja (<50%)"}
    if nivel in etiquetas:
        partes.append("Confianza: " + etiquetas[nivel])
    if desde:
        partes.append(f"Desde: {desde}")
    if hasta:
        partes.append(f"Hasta: {hasta}")
    return " · ".join(partes) if partes else "Todos los diagnósticos"


@login_required
def historial(request):
    """
    Galería paginada de diagnósticos con filtros: por enfermedad (multi),
    por nivel de confianza y por rango de fechas. Los conteos por enfermedad
    se calculan sobre TODO el historial (para el panel de filtros).
    """
    from django.db.models import Count

    from .nombres import NOMBRES_ES, traducir_clase

    base = Prediccion.objects.all()

    # Conteos por enfermedad (sin filtrar) para el panel lateral
    conteos = dict(base.values_list("clase_predicha").annotate(n=Count("id")))
    filtro_enfermedades = request.GET.getlist("enfermedad")
    filtros_enfermedad = [
        {
            "valor": clase,
            "nombre_es": traducir_clase(clase),
            "conteo": conteos.get(clase, 0),
            "activo": clase in filtro_enfermedades,
        }
        for clase in NOMBRES_ES  # orden del contrato
    ]

    # Aplicar filtros a la consulta (mismo helper que usa el reporte PDF)
    qs, nivel, desde, hasta = _filtrar_predicciones(request, base)

    paginador = Paginator(qs, 8)
    pagina = paginador.get_page(request.GET.get("pagina"))

    # Enriquecer cada tarjeta: estado (badge) + modelo principal + mini-barras
    for pred in pagina.object_list:
        if pred.es_confiable:
            pred.estado, pred.estado_css = "Confiable", "ok"
        elif pred.confianza >= 0.5:
            pred.estado, pred.estado_css = "No concluyente", "medio"
        else:
            pred.estado, pred.estado_css = "Inconclusivo", "bajo"

        # Modelo con mayor probabilidad individual (para el detalle al pasar
        # el mouse). Si no es confiable, no se destaca ningún modelo.
        principal, mejor = "", -1.0
        if pred.es_confiable:
            for nombre, datos in (pred.probabilidades_por_modelo or {}).items():
                m = max(datos["probabilidades"])
                if m > mejor:
                    principal, mejor = nombre, m
        pred.modelo_principal = principal or "—"

        # Mini-distribución del ensemble para el detalle al pasar el mouse
        # (en cero si el diagnóstico fue no confiable / desconocido)
        pred.barras_mini = [
            {"clase_es": traducir_clase(clase), "pct": round(prob * 100, 1)}
            for clase, prob in zip(NOMBRES_ES, pred.probabilidades_ensemble_visibles or [])
        ]

    # Preservar los filtros en la paginación (querystring sin 'pagina')
    params = request.GET.copy()
    params.pop("pagina", None)
    querystring = params.urlencode()

    return render(request, "diagnostico/historial.html", {
        "pagina": pagina,
        "filtros_enfermedad": filtros_enfermedad,
        "nivel_confianza": nivel,
        "desde": desde,
        "hasta": hasta,
        "querystring": querystring,
        "total_filtrado": paginador.count,
        "vista": request.GET.get("vista", ""),
        "hay_filtros": bool(filtro_enfermedades or nivel or desde or hasta),
        "desc_filtros": _descripcion_filtros(request, nivel, desde, hasta),
    })


@login_required
@require_POST
def eliminar_prediccion(request, pk):
    """Elimina un diagnóstico del historial (registro + archivo de imagen)."""
    prediccion = get_object_or_404(Prediccion, pk=pk)
    prediccion.imagen.delete(save=False)
    prediccion.delete()
    messages.success(request, "Diagnóstico eliminado del historial.")

    # Volver a la misma página del historial desde la que se eliminó
    pagina = request.GET.get("pagina")
    url = reverse("web-historial")
    if pagina:
        url = f"{url}?pagina={pagina}"
    return redirect(url)


# ------------------------------------------------------------------
# Reportes PDF
# ------------------------------------------------------------------
def _ahora_texto():
    from django.utils import timezone
    return timezone.localtime(timezone.now()).strftime("%d/%m/%Y %H:%M")


def _respuesta_pdf(contenido, nombre, descargar=False):
    """
    Devuelve el PDF. Por defecto 'inline' (el navegador lo muestra en su visor);
    con descargar=True fuerza la descarga como archivo adjunto.
    """
    from django.http import HttpResponse

    resp = HttpResponse(contenido, content_type="application/pdf")
    disposicion = "attachment" if descargar else "inline"
    resp["Content-Disposition"] = f'{disposicion}; filename="{nombre}"'
    return resp


@login_required
@xframe_options_sameorigin  # permite la vista previa en <iframe> del mismo sitio
def reporte_diagnostico_pdf(request, pk):
    """Informe PDF individual de un diagnóstico (toda la detección)."""
    from .reportes import pdf_diagnostico

    prediccion = get_object_or_404(Prediccion, pk=pk)
    try:
        contenido = pdf_diagnostico(prediccion, _ahora_texto())
    except Exception:
        logger.exception("Error al generar el PDF del diagnóstico %s", pk)
        messages.error(request, "No se pudo generar el PDF. Intenta de nuevo.")
        return redirect("web-resultado", pk=pk)

    nombre = f"diagnostico_{prediccion.creado_en:%Y%m%d}_{str(pk)[:8]}.pdf"
    return _respuesta_pdf(contenido, nombre, descargar="descargar" in request.GET)


@login_required
@xframe_options_sameorigin  # permite la vista previa en <iframe> del mismo sitio
def reporte_historial_pdf(request):
    """Reporte PDF agregado del historial (con los filtros aplicados)."""
    from .reportes import pdf_resumen

    qs, nivel, desde, hasta = _filtrar_predicciones(request)
    predicciones = qs.order_by("-creado_en")
    subtitulo = _descripcion_filtros(request, nivel, desde, hasta)

    try:
        contenido = pdf_resumen(predicciones, _ahora_texto(), subtitulo=subtitulo)
    except Exception:
        logger.exception("Error al generar el reporte PDF del historial")
        messages.error(request, "No se pudo generar el reporte. Intenta de nuevo.")
        return redirect("web-historial")

    return _respuesta_pdf(contenido, "reporte_diagnosticos.pdf", descargar="descargar" in request.GET)
