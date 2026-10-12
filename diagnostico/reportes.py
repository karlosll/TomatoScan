"""
Generación de reportes PDF (ReportLab, Python puro).

Dos reportes:
- pdf_diagnostico(prediccion): informe individual con TODA la información de
  la detección (imagen, veredicto del ensemble, análisis por CNN, matriz del
  promedio ponderado e interpretación para la toma de decisiones).
- pdf_resumen(predicciones, ...): informe agregado del historial filtrado con
  estadísticas (distribución de enfermedades, confianza, consenso) y hallazgos
  accionables.

Los nombres de clase se traducen al español con diagnostico.nombres; el sistema
sigue almacenando en inglés (contrato de los modelos).
"""
import io

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import (
    HRFlowable, Image as RLImage, Paragraph, SimpleDocTemplate, Spacer,
    Table, TableStyle,
)

from .models import ModeloEntrenado
from .nombres import CLASE_DESCONOCIDA, NOMBRES_ES, traducir_clase

# --- Paleta coherente con la web ---
VERDE = colors.HexColor("#2d6a4f")
VERDE_OSC = colors.HexColor("#12341f")
VERDE_CLARO = colors.HexColor("#d8f3dc")
GRIS = colors.HexColor("#6c757d")
AMBAR = colors.HexColor("#d99a00")
ROJO = colors.HexColor("#b02a37")
BORDE = colors.HexColor("#dee2e6")

# Guía de manejo por enfermedad (apoyo a la decisión; no reemplaza a un agrónomo)
GUIA_MANEJO = {
    "Bacterial Spot": "Enfermedad bacteriana favorecida por alta humedad. Retirar hojas "
        "afectadas, evitar el riego por aspersión y considerar productos a base de cobre. "
        "Desinfectar herramientas para no propagarla.",
    "Early Blight": "Hongo (Alternaria). Retirar residuos vegetales, mejorar la ventilación, "
        "rotar cultivos y aplicar fungicidas preventivos. Afecta primero a las hojas viejas.",
    "Healthy": "La hoja no muestra signos de enfermedad. Mantener el monitoreo periódico y "
        "las buenas prácticas de riego y fertilización.",
    "Late Blight": "Hongo agresivo (Phytophthora infestans), muy rápido en clima fresco y "
        "húmedo. Actuar de inmediato: eliminar plantas afectadas y aplicar fungicidas "
        "específicos. Puede arrasar el cultivo en días.",
    "Yellow Leaf Curl Virus": "Virus transmitido por la mosca blanca; no tiene cura. Controlar "
        "el vector, eliminar las plantas infectadas y usar variedades resistentes para "
        "próximas siembras.",
}


# ------------------------------------------------------------------
# Estilos
# ------------------------------------------------------------------
def _estilos():
    e = getSampleStyleSheet()
    e.add(ParagraphStyle("TituloDoc", parent=e["Title"], textColor=VERDE_OSC, fontSize=20, spaceAfter=2))
    e.add(ParagraphStyle("Sub", parent=e["Normal"], textColor=GRIS, fontSize=9.5, spaceAfter=2))
    e.add(ParagraphStyle("H2", parent=e["Heading2"], textColor=VERDE_OSC, fontSize=13, spaceBefore=12, spaceAfter=6))
    e.add(ParagraphStyle("Cuerpo", parent=e["Normal"], fontSize=10, leading=15))
    e.add(ParagraphStyle("CuerpoP", parent=e["Normal"], fontSize=10, leading=15, spaceAfter=6))
    e.add(ParagraphStyle("Peque", parent=e["Normal"], fontSize=8.5, textColor=GRIS, leading=12))
    e.add(ParagraphStyle("Veredicto", parent=e["Normal"], fontSize=22, textColor=VERDE_OSC, leading=24))
    e.add(ParagraphStyle("CeldaCen", parent=e["Normal"], fontSize=9, alignment=TA_CENTER))
    return e


