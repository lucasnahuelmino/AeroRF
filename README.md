# RF Interference System

Proyecto para detectar y analizar interferencias RF, con dashboard, mapas y búsqueda de rutas de vuelo.

Contenido:
- `app/` - backend FastAPI
- `frontend/` - Vue 3 + Vite frontend
- `rf_engine/` - motor de análisis RF

Instrucciones rápidas:

1. Backend (Python):

```bash
# crear y activar venv
python -m venv .venv
.venv\Scripts\activate   # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```

2. Frontend:

```bash
cd frontend
npm install
npm run dev
```

3. Para subir a GitHub: inicializa repo local (ya hecho) y añade un remoto con la URL que crea tu repositorio en GitHub, luego `git push -u origin main`.
# SIARI — RF Interference Analysis System

Plataforma profesional para investigación y análisis de interferencias en banda aeronáutica.

## Estructura del Proyecto

```
rf-interference-system/
├── app/                          # Backend (Python/FastAPI)
│   ├── main.py                   # Punto de entrada
│   ├── api/
│   │   └── routes/
│   │       ├── rf.py             # Cálculos RF básicos
│   │       ├── rf_expediente.py  # RF integrado con expedientes
│   │       └── expedientes.py    # Gestión de casos
│   ├── models/
│   │   ├── expediente.py         # Modelo de caso
│   │   ├── medicion.py           # Mediciones de campo
│   │   ├── evento_rf.py          # Eventos RF detectados
│   │   ├── espectro.py           # Registros espectrales
│   │   ├── rf_models.py          # Modelos RF originales
│   │   └── schemas.py            # Schemas Pydantic
│   ├── rf_engine/                # Motor RF (existente)
│   │   ├── engine.py
│   │   ├── harmonics.py
│   │   ├── intermod.py
│   │   ├── ranking.py
│   │   └── ...
│   ├── services/
│   │   └── rf_service.py         # Servicio RF integrado
│   ├── database/
│   │   └── database.py           # Configuración SQLAlchemy
│   └── core/
├── frontend/                     # Frontend (Vue 3/Vite)
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   └── src/
│       ├── main.js
│       ├── App.vue
│       ├── components/           # Componentes Vue
│       ├── views/
│       │   ├── DashboardView.vue
│       │   ├── ExpedientesView.vue
│       │   ├── ExpedienteDetalleView.vue
│       │   ├── CalculadoraRFView.vue
│       │   ├── MapasView.vue
│       │   └── EspectroView.vue
│       ├── stores/               # Pinia stores
│       │   ├── expedientes.js
│       │   └── rf.js
│       ├── services/             # API clients
│       ├── assets/
│       └── utils/
├── requirements.txt              # Dependencias Python
├── .env.example                  # Variables de entorno
└── README.md
```

## Setup Inicial

### 1. Backend

```bash
# Navegar a la raíz del proyecto
cd rf-interference-system

# Crear ambiente virtual (ya debe existir)
python -m venv .venv

# Activar ambiente
.venv\Scripts\activate  # Windows
# o
source .venv/bin/activate  # Linux/Mac

# Instalar dependencias
pip install -r requirements.txt

# Crear archivo .env
cp .env.example .env

# Ejecutar servidor
uvicorn app.main:app --reload --port 8000
```

Swagger UI: http://localhost:8000/docs

### 2. Frontend

```bash
# En otra terminal, navegar a la carpeta frontend
cd frontend

# Instalar dependencias (requiere Node.js 18+)
npm install

# Ejecutar servidor de desarrollo
npm run dev
```

App estará disponible en: http://localhost:5173

## Stack Tecnológico

### Backend
- **FastAPI** — Framework web moderno
- **SQLAlchemy** — ORM para base de datos
- **Pydantic** — Validación de datos
- **pandas/NumPy** — Análisis de datos

### Frontend
- **Vue 3** — Framework UI reactivo
- **Vite** — Build tool ultra-rápido
- **Pinia** — Estado global
- **TailwindCSS** — Estilos
- **Plotly.js** — Gráficos
- **Leaflet** — Mapas interactivos
- **Axios** — HTTP client

### Base de datos
- **SQLite** (desarrollo) / **PostgreSQL** (producción)

## Módulos Funcionales

### ✅ Implementados

1. **Gestión de Expedientes** — Crear, listar, actualizar expedientes
2. **Motor Matemático RF** — Cálculos de armónicas e IM (existente)
3. **Integración RF-BD** — Almacenar y correlacionar resultados
4. **Dashboard** — Vista general de casos activos
5. **Calculadora RF** — Interfaz para cálculos interactivos
6. **Detalle de Expediente** — Análisis completo de caso

### 🔄 En desarrollo

7. **Mapas y Geolocalización** — Visualizar puntos de medición
8. **Rutas de Vuelo** — Integración OpenSky API
9. **Registro Espectral** — Cargar y procesar espectrogramas
10. **Exportación** — PDF, Excel, reportes

