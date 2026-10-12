# CLAUDE.md — Guía del proyecto para Claude Code

## Qué es este proyecto

App web Django para diagnosticar 5 enfermedades en hojas de tomate. El
usuario sube una foto; el sistema la evalúa con varias CNN entrenadas por
un equipo universitario (una arquitectura por integrante) y combina las
salidas en un ensemble. Es un proyecto académico (UNEMI) con datos reales.

Stack: **Python 3.11+ · Django 5 · DRF · TensorFlow/Keras · PostgreSQL
(SQLite como fallback de desarrollo) · Pillow · django-environ · ReportLab
(reportes PDF)**.

## Invariantes — NO romper esto

Estas reglas sostienen todo el sistema. Cualquier cambio debe respetarlas:

1. **El contrato de los modelos.** Todo `.keras` del equipo:
   - recibe un tensor `(N, 224, 224, 3)` float32 con píxeles crudos `[0-255]`,
   - normaliza POR DENTRO (capa Rescaling/preprocess horneada),
   - devuelve softmax `(N, 5)` en el orden EXACTO de
     `modelos_entrenados/class_names.json` (alfabético):
     `["Bacterial Spot", "Early Blight", "Healthy", "Late Blight", "Yellow Leaf Curl Virus"]`.
   - Nunca reordenar `class_names.json` ni asumir otro orden en el código.

2. **Separación de capas.**
   - `diagnostico/ml/registro.py` = TODO lo de TensorFlow (carga, inferencia,
     ensemble). Nada de TF fuera de este archivo.
   - `diagnostico/services.py` = orquestación (validar archivo → inferir →
     guardar `Prediccion`). Es la ÚNICA puerta de entrada a la inferencia.
   - `views_web.py` (HTML) y `views.py` (API DRF) son capas finas que llaman
     a `services.ejecutar_prediccion()`. Nueva funcionalidad de predicción =
     tocar services/registro, no duplicar lógica en vistas.

3. **Imports perezosos de TensorFlow.** `import tensorflow` vive DENTRO de
   `RegistroModelos._cargar()` y de `_aplicar_preprocesamiento()`. Esto es
   deliberado: permite que `manage.py migrate/check/registrar_modelos` y los
   tests corran sin TF instalado o sin cargar 600 MB. No mover esos imports
   al nivel de módulo.

4. **Singleton del registro.** `RegistroModelos.instancia()` carga los
   modelos UNA vez por proceso (lazy, thread-safe con doble verificación).
   No crear instancias nuevas por request. En producción se corre
   `gunicorn -w 1 --threads N` justamente para tener una sola copia en RAM.

5. **Los modelos se descubren por carpetas.** `modelos_entrenados/<slug>/`
   contiene un único `.keras` + un `info.json`
   (`arquitectura, autor, f1_macro, preprocesamiento`). El comando
   `python manage.py registrar_modelos` escanea y sincroniza con la tabla
   `ModeloEntrenado`. Para agregar una arquitectura nueva: crear carpeta +
   info.json, no tocar código (salvo que necesite un preprocess nuevo, ver
   punto 6).

6. **Preprocesamiento plan B.** `ModeloEntrenado.preprocesamiento="crudo"`
   significa "el modelo normaliza solo" (contrato). Los demás valores
   (`vgg16`, `resnet50`, `mobilenet_v2`, `efficientnet`) aplican el
   `preprocess_input` de Keras correspondiente en
   `registro._aplicar_preprocesamiento()`. Para soportar otra arquitectura
   externa: agregar el choice en `models.ModeloEntrenado.Preprocesamiento`,
   la rama en `_aplicar_preprocesamiento()`, y una migración.

7. **Auditoría en BD.** `Prediccion` guarda SIEMPRE
   `probabilidades_por_modelo` (dict nombre→{clase, probabilidades[5]}) y
   `probabilidades_ensemble` (lista de 5). No "optimizar" quitando estos
   campos: son la base del análisis del informe académico.

