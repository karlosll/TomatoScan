# 🍅 Sistema de diagnóstico de enfermedades en hojas de tomate
### App web multi-modelo · Django + PostgreSQL + TensorFlow

Aplicación web donde el usuario sube la foto de una hoja de tomate desde el
navegador y el sistema la diagnostica ejecutando **todas las arquitecturas CNN
entrenadas por el equipo** (MobileNetV2, VGG16, ResNet50 y Xception) y
combinando sus salidas en un **ensemble por soft voting ponderado por F1 macro**.

Clases que detecta (contrato del equipo, orden fijo):
`Bacterial Spot · Early Blight · Healthy · Late Blight · Yellow Leaf Curl Virus`

---

## 1. Cómo funciona el sistema (visión general)

```
Navegador ──sube foto──▶ Django (vistas web)
                             │
                             ▼
                     services.ejecutar_prediccion()
                             │
                             ▼
                  ml/registro.py  (RegistroModelos)
                  · carga los .keras una vez por proceso
                  · misma imagen cruda 224×224 a cada modelo
                  · softmax de 5 clases por modelo
                  · ensemble = promedio ponderado por F1
                             │
                             ▼
                     PostgreSQL / SQLite
                  (imagen + resultado + vector de
                   probabilidades de CADA modelo)
```

Puntos clave del diseño:

- **Contrato del equipo.** Todos los modelos se entrenaron con el mismo
  notebook base: entrada RGB 224×224×3 con píxeles crudos [0–255],
  normalización horneada dentro del modelo, salida softmax de 5 posiciones
  en el orden de `modelos_entrenados/class_names.json`. Gracias a eso el
  backend trata a las 4 arquitecturas de forma idéntica.
- **Ensemble ponderado.** Cada vector softmax se multiplica por el F1 macro
  que ese modelo obtuvo en test, se suman y se normaliza. Un modelo mejor
  pesa más, pero ninguno decide solo.
- **Plan B de preprocesamiento.** Si un compañero NO horneó la normalización
  dentro de su modelo, basta poner `"preprocesamiento": "vgg16"` (o el que
  sea) en su `info.json` y el backend aplica el `preprocess_input` correcto
  antes de inferir.
- **Auditoría total.** Cada predicción guarda en la base de datos las
  probabilidades completas de cada modelo (JSONB), no solo la clase ganadora.
  Sirve para el informe: se puede consultar en qué imágenes discreparon los
  modelos y cómo el ensemble resolvió el empate.

## 2. Estructura del proyecto

```
sistema_tomate/
├── manage.py                     # comando principal de Django
├── requirements.txt
├── .env.ejemplo                  # plantilla de variables de entorno
├── README.md                     # este archivo
├── CLAUDE.md                     # guía para Claude Code
│
├── config/                       # configuración del proyecto
│   ├── settings.py               # BD, MEDIA, MODELOS_DIR, apps
│   ├── urls.py                   # rutas raíz (web en /, API en /api/)
│   └── wsgi.py / asgi.py
│
├── diagnostico/                  # LA app (toda la lógica vive aquí)
│   ├── models.py                 # ModeloEntrenado, Prediccion
│   ├── services.py               # ejecutar_prediccion() — lógica compartida
│   ├── views_web.py              # páginas HTML
│   ├── views.py                  # API JSON (DRF)
│   ├── serializers.py
│   ├── urls.py
│   ├── admin.py
│   ├── templates/diagnostico/    # base, subir, resultado, historial
│   ├── ml/registro.py            # carga de modelos + ensemble
│   ├── migrations/               # YA generadas (0001_initial.py)
│   └── management/commands/
│       └── registrar_modelos.py  # escanea las carpetas y registra en BD
│
└── modelos_entrenados/           # ARTEFACTOS DEL EQUIPO (uno por carpeta)
    ├── class_names.json          # orden oficial de las 5 clases
    ├── mobilenetv2/              # modelo + metadatos
    │   ├── mobilenetv2_tomato.keras
    │   └── info.json
    ├── vgg16/                    # modelo + metadatos
    ├── resnet50/                 # modelo + metadatos
    ├── xception/                 # modelo + metadatos
    └── efficientnet/             # plantilla, aún sin modelo
```

Los archivos de modelos (`.keras` y `.h5`) se gestionan con **Git LFS**. La
carpeta `modelos_entrenados/_respaldos/` no forma parte del repositorio porque
duplica artefactos y aumenta innecesariamente el tamaño de la descarga.

## 3. Instrucciones de ejecución (paso a paso, sin errores)

Probado con Python 3.11+ en Windows/Linux/macOS.

### Paso 1 — Entorno virtual y dependencias

```bash
git lfs install
git clone URL_DEL_REPOSITORIO
cd sistema_tomate

# Si el repositorio ya estaba clonado antes de instalar Git LFS:
git lfs pull

# Crear y activar entorno virtual
python -m venv venv
venv\Scripts\activate        # Windows
# source venv/bin/activate   # Linux / macOS

pip install -r requirements.txt
```