def _encabezado(story, est, titulo, subtitulo, generado):
    story.append(Paragraph("🍅 TomatoScan — Diagnóstico de hojas de tomate", est["Sub"]))
    story.append(Paragraph(titulo, est["TituloDoc"]))
    if subtitulo:
        story.append(Paragraph(subtitulo, est["Sub"]))
    story.append(Paragraph(f"Generado: {generado}", est["Sub"]))
    story.append(Spacer(1, 4))
    story.append(HRFlowable(width="100%", thickness=1.2, color=VERDE))
    story.append(Spacer(1, 8))


def _barra(pct, ancho=52 * mm, alto=5.2 * mm, color=VERDE):
    """Barra de progreso como mini-tabla (relleno proporcional a pct)."""
    lleno = min(max(ancho * pct / 100.0, 0.4), ancho)
    vacio = max(ancho - lleno, 0.1)
    t = Table([["", ""]], colWidths=[lleno, vacio], rowHeights=[alto])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (0, 0), color),
        ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#eef1f3")),
        ("LINEABOVE", (0, 0), (-1, -1), 0, colors.white),
        ("BOX", (0, 0), (-1, -1), 0, colors.white),
        ("TOPPADDING", (0, 0), (-1, -1), 0), ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
    ]))
    return t


def _sombra(prob):
    """Color de fondo tipo mapa de calor para una probabilidad [0-1]."""
    return colors.linearlyInterpolatedColor(colors.white, VERDE_CLARO, 0, 1, min(prob, 1.0))