8. **Ensemble = soft voting ponderado por F1 macro** (campo
   `ModeloEntrenado.f1_macro`, medido en el test set común). Suma ponderada
   de softmax / suma de pesos. Si se cambia la estrategia, hacerlo en
   `RegistroModelos.predecir()` y documentarlo aquí.

## Mapa de archivos

| Archivo | Responsabilidad |
|---|---|
| `config/settings.py` | `MODELOS_DIR`, `MEDIA_ROOT`, BD vía `env.db("DATABASE_URL", default=sqlite)` |
| `config/urls.py` | raíz → `diagnostico.urls` |
| `diagnostico/models.py` | `ModeloEntrenado` (registro/pesos), `Prediccion` (UUID pk, ImageField, JSONFields) |
| `diagnostico/ml/registro.py` | Singleton `RegistroModelos`: carga, preproceso, inferencia, ensemble |
| `diagnostico/services.py` | `ejecutar_prediccion(archivo) -> Prediccion` + excepción `ImagenInvalida` |
| `diagnostico/reportes.py` | Generación de PDF con ReportLab: `pdf_diagnostico` (individual, toda la detección) y `pdf_resumen` (agregado del historial con estadísticas). Traduce clases con `nombres.py` |
| `diagnostico/nombres.py` | `NOMBRES_ES` (traducción de clases al español, capa de presentación) + filtro `clase_es` en `templatetags/traducciones.py` |
| `diagnostico/forms.py` | `RegistroUsuarioForm` (alta pública de usuarios) |
| `diagnostico/views_web.py` | `home` (pública), `subir_imagen`, `ver_resultado`, `historial` (render de templates) |
| `diagnostico/views.py` | API DRF equivalente (POST /api/predicciones/, listados) |
| `diagnostico/urls.py` | home pública en `/`; login en `/login/` y `/logout/`; web en `/diagnostico/`, `/resultado/<uuid>/`, `/historial/`; API bajo `/api/` |
| `diagnostico/templates/diagnostico/` | `base.html` (estilos inline, sin framework CSS), `home` (landing autocontenida), `login`, `subir`, `resultado`, `historial` |
| `diagnostico/management/commands/registrar_modelos.py` | escaneo de carpetas → BD |

## Convenciones del código

- Idioma: código, comentarios, docstrings, mensajes y templates en
  **español** (nombres de campos y funciones incluidos: `ejecutar_prediccion`,
  `clase_predicha`). Mantenerlo así.
- Sin frameworks CSS externos; los estilos viven en `base.html`.
- **Autenticación**: el admin de Django está desactivado (fuera de
  `INSTALLED_APPS` y de `config/urls.py`). El acceso es con login propio
  (`LoginView`/`LogoutView` de `django.contrib.auth` + plantilla
  `diagnostico/login.html`). Vistas web con `@login_required`; la API exige
  `IsAuthenticated` (sesión o HTTP Basic). Usuarios: registro público en
  `/registro/` (`views_web.registro` + `RegistroUsuarioForm` en `forms.py`,
  extiende `UserCreationForm`; tras registrarse hace login automático y
  redirige a `LOGIN_REDIRECT_URL`). El `createsuperuser` por terminal sigue
  disponible para el primer admin.
- **Criterios de confiabilidad**: un diagnóstico es confiable solo si cumple
  AMBOS (ver `services.evaluar_confiabilidad`): confianza del ensemble ≥
  `settings.UMBRAL_CONFIANZA` (0.55; el promedio de 4 softmax aplana la
  confianza) Y fracción de modelos que coinciden con la clase del ensemble ≥
  `settings.UMBRAL_CONSENSO` (1.0 = unanimidad; las imágenes fuera de
  distribución dividen los votos). Calibrado con datos reales de la BD:
  hojas legítimas dan 4/4 con confianza 0.58-0.83; un tomate dio 3/4.
  `settings.UMBRALES_POR_CLASE` sobreescribe ambos umbrales por clase
  (hoy: "Yellow Leaf Curl Virus" → confianza 0.45, consenso 0.75, porque
  esa clase está mal balanceada en el entrenamiento de todas las
  arquitecturas). Si no, se
  PRESENTA como "Desconocido" con todas las métricas en cero (web, historial,
  PDF y API). La BD guarda los valores reales (invariante 7).
  Toda capa de presentación debe usar las propiedades `Prediccion.clase_visible`,
  `confianza_visible`, `probabilidades_ensemble_visibles` y
  `probabilidades_por_modelo_visibles`, nunca los campos crudos.