> La instalación de TensorFlow tarda varios minutos (es ~600 MB). Paciencia.

### Paso 2 — Base de datos

**Opción rápida (primera prueba):** no hagas nada. El proyecto usa SQLite
automáticamente y crea `db.sqlite3` solo.

**Opción PostgreSQL (para la entrega final):**
```bash
# 1) En pgAdmin o psql, crea la base:
#      CREATE DATABASE tomate_db;
# 2) Copia la plantilla de entorno:
cp .env.ejemplo .env         # Windows: copy .env.ejemplo .env
# 3) Edita .env y descomenta/ajusta:
#      DATABASE_URL=postgres://postgres:TU_CLAVE@localhost:5432/tomate_db
```

### Paso 3 — Migrar y registrar los modelos

```bash
python manage.py migrate
python manage.py registrar_modelos
```

Verás algo como:
```
  [mobilenetv2] Creado: mobilenetv2 (MobileNetV2, F1=0.849)
  [vgg16]       Omitido: aún no hay archivo .keras ...
  ...
Listo: 1 modelo(s) activo(s).
```
Los "Omitido" son normales: el sistema funciona con los modelos que estén
listos y los demás se suman después.

### Paso 4 — Crear el usuario del sistema

El sistema exige iniciar sesión (el admin de Django está desactivado; se
usa un login propio en `/login/`). Crea tu usuario desde la terminal:

```bash
python manage.py createsuperuser
```

Con ese usuario y contraseña entras en **http://localhost:8000/login/**.

### Paso 5 — Ejecutar

```bash
python manage.py runserver
```

Abrir **http://localhost:8000/** → subir una foto de hoja → ver el diagnóstico.

> **La primera predicción tarda 20–60 segundos**: ahí es cuando TensorFlow
> carga los modelos en memoria. Las siguientes tardan menos de un segundo.
> Esto es normal, no es un error.

### Cuando se agregue o reemplace un modelo

1. Copiar el archivo `.keras` dentro de su carpeta
   (ej: `modelos_entrenados/vgg16/vgg16_tomato.keras`).
2. Editar el `info.json` de esa carpeta: poner el **F1 macro real** que le
   salió en la evaluación y el nombre del autor. Si no se horneó la
   normalización dentro del modelo, cambiar `"preprocesamiento"` al de su
   arquitectura (`"vgg16"`, `"resnet50"` o `"efficientnet"`).
3. Ejecutar `python manage.py registrar_modelos` y reiniciar el servidor.

Nada más. El ensemble incorpora el nuevo modelo automáticamente.

## 4. Páginas y API

| Ruta | Qué hace |
|---|---|
| `/` | Página de inicio pública: qué hace el sistema + botón "Iniciar sesión" |
| `/diagnostico/` | Formulario de subida + tabla de modelos activos con sus F1 |
| `/resultado/<id>/` | Diagnóstico: barras de probabilidad del ensemble + tabla "qué dijo cada modelo" |
| `/historial/` | Grilla paginada de predicciones anteriores |
| `/login/` y `/logout/` | Inicio y cierre de sesión (todas las páginas y la API requieren usuario) |
| `POST /api/predicciones/` | Igual que la web pero en JSON (`curl -u usuario:clave -F "imagen=@hoja.jpg" ...`) |
| `GET /api/predicciones/historial/` | Historial JSON paginado |
| `GET /api/modelos/` | Modelos activos y métricas |

## 5. Solución de problemas comunes

| Síntoma | Causa y solución |
|---|---|
| `ImportError: No se pudo importar Django` | El entorno virtual no está activo. Actívalo y reinstala requirements. |
| `No hay modelos activos registrados` al predecir | Falta correr `python manage.py registrar_modelos` (y que al menos una carpeta tenga `.keras` + `f1_macro > 0`). |
| La primera predicción "se queda pegada" | Es la carga de TensorFlow + modelos (hasta 60 s). Espera; las siguientes son rápidas. |
| `el archivo no existe: .../xxx.keras` | Un modelo quedó registrado pero borraron/movieron su archivo. Reponlo y corre de nuevo `python manage.py registrar_modelos`. |
| Error de conexión a PostgreSQL | Verifica que el servicio esté corriendo y que `DATABASE_URL` en `.env` tenga usuario/clave/puerto correctos. O borra esa línea para volver a SQLite. |
| Las imágenes del historial no cargan | Solo pasa con `DEBUG=False`. En desarrollo deja `DEBUG=True` (valor por defecto). |
| El modelo de un compañero predice "raro" (siempre la misma clase) | Casi seguro no horneó la normalización. Cambia su `preprocesamiento` en `info.json`, re-registra y reinicia. |

## 6. Producción (opcional)

```bash
gunicorn config.wsgi -w 1 --threads 4 --timeout 120
```
1 worker con hilos = una sola copia de los modelos en RAM. Con más workers
la memoria se multiplica (cada worker carga sus propios modelos).
