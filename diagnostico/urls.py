"""Rutas de la app: login + páginas web + API."""
from django.contrib.auth import views as auth_views
from django.urls import path

from . import views_web
from .views import (
    CrearPrediccionView,
    DetallePrediccionView,
    ListaModelosView,
    ListaPrediccionesView,
)

urlpatterns = [
    # --- Autenticación (reemplaza al admin de Django) ---
    path("login/", auth_views.LoginView.as_view(
        template_name="diagnostico/login.html",
        redirect_authenticated_user=True,
    ), name="web-login"),
    path("logout/", auth_views.LogoutView.as_view(), name="web-logout"),
    path("registro/", views_web.registro, name="web-registro"),

    # --- Páginas web (lo que ve el usuario) ---
    path("", views_web.home, name="web-home"),
    path("diagnostico/", views_web.subir_imagen, name="web-subir"),
    path("resultado/<uuid:pk>/", views_web.ver_resultado, name="web-resultado"),
    path("resultado/<uuid:pk>/pdf/", views_web.reporte_diagnostico_pdf, name="web-resultado-pdf"),
    path("historial/", views_web.historial, name="web-historial"),
    path("historial/reporte.pdf", views_web.reporte_historial_pdf, name="web-historial-pdf"),
    path("historial/eliminar/<uuid:pk>/", views_web.eliminar_prediccion, name="web-eliminar"),

    # --- API JSON (opcional: integraciones, pruebas con curl, informe) ---
    path("api/predicciones/", CrearPrediccionView.as_view(), name="crear-prediccion"),
    path("api/predicciones/historial/", ListaPrediccionesView.as_view(), name="lista-predicciones"),
    path("api/predicciones/<uuid:pk>/", DetallePrediccionView.as_view(), name="detalle-prediccion"),
    path("api/modelos/", ListaModelosView.as_view(), name="lista-modelos"),
]