## API Endpoints

### Expedientes
```
GET    /api/v1/expedientes                    — Listar todos
POST   /api/v1/expedientes                    — Crear nuevo
GET    /api/v1/expedientes/{id}               — Obtener uno
PUT    /api/v1/expedientes/{id}               — Actualizar
DELETE /api/v1/expedientes/{id}               — Eliminar
GET    /api/v1/expedientes/{id}/mediciones    — Mediciones
GET    /api/v1/expedientes/{id}/eventos       — Eventos RF
```

### RF Engine
```
POST   /api/v1/rf/calculate                   — Cálculo rápido
GET    /api/v1/rf/harmonics/{freq}            — Tabla armónicas
POST   /api/v1/rf/expedientes/{id}/calculate  — Cálculo integrado
GET    /api/v1/rf/expedientes/{id}/candidates — Top candidatos
GET    /api/v1/rf/frequency-conflicts         — Búsqueda histórica
```

## Estructura de Datos

### Expediente
```json
{
  "id": 1,
  "numero_expediente": "EXP-2026-001",
  "freq_mhz": 119.0,
  "aeropuerto": "Ministro Pistarini",
  "lat": -34.8196,
  "lon": -58.5356,
  "estado": "investigacion",
  "severidad": "alta",
  "inspector_responsable": "Juan Pérez",
  "observaciones": "Interferencia intermitente",
  "fecha_creacion": "2026-05-27T10:00:00"
}
```

### EventoRF
```json
{
  "id": 1,
  "expediente_id": 1,
  "formula": "2×88.5 - 58.0",
  "tipo_producto": "IM3",
  "resultado_mhz": 119.0,
  "error_khz": 0.5,
  "score_probabilidad": 92,
  "freq_1_mhz": 88.5,
  "freq_2_mhz": 58.0
}
```

## Cálculos RF

El sistema calcula:

1. **Armónicas**: 2f, 3f, 4f, ... nf
2. **IM2**: f1 + f2, |f1 - f2|
3. **IM3**: 2f1 - f2, 2f2 - f1, 2f1 + f2, 2f2 + f1
4. **IM5 y IM7**: Órdenes superiores

### Scoring
- **Proximidad**: ¿Qué tan cerca está del objetivo?
- **Orden del producto**: ¿Qué tan probable es este tipo?
- **Tipo de señal**: ¿Qué emisor es? (FM, TV, etc)
- **Potencia**: Si se conoce, ¿cuál es la potencia?

Resultado: **Score 0-99** que indica probabilidad de interferencia.

## Desarrollo

### Agregar nueva ruta
```python
# En app/api/routes/nueva_ruta.py
from fastapi import APIRouter

router = APIRouter(prefix="/nueva", tags=["Mi Módulo"])

@router.get("/")
def mi_endpoint():
    return {"message": "Hola"}

# En app/main.py
from app.api.routes.nueva_ruta import router as nueva_router
app.include_router(nueva_router, prefix="/api/v1")
```

### Agregar nuevo modelo
```python
# En app/models/nuevo_modelo.py
from app.database.database import Base
from sqlalchemy import Column, Integer, String

class MiModelo(Base):
    __tablename__ = "mi_tabla"
    id = Column(Integer, primary_key=True)
    nombre = Column(String(100))

# En app/models/__init__.py
from app.models.nuevo_modelo import MiModelo
```

### Agregar componente Vue
```vue
<!-- En frontend/src/components/MiComponente.vue -->
<template>
  <div>Mi Componente</div>
</template>

<script setup>
// Lógica
</script>
```

## Testing

```bash
# Backend
pytest app/rf_engine/test_rf_engine.py -v

# Frontend (futuro)
npm run test
```

## Producción

### Backend
```bash
# Con Gunicorn + Uvicorn
pip install gunicorn
gunicorn app.main:app -w 4 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

### Frontend
```bash
# Build
npm run build

# Servir con nginx o similar
```

## Troubleshooting

### "Module not found: app"
- Asegurar que se ejecuta uvicorn desde la **raíz del proyecto**
- No desde la carpeta `app/`

### Port 8000 ya en uso
```bash
netstat -ano | findstr :8000  # Windows
kill -9 <PID>
```

### Base de datos corrupta
```bash
# Eliminar y recrear
rm siari.db
# Se recreará automáticamente en el startup
```

## Próximos Pasos

1. ✅ Estructura base
2. ✅ Motor RF integrado
3. ⏳ Mapas interactivos (Leaflet)
4. ⏳ Integración OpenSky (rutas de vuelo)
5. ⏳ Dashboard en tiempo real (WebSockets)
6. ⏳ Exportación de reportes (PDF)
7. ⏳ IA para detección automática
8. ⏳ Streaming en tiempo real (SDR)

## Contacto

**ENACOM — Ente Nacional de Comunicaciones**
Gestión del Espectro