# ------------------------------------------------------------------
# Reporte individual
# ------------------------------------------------------------------
def pdf_diagnostico(prediccion, generado) -> bytes:
    est = _estilos()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, title=f"Diagnóstico {prediccion.id}",
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
    )
    story = []
    _encabezado(story, est, "Reporte de diagnóstico",
                f"Identificador: {prediccion.id}", generado)

    # Valores "visibles": si no superó el umbral, la clase es "Desconocido"
    # y todas las métricas del reporte van en cero (la BD conserva las reales).
    clase_es = traducir_clase(prediccion.clase_visible)
    conf_pct = round(prediccion.confianza_visible * 100, 1)
    estado = ("Confiable" if prediccion.es_confiable
              else ("No concluyente" if prediccion.confianza >= 0.5 else "Inconclusivo"))
    color_estado = VERDE if prediccion.es_confiable else (AMBAR if prediccion.confianza >= 0.5 else ROJO)

    # --- Bloque veredicto: imagen + resumen ---
    izq = []
    img = _imagen(prediccion.imagen)
    if img is not None:
        izq.append(img)
    else:
        izq.append(Paragraph("(imagen no disponible)", est["Peque"]))

    der = [
        Paragraph("Diagnóstico del ensemble", est["Sub"]),
        Paragraph(clase_es, est["Veredicto"]),
        Spacer(1, 4),
        Paragraph(f"<b>Confianza:</b> {conf_pct}%", est["Cuerpo"]),
        Paragraph(f"<b>Estado:</b> <font color='#{color_estado.hexval()[2:]}'>{estado}</font>", est["Cuerpo"]),
        Paragraph(f"<b>Modelos usados:</b> {len(prediccion.modelos_usados)}", est["Cuerpo"]),
        Paragraph(f"<b>Tiempo de inferencia:</b> {prediccion.tiempo_inferencia_ms} ms", est["Cuerpo"]),
        Paragraph(f"<b>Fecha:</b> {prediccion.creado_en:%d/%m/%Y %H:%M}", est["Cuerpo"]),
    ]
    bloque = Table([[izq, der]], colWidths=[60 * mm, None])
    bloque.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (1, 0), (1, 0), 12)]))
    story.append(bloque)

    if not prediccion.es_confiable:
        story.append(Spacer(1, 6))
        story.append(Paragraph(
            "⚠ <b>Diagnóstico desconocido:</b> el resultado no superó los criterios de "
            "confiabilidad (confianza mínima y acuerdo entre los modelos). La imagen podría "
            "no ser una hoja de tomate o tener baja calidad. El resultado se reporta como "
            "Desconocido y todas las métricas se muestran en cero.",
            _recuadro_estilo(est)))

    # --- Distribución del ensemble ---
    story.append(Paragraph("Probabilidades del ensemble", est["H2"]))
    filas = [["Clase", "Probabilidad", ""]]
    ens = sorted(zip(NOMBRES_ES, prediccion.probabilidades_ensemble_visibles), key=lambda x: x[1], reverse=True)
    for clase, prob in ens:
        pct = round(prob * 100, 1)
        filas.append([traducir_clase(clase), f"{pct}%", _barra(pct)])
    t = Table(filas, colWidths=[55 * mm, 25 * mm, 58 * mm])
    t.setStyle(_estilo_tabla_base())
    story.append(t)

    # --- Análisis por modelo ---
    story.append(Paragraph("Análisis por red neuronal (CNN)", est["H2"]))
    modelos_bd = {m.nombre: m for m in ModeloEntrenado.objects.filter(nombre__in=prediccion.modelos_usados)}
    suma_f1 = sum(m.f1_macro for m in modelos_bd.values()) or 1.0

    encab = ["Modelo", "Peso", "Su predicción", "Conf."]
    coincidencias = 0
    filas_m = [encab]
    for nombre, datos in prediccion.probabilidades_por_modelo_visibles.items():
        m = modelos_bd.get(nombre)
        arq = m.arquitectura if m else nombre
        f1 = m.f1_macro if m else 0.0
        top_es = traducir_clase(datos["clase"])
        coincide = prediccion.es_confiable and datos["clase"] == prediccion.clase_predicha
        coincidencias += 1 if coincide else 0
        filas_m.append([
            arq, f"{round(f1 / suma_f1 * 100, 1)}%",
            top_es + ("  ✓" if coincide else ""),
            f"{round(max(datos['probabilidades']) * 100, 1)}%" if datos["probabilidades"] else "0%",
        ])
    t = Table(filas_m, colWidths=[40 * mm, 20 * mm, 62 * mm, 20 * mm])
    t.setStyle(_estilo_tabla_base())
    story.append(t)

    # --- Matriz del promedio ponderado ---
    story.append(Paragraph("Cómo se combinan: promedio ponderado", est["H2"]))
    story.append(Paragraph(
        "Cada modelo aporta su probabilidad por clase multiplicada por su peso (F1 macro "
        "normalizado). El sombreado indica probabilidades más altas.", est["Peque"]))
    story.append(Spacer(1, 4))
    story.append(_matriz(prediccion, modelos_bd, est))

    # --- Interpretación para la decisión ---
    story.append(Paragraph("Interpretación para la toma de decisiones", est["H2"]))
    consenso = f"{coincidencias} de {len(prediccion.probabilidades_por_modelo)} modelos coincidieron con el diagnóstico final."
    story.append(Paragraph(f"<b>Consenso:</b> {consenso}", est["CuerpoP"]))
    story.append(Paragraph(f"<b>Diagnóstico:</b> {clase_es} (confianza {conf_pct}%).", est["CuerpoP"]))
    # Para un diagnóstico Desconocido no hay entrada en la guía: se recomienda repetir la foto.
    guia = GUIA_MANEJO.get(prediccion.clase_visible, "")
    if guia:
        story.append(Paragraph(f"<b>Recomendación de manejo:</b> {guia}", est["CuerpoP"]))
    elif not prediccion.es_confiable:
        story.append(Paragraph(
            "<b>Recomendación:</b> repetir la captura con una foto clara de una sola hoja de "
            "tomate, bien iluminada y enfocada, y volver a analizarla.", est["CuerpoP"]))
    story.append(Spacer(1, 6))
    story.append(Paragraph(
        "Este informe es una herramienta de apoyo a la decisión basada en modelos de aprendizaje "
        "automático (proyecto académico UNEMI). No sustituye la evaluación de un ingeniero agrónomo.",
        est["Peque"]))

    doc.build(story)
    return buffer.getvalue()


