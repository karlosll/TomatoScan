"""
Comando: python manage.py registrar_modelos

Escanea las carpetas de modelos_entrenados/ (una por arquitectura),
detecta automáticamente el archivo .keras de cada una y la registra
en la base de datos usando los metadatos de su info.json.

Flujo para el equipo:
1. Cada compañero copia su .keras en la carpeta de su arquitectura.
2. Edita el info.json de esa carpeta (F1 macro real, su nombre).
3. Cualquiera ejecuta: python manage.py registrar_modelos

Las carpetas sin .keras o con f1_macro=0 se omiten sin error:
el sistema funciona con los modelos que sí estén listos.
"""
import json
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand

from diagnostico.models import ModeloEntrenado


class Command(BaseCommand):
    help = "Escanea modelos_entrenados/ y registra los modelos del equipo."

    def handle(self, *args, **options):
        raiz = Path(settings.MODELOS_DIR)
        if not raiz.exists():
            self.stderr.write(self.style.ERROR(f"No existe la carpeta {raiz}"))
            return

        carpetas = sorted(d for d in raiz.iterdir() if d.is_dir())
        if not carpetas:
            self.stderr.write(self.style.ERROR(
                "No hay carpetas de arquitecturas dentro de modelos_entrenados/."
            ))
            return

        registrados = 0
        for carpeta in carpetas:
            nombre = carpeta.name  # ej: mobilenetv2

            info_path = carpeta / "info.json"
            if not info_path.exists():
                self.stdout.write(self.style.WARNING(
                    f"  [{nombre}] Omitido: falta info.json en {carpeta}/"
                ))
                continue

            with open(info_path, encoding="utf-8") as f:
                info = json.load(f)

            keras_files = list(carpeta.glob("*.keras"))
            if not keras_files:
                self.stdout.write(self.style.WARNING(
                    f"  [{nombre}] Omitido: aún no hay archivo .keras en {carpeta}/"
                ))
                continue
            if len(keras_files) > 1:
                self.stdout.write(self.style.WARNING(
                    f"  [{nombre}] Omitido: hay {len(keras_files)} archivos .keras; "
                    f"deja solo uno en {carpeta}/"
                ))
                continue

            f1 = float(info.get("f1_macro", 0))
            if f1 <= 0:
                self.stdout.write(self.style.WARNING(
                    f"  [{nombre}] Omitido: f1_macro sin definir en info.json "
                    f"(pon el F1 real del Paso 12 del notebook)."
                ))
                continue

            # Ruta relativa a MODELOS_DIR, ej: "mobilenetv2/mobilenetv2_tomato.keras"
            archivo_rel = f"{nombre}/{keras_files[0].name}"

            objeto, creado = ModeloEntrenado.objects.update_or_create(
                nombre=nombre,
                defaults={
                    "arquitectura": info.get("arquitectura", nombre),
                    "autor": info.get("autor", ""),
                    "archivo": archivo_rel,
                    "f1_macro": f1,
                    "preprocesamiento": info.get("preprocesamiento", "crudo"),
                    "activo": True,
                },
            )
            accion = "Creado" if creado else "Actualizado"
            self.stdout.write(self.style.SUCCESS(f"  [{nombre}] {accion}: {objeto}"))
            registrados += 1

        self.stdout.write("")
        if registrados:
            self.stdout.write(self.style.SUCCESS(
                f"Listo: {registrados} modelo(s) activo(s). "
                "Reinicia el servidor si estaba corriendo."
            ))
        else:
            self.stderr.write(self.style.ERROR(
                "Ningún modelo quedó registrado. Revisa las advertencias de arriba."
            ))