- Errores de usuario → `messages.error` en web, `Response 400` en API.
  Errores internos → `logger.exception` + mensaje genérico (nunca traceback
  al usuario).
- Migraciones: siempre `python manage.py makemigrations diagnostico` tras
  tocar `models.py`; las migraciones se versionan.

## Comandos útiles

```bash
python manage.py migrate                # aplicar migraciones
python manage.py registrar_modelos     # sincronizar carpetas → BD
python manage.py runserver             # desarrollo
python manage.py check                 # sanity check (corre sin TF)
gunicorn config.wsgi -w 1 --threads 4  # producción (1 worker = 1 copia de modelos)
```

## Estado actual y pendientes

- ✅ `mobilenetv2/` completo (autor Carlos, F1 macro 0.8491, preprocesamiento
  crudo — normalización horneada con `Rescaling(1/127.5, -1)`).
- ✅ `vgg16/` (Hernan Sarango, F1 macro 0.80) y `resnet50/` (Aithor Oña,
  F1 macro 0.92): sus bases son pesos ImageNet CONGELADOS (verificado bit
  a bit contra `keras.applications`), sin normalización horneada → van con
  `preprocesamiento: "vgg16"` / `"resnet50"` (plan B).
- ✅ `xception/` (Jesus Sanchez, F1 macro 0.87; arquitectura extra al plan
  original). Normaliza por dentro (`x/127.5 - 1` horneado en el grafo) →
  `preprocesamiento: "crudo"`, no necesitó código nuevo.
- ⏳ `efficientnet/`: solo `info.json` plantilla (`f1_macro: 0` → el
  comando la omite). Cuando llegue el `.keras`, se llena y se re-registra.
- `modelos_entrenados/_respaldos/`: archivos redundantes que enviaron los
  compañeros (pesos sueltos `.weights.h5`, arquitecturas `.json`, un `.h5`
  legacy). No los usa el sistema; el comando ignora la carpeta (avisa
  "falta info.json", es normal). Nota: los `.keras.zip` que enviaron ERAN
  los `.keras` (un `.keras` es un zip por dentro); solo se renombraron.
- No hay tests automatizados aún. Si se agregan: mockear
  `RegistroModelos.predecir` en tests de vistas (no cargar TF), y probar
  el ensemble con arrays sintéticos.

## Trampas conocidas (no re-descubrirlas)

- La PRIMERA predicción tras arrancar tarda 20–60 s (carga perezosa de TF y
  modelos). Es diseño, no bug.
- `archivo.seek(0)` en `services.py` es necesario: PIL consume el stream al
  validar y sin el seek la imagen se guarda vacía/corrupta.
- TFLite (`.tflite`) NO se usa en este sistema (era para una app Flutter
  descartada). Solo `.keras`.
- TensorFlow fijado a `2.20.*` porque los modelos se entrenaron con esa
  versión; subirla puede romper la deserialización de los `.keras`.
- El locale es `es-ec`: Django renderiza los floats con coma decimal en los
  templates. Todo número interpolado dentro de CSS/JS inline
  (`width:{{ pct }}%`, `rgba(...,{{ alpha }})`, `data-ancho`) DEBE llevar
  `|unlocalize` (`{% load l10n %}`), o el navegador ignora la regla y las
  barras salen al 100%.
- `val/test` del dataset nunca se barajaron y el orden de clases es
  alfabético: si algo predice "siempre la misma clase", sospechar primero
  del preprocesamiento (modelo sin normalización horneada registrado como
  "crudo").