# ------------------------------------------------------------------
# Reporte agregado (historial)
# ------------------------------------------------------------------
def pdf_resumen(predicciones, generado, subtitulo="") -> bytes:
    est = _estilos()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4, title="Reporte de diagnósticos",
        leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
    )
    story = []
    _encabezado(story, est, "Reporte de diagnósticos", subtitulo, generado)

    predicciones = list(predicciones)
    total = len(predicciones)

    if total == 0:
        story.append(Paragraph("No hay diagnósticos que coincidan con los filtros seleccionados.", est["Cuerpo"]))
        doc.build(story)
        return buffer.getvalue()

    # --- Métricas globales (valores visibles: los diagnósticos Desconocido
    # cuentan con confianza 0) ---
    confianzas = [p.confianza_visible for p in predicciones]
    conf_prom = sum(confianzas) / total
    n_confiables = sum(1 for p in predicciones if p.es_confiable)
    n_bajos = sum(1 for p in predicciones if p.confianza_visible < 0.5)

    tarjetas = [[
        _tarjeta_kpi(est, str(total), "diagnósticos"),
        _tarjeta_kpi(est, f"{round(conf_prom * 100, 1)}%", "confianza promedio"),
        _tarjeta_kpi(est, f"{round(n_confiables / total * 100)}%", "confiables"),
        _tarjeta_kpi(est, str(n_bajos), "de baja confianza"),
    ]]
    tk = Table(tarjetas, colWidths=[42 * mm] * 4)
    tk.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 6)]))
    story.append(tk)

    # --- Distribución por enfermedad ---
    story.append(Paragraph("Distribución por enfermedad", est["H2"]))
    conteos = {c: 0 for c in NOMBRES_ES}
    for p in predicciones:
        conteos[p.clase_visible] = conteos.get(p.clase_visible, 0) + 1
    orden = sorted(conteos.items(), key=lambda x: x[1], reverse=True)
    filas = [["Enfermedad", "Casos", "%", ""]]
    for clase, n in orden:
        pct = round(n / total * 100, 1)
        filas.append([traducir_clase(clase), str(n), f"{pct}%", _barra(pct)])
    t = Table(filas, colWidths=[52 * mm, 18 * mm, 18 * mm, 52 * mm])
    t.setStyle(_estilo_tabla_base())
    story.append(t)

    # --- Pesos de los modelos ---
    modelos = list(ModeloEntrenado.objects.filter(activo=True).order_by("-f1_macro"))
    if modelos:
        story.append(Paragraph("Modelos del ensemble (peso = F1 macro)", est["H2"]))
        filas = [["Arquitectura", "Autor", "F1 macro"]]
        for m in modelos:
            filas.append([m.arquitectura, m.autor or "—", f"{m.f1_macro:.3f}"])
        t = Table(filas, colWidths=[45 * mm, 60 * mm, 30 * mm])
        t.setStyle(_estilo_tabla_base())
        story.append(t)

    # --- Hallazgos accionables ---
    story.append(Paragraph("Hallazgos para la toma de decisiones", est["H2"]))
    clase_top, n_top = orden[0]
    hallazgos = [
        f"La enfermedad más frecuente es <b>{traducir_clase(clase_top)}</b> "
        f"({n_top} de {total} casos, {round(n_top / total * 100, 1)}%).",
    ]
    n_sanas = conteos.get("Healthy", 0)
    hallazgos.append(
        f"El {round(n_sanas / total * 100, 1)}% de las hojas analizadas resultaron sanas; "
        f"el {round((total - n_sanas) / total * 100, 1)}% presentó alguna enfermedad.")
    n_desconocidos = total - n_confiables
    if n_desconocidos:
        hallazgos.append(
            f"{n_desconocidos} diagnóstico(s) resultaron <b>Desconocido</b> (no superaron los "
            f"criterios de confiabilidad): revisar la calidad de esas imágenes y repetir la captura.")
    enfermas = [(c, n) for c, n in orden
                if c not in ("Healthy", CLASE_DESCONOCIDA) and n > 0]
    if enfermas:
        guia = GUIA_MANEJO.get(enfermas[0][0], "")
        if guia:
            hallazgos.append(f"Prioridad de manejo — {traducir_clase(enfermas[0][0])}: {guia}")
    for h in hallazgos:
        story.append(Paragraph("• " + h, est["CuerpoP"]))

    # --- Detalle (tabla de diagnósticos) ---
    story.append(Paragraph("Detalle de los diagnósticos", est["H2"]))
    filas = [["Fecha", "Enfermedad", "Confianza", "Estado"]]
    for p in predicciones[:60]:
        estado = ("Confiable" if p.es_confiable
                  else ("No concluyente" if p.confianza >= 0.5 else "Inconclusivo"))
        filas.append([p.creado_en.strftime("%d/%m/%Y %H:%M"),
                      traducir_clase(p.clase_visible),
                      f"{round(p.confianza_visible * 100, 1)}%", estado])
    t = Table(filas, colWidths=[38 * mm, 52 * mm, 25 * mm, 35 * mm], repeatRows=1)
    t.setStyle(_estilo_tabla_base())
    story.append(t)
    if total > 60:
        story.append(Paragraph(f"… y {total - 60} diagnóstico(s) más (mostrando los 60 más recientes).", est["Peque"]))

    story.append(Spacer(1, 8))
    story.append(Paragraph(
        "Herramienta de apoyo a la decisión (proyecto académico UNEMI). Los diagnósticos provienen "
        "de un ensemble de CNN ponderado por F1 macro; no sustituyen la evaluación de un agrónomo.",
        est["Peque"]))

    doc.build(story)
    return buffer.getvalue()


