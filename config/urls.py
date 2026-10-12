"""config/urls.py — rutas raíz del proyecto."""
from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

# El admin de Django está desactivado; el acceso es con el login propio
# definido en diagnostico/urls.py (/login/).
urlpatterns = [
    path("", include("diagnostico.urls")),   # web en la raíz + /api/ dentro
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
