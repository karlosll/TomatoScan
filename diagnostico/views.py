"""
API JSON del sistema de diagnóstico (Django REST Framework).

La lógica de inferencia vive en services.py y es compartida con las
vistas web. Esta API queda disponible para pruebas con curl, para el
informe y para futuras integraciones.
"""
import logging

from rest_framework import status
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ModeloEntrenado, Prediccion
from .serializers import (
    ModeloEntrenadoSerializer,
    PrediccionDetalleSerializer,
    PrediccionListaSerializer,
)
from .services import ImagenInvalida, ejecutar_prediccion

logger = logging.getLogger(__name__)


class CrearPrediccionView(APIView):
    """Recibe una imagen (multipart) y devuelve el diagnóstico completo."""

    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        try:
            prediccion = ejecutar_prediccion(request.FILES.get("imagen"))
        except ImagenInvalida as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception:
            logger.exception("Error durante la inferencia")
            return Response(
                {"error": "Error interno al ejecutar los modelos."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        serializer = PrediccionDetalleSerializer(prediccion, context={"request": request})
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ListaPrediccionesView(ListAPIView):
    queryset = Prediccion.objects.all()
    serializer_class = PrediccionListaSerializer


class DetallePrediccionView(RetrieveAPIView):
    queryset = Prediccion.objects.all()
    serializer_class = PrediccionDetalleSerializer


class ListaModelosView(ListAPIView):
    queryset = ModeloEntrenado.objects.filter(activo=True)
    serializer_class = ModeloEntrenadoSerializer