# ------------------------------------------------------------------
# Auxiliares
# ------------------------------------------------------------------
def _imagen(filefield, max_lado=55 * mm):
    try:
        ir = ImageReader(filefield.path)
        iw, ih = ir.getSize()
        escala = min(max_lado / iw, max_lado / ih)
        return RLImage(filefield.path, width=iw * escala, height=ih * escala)
    except Exception:
        return None


def _recuadro_estilo(est):
    return ParagraphStyle("Aviso", parent=est["Cuerpo"], textColor=colors.HexColor("#664d03"),
                          backColor=colors.HexColor("#fff3cd"), borderColor=colors.HexColor("#ffe69c"),
                          borderWidth=1, borderPadding=8, leading=14)


def _estilo_tabla_base():
    return TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), VERDE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f4f7f5")]),
        ("LINEBELOW", (0, 0), (-1, -1), 0.4, BORDE),
        ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
    ])


def _matriz(prediccion, modelos_bd, est):
    clases = list(NOMBRES_ES)
    encab = ["Modelo"] + [traducir_clase(c) for c in clases]
    filas = [encab]
    estilos = [
        ("BACKGROUND", (0, 0), (-1, 0), VERDE),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7.5),
        ("ALIGN", (1, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.4, BORDE),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]
    r = 1
    for nombre, datos in prediccion.probabilidades_por_modelo_visibles.items():
        m = modelos_bd.get(nombre)
        arq = m.arquitectura if m else nombre
        fila = [arq]
        for i, prob in enumerate(datos["probabilidades"]):
            fila.append(f"{round(prob * 100, 1)}%")
            estilos.append(("BACKGROUND", (i + 1, r), (i + 1, r), _sombra(prob)))
        filas.append(fila)
        r += 1
    # Fila ensemble
    fila = ["Ensemble"]
    for prob in prediccion.probabilidades_ensemble_visibles:
        fila.append(f"{round(prob * 100, 1)}%")
    filas.append(fila)
    estilos += [
        ("BACKGROUND", (0, r), (-1, r), VERDE_CLARO),
        ("FONTNAME", (0, r), (-1, r), "Helvetica-Bold"),
        ("LINEABOVE", (0, r), (-1, r), 1, VERDE),
    ]
    ancho = 36 * mm
    col = (160 * mm - ancho) / len(clases)
    t = Table(filas, colWidths=[ancho] + [col] * len(clases))
    t.setStyle(TableStyle(estilos))
    return t


def _tarjeta_kpi(est, numero, etiqueta):
    inner = Table([[Paragraph(f"<b>{numero}</b>", ParagraphStyle("kpi", fontSize=20, textColor=VERDE, alignment=TA_CENTER))],
                   [Paragraph(etiqueta, ParagraphStyle("kpiE", fontSize=8.5, textColor=GRIS, alignment=TA_CENTER))]],
                  colWidths=[38 * mm])
    inner.setStyle(TableStyle([
        ("BOX", (0, 0), (-1, -1), 0.6, BORDE),
        ("BACKGROUND", (0, 0), (-1, -1), colors.white),
        ("TOPPADDING", (0, 0), (0, 0), 8), ("BOTTOMPADDING", (0, 1), (0, 1), 8),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    return inner
