"""
Configuración del proyecto — Sistema de diagnóstico de hojas de tomate.

Base de datos:
- Por defecto usa SQLite (db.sqlite3) para que el proyecto arranque sin
  configurar nada. Ideal para probarlo por primera vez.
- Para usar PostgreSQL (recomendado para la entrega), define DATABASE_URL
  en el archivo .env:
      DATABASE_URL=postgres://postgres:tu_clave@localhost:5432/tomate_db
"""
from pathlib import Path

import environ

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env()
# Lee el archivo .env si existe (no es obligatorio para la primera prueba)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env(
    "SECRET_KEY",
    default="dev-cambia-esta-clave-en-produccion",
)
DEBUG = env.bool("DEBUG", default=True)
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])

INSTALLED_APPS = [
    # El admin de Django está desactivado: el acceso al sistema se hace
    # con el login propio en /login/ (ver diagnostico/urls.py).
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Terceros
    "rest_framework",
    # Apps propias
    "diagnostico",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------
# Base de datos
# SQLite por defecto (cero configuración); PostgreSQL si defines
# DATABASE_URL en .env
# ---------------------------------------------------------------
DATABASES = {
    "default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}"),
}

# ---------------------------------------------------------------
# Autenticación: login propio (sin admin de Django)
# ---------------------------------------------------------------
LOGIN_URL = "web-login"
LOGIN_REDIRECT_URL = "web-subir"
LOGOUT_REDIRECT_URL = "web-home"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "es-ec"
TIME_ZONE = "America/Guayaquil"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"

# ---------------------------------------------------------------
# Imágenes subidas por los usuarios
# ---------------------------------------------------------------
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---------------------------------------------------------------
# Carpeta raíz de los modelos del equipo (una subcarpeta por
# arquitectura) + class_names.json
# ---------------------------------------------------------------
MODELOS_DIR = BASE_DIR / "modelos_entrenados"

# ---------------------------------------------------------------
# Criterios de confiabilidad del diagnóstico. Un softmax de 5 clases
# siempre reparte el 100%, así que una imagen fuera de distribución
# (no es hoja de tomate, baja calidad) puede "ganar" una clase igual.
# La predicción solo es confiable si cumple AMBOS:
# - UMBRAL_CONFIANZA (0-1): probabilidad mínima de la clase ganadora
#   del ensemble. El promedio ponderado de 4 softmax aplana la
#   confianza (hojas reales rondan 0.55-0.85), por eso es bajo.
# - UMBRAL_CONSENSO (0-1): fracción mínima de modelos cuya clase top
#   coincide con la del ensemble. 1.0 = unanimidad: en los datos
#   reales las hojas legítimas dan 4/4 y las imágenes fuera de
#   distribución (p. ej. un tomate) dividen los votos (≤3/4).
# Ajustables vía .env: UMBRAL_CONFIANZA=0.55, UMBRAL_CONSENSO=1.0
# ---------------------------------------------------------------
UMBRAL_CONFIANZA = env.float("UMBRAL_CONFIANZA", default=0.55)
UMBRAL_CONSENSO = env.float("UMBRAL_CONSENSO", default=1.0)

# Ajustes por clase (opcional): sobreescriben los umbrales globales
# cuando la clase ganadora del ensemble es la indicada. Se usa para
# clases mal balanceadas en el dataset de entrenamiento, donde todas
# las arquitecturas rinden peor: exigirles la misma confianza y
# unanimidad que al resto las volvería casi indetectables.
# Claves en inglés (contrato de class_names.json).
UMBRALES_POR_CLASE = {
    # Clase minoritaria en el entrenamiento de todas las arquitecturas:
    # confianza más baja y basta con 3 de 4 modelos de acuerdo.
    "Yellow Leaf Curl Virus": {"confianza": 0.45, "consenso": 0.75},
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
    # La API también exige usuario autenticado: sesión (navegador) o
    # básica (curl: -u usuario:clave).
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.SessionAuthentication",
        "rest_framework.authentication.BasicAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "diagnostico": {"handlers": ["console"], "level": "INFO"},
    },
}
