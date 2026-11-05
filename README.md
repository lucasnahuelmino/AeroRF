# AeroRF

**Plataforma GIS para el análisis de interferencias aeronáuticas**

AeroRF es una herramienta de investigación geográfica para el estudio de
interferencias en las bandas de comunicaciones aeronáuticas. Permite medir
distancias y áreas de protección, administrar objetos GIS, correlacionar
fuentes de interferencia con tráfico aéreo real y conservar **la procedencia
de cada dato**.

Desarrollado para la **Dirección Nacional de Control y Fiscalización
(ENACOM)**.

---

La fase actual de trabajo (AeroRF 2.4, en curso) amplía el Inspector con un
contrato de coordenadas más robusto, marcadores configurables por objeto,
dibujo repetido de líneas y exportación PNG del mapa. Su validación integral
está en progreso; consultar [RETOMAR.md](./RETOMAR.md) antes de tratarla como
una versión publicada.

## Qué hace y qué no hace

Esta distinción es lo más importante de la herramienta, y está impuesta en el
código, no sólo en la documentación.

**AeroRF no inventa posiciones.** No hay vuelos de demostración, ni datos
sintéticos, ni recorridos inventados para que el mapa se vea lleno. Cuando
OpenSky no tiene datos de una aeronave, la interfaz dice *"sin datos"*. Cuando
una posición no existe, el campo queda vacío en lugar de rellenarse.

**AeroRF no afirma causalidad.** La correlación entre una fuente de
interferencia y una aeronave informa de proximidad espacial. Dos cosas que
están cerca no se lesionan una a la otra por estarlo, y la herramienta nunca
lo insinúa: cada informe de correlación lleva la advertencia explícita.

**Todo dato declara su procedencia.** Cada punto, cada tramo de trayectoria y
cada valor guardado indica si es observado, histórico, en vivo, calculado o
introducido por el operador. Es la diferencia entre una medición y una
suposición, y es lo que hace defendible un análisis.

---

## Instalación

Requisitos: **Python 3.11+** y **Node.js 18+**.

```powershell
# Backend
cd AeroRF
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt

# Frontend
cd frontend
npm install
```

### Credenciales de OpenSky (opcional)

Sin credenciales AeroRF funciona por completo para el trabajo de campo: dibuja,
mide, guarda objetos, arma expedientes. Lo que se pierde son los vuelos en vivo
y las trayectorias históricas.

Para habilitarlas, copiá `.env.example` a `.env` y completá `OPENSKY_CLIENT_ID`
y `OPENSKY_CLIENT_SECRET` con las claves OAuth2 de OpenSky. El archivo `.env`
está en `.gitignore` y nunca debe subirse a un repositorio.

```powershell
Copy-Item .env.example .env
```

**Modo anónimo:** sin ningún valor configurado, AeroRF usa el acceso anónimo de
OpenSky, que permite consultar los vectores de estado globales. Es útil para
ver tráfico en vivo, aunque tiene límites de frecuencia más estrictos.

---

## Puesta en marcha

Dos procesos. El backend en el 8010 y el frontend en el 5173.

```powershell
# Terminal 1 — API
.\.venv\Scripts\python.exe -m uvicorn app.main:app --port 8010

# Terminal 2 — interfaz
cd frontend
$env:VITE_API_TARGET="http://127.0.0.1:8010"
npm run dev
```

Abrí `http://localhost:5173`.

> **El puerto 8010 no es arbitrario.** En esta máquina el 8000 está ocupado por
> otro proyecto. Si en la tuya está libre, AeroRF funciona igual en el 8000:
> ajustá `--port` y `VITE_API_TARGET` juntos.

También hay `start.bat` (Windows) y `start.sh` (Linux), que levantan ambos
procesos con las variables ya configuradas.

---

## Pilares de trabajo

La barra superior está presente en **todas** las secciones, así que siempre se
sabe dónde se está y siempre se puede ir a otro lugar.

| Pilar | Para qué es |
|---|---|
| **Mapa** | La herramienta principal. Todo el trabajo geográfico ocurre acá. |
| **Centro de Situación** | Estado reportado de servicios, vuelos seguidos, sesiones, eventos RF y mediciones recientes. |
| **Objetos GIS** | Administrar, buscar, filtrar, editar, ocultar y eliminar objetos persistentes, también si no se dibujan en el mapa. |
| **Análisis RF** | Frecuencias, armónicos, intermodulación y análisis espacial aeronáutico. |

### Workspace GIS

En el mapa, un único Workspace contextual organiza la navegación en cinco
categorías: Herramientas, Capas, Objetos, Vuelos y Aeropuertos. Cada categoría
abre sus tareas existentes; la configuración de herramientas y el Inspector
viven dentro del mismo panel, no en barras o inspectores laterales duplicados.
El panel puede moverse a cualquiera de los lados, redimensionarse, contraerse o
cerrarse; su navegación y preferencias se conservan localmente.

Al seleccionar un objeto en el mapa o en la lista, una aeronave, o un objeto
recién persistido, el Inspector muestra automáticamente ese contexto. Se puede
fijar para protegerlo de selecciones nuevas: estas quedan pendientes hasta que
se elija inspeccionarlas. El historial reciente permite recuperar contextos y
la acción Volver retorna a la tarea que estaba abierta antes de la inspección.

La reproducción embebida y el dock inferior usan el mismo estado de sesión y
replay de vuelos; no crean copias independientes. El dock permanece plegable y
el footer institucional ya no reserva espacio de pantalla dentro del árbol de
la aplicación.

La calculadora RF sigue disponible como herramienta. **Expedientes** está fuera de la navegación activa y sus rutas antiguas vuelven
al mapa, pero quedan consumidores internos y APIs legacy. El borrado de un
expediente con objetos GIS, mediciones, resultados RF o registros espectrales
se bloquea para proteger esos datos. La retirada completa depende de validar
su preservación y los vínculos destino; no se inspeccionaron ni migraron datos
de ninguna base en esta etapa.

El detalle de uso está en **[MANUAL.md](MANUAL.md)**.

---

## Cómo está construido

### Backend

FastAPI sobre Uvicorn. Se eligió sobre Flask (que sugería la especificación)
porque el repositorio ya usaba FastAPI, porque el WebSocket de vuelos necesita
soporte nativo de ASGI, y porque la validación con Pydantic cubre los contratos
de la API. Cambiar de framework habría duplicado la arquitectura y perdido el
WebSocket.

- **19 tablas** declaradas en SQLAlchemy. `map_objects` es la raíz única de todo objeto
  espacial del operador, con tablas satélite 1:1 para fuentes RF, antenas,
  eventos, mediciones y referencias.
- **Geometría doble**: columnas `Float` de latitud y longitud indexadas, para
  consultas espaciales portables, más una columna JSON `geometry` en GeoJSON.
  Migrar a PostGIS es un `ALTER TABLE`.
- Routers API bajo `/api/v1` para GIS, RF, vuelos, correlación, exportación y
  funciones heredadas. Se evita publicar un conteo no medido de endpoints.

### Frontend

Vue 3 con Vite, Tailwind, Pinia y Leaflet.

- **`MapEngine`** es una clase, no un composable: maneja los objetos de Leaflet
  y no debe ser reactivado por Vue. Los componentes hablan con el store, el
  store empuja al motor, y nunca al revés.
- El Workspace GIS usa el store `system` para persistir navegación, posición,
  tamaño y estado del contexto; selección, inspección y dibujo siguen usando
  los stores y componentes existentes para no duplicar datos ni motores.
- **`map/geo.js`** implementa la geodesia sin importar Leaflet, para poder
  probarla en Node y compararla con el backend.
- Stores de mapa, vuelos y sistema; `expedientes` permanece por compatibilidad
  heredada hasta su retirada segura.

### El orden de las coordenadas

Tres sistemas, tres órdenes: las herramientas de dibujo usan el orden de
Leaflet `[lat, lon]`, la API y el almacenamiento usan GeoJSON `[lon, lat]`, y el
operador escribe lo que escribe. La conversión ocurre en un único lugar
(`toApiPayload`, en el store de mapa) porque repartirla en varios sitios es la
forma más común de que un mapa dibuje una cosa y la base guarde otra.

---

## Pruebas

| Suite | Cubre | Comando |
|---|---|---|
| Backend | Lógica de negocio, geodesia, API, persistencia | `.\.venv\Scripts\python.exe -m pytest -q -m "not integration"` |
| Integración | WebSocket contra el backend | `.\.venv\Scripts\python.exe -m pytest -q -m integration` |
| Frontend | Componentes y flujos en jsdom | `cd frontend; npm test` |
| Build | Bundle de producción | `cd frontend; npm run build` |
| Paridad | Geodesia JS contra Python | `node tests/geo_parity.mjs` |

Ninguna prueba por defecto toca la red. OpenSky se ejercita con
`httpx.MockTransport`, y los contratos están fijados a **capturas reales** de su
API, no a lo que dice su documentación.

En la última ejecución completa del backend registrada en la base: **699
pasaron, 7 fueron excluidas** por el marcador de integración. Tras la
implementación del Workspace contextual, la suite frontend completa pasó:
**487 pruebas en 37 archivos**. Se ampliaron a 20 segundos los límites de dos
pruebas sensibles a la carga del entorno.

---

## Documentación

- **[MANUAL.md](MANUAL.md)** — guía de uso: cada sección, cada herramienta, los
  atajos de teclado y el flujo de trabajo recomendado.
- **[AERORF_ARCHITECTURE.md](AERORF_ARCHITECTURE.md)** — decisiones de diseño y
  sus motivos, para quien tenga que mantener el código.
- **[AERORF_2_AUDIT.md](AERORF_2_AUDIT.md)** — auditoría del checkout actual y
  estado verificado.
- **[AERORF_2_IMPLEMENTATION_PLAN.md](AERORF_2_IMPLEMENTATION_PLAN.md)** —
  etapas, dependencias y estado.
- **[AERORF_2_1_AUDIT.md](AERORF_2_1_AUDIT.md)** — auditoría del rebranding
  institucional y corrección de trayectorias.
- **[AERORF_2_1_IMPLEMENTATION_PLAN.md](AERORF_2_1_IMPLEMENTATION_PLAN.md)** —
  plan de trabajo, etapas y validación de la evolución 2.1.
- **[AERORF_2_CHANGELOG.md](AERORF_2_CHANGELOG.md)** — cambios de esta evolución.
- **[AERORF_CHANGELOG.md](AERORF_CHANGELOG.md)** — qué cambió y por qué.
- **[RETOMAR.md](RETOMAR.md)** — estado actual y qué queda pendiente.

---

## Estructura

```
AeroRF/
├── app/
│   ├── api/routes/     routers GIS, RF, vuelos y servicios
│   ├── core/           geodesia, unidades, tiempo, config, logging
│   ├── models/         19 tablas SQLAlchemy
│   └── services/       lógica de negocio
├── frontend/src/
│   ├── components/gis/ paneles del shell
│   ├── map/            MapEngine, dibujo, medición, aeronaves
│   ├── stores/         estado de Pinia
│   └── views/          shell GIS y herramientas
├── tests/              suite de Python y paridad
├── tools/              generadores de datos de referencia
└── .env.example
```

---

## Licencia y atribución

Software developed for the **Dirección Nacional de Control y Fiscalización
(ENACOM)**.

Los puntos de referencia de aeródromo provienen de **OurAirports** (dominio
público) y se generan con `tools/build_airports.py`; la capa del mapa dibuja
además la lista de sitios que cargó el operador
(`frontend/src/composables/useAirport.js`), sin persistirla. Los iconos del
mapa —el avión de aeropuerto y las fuentes de punto (FM, TPRS, Otro)— son de
**Font Awesome Free 6.7.2** (iconos CC BY 4.0) y viven en
`frontend/public/iconos/` con su `LEEME.txt`: se cambian reemplazando el
archivo. Los datos de vuelo provienen de la **OpenSky Network** bajo su
respetiva licencia.

La marca ENACOM no se reproduce en el software: se usa un lockup tipográfico.
Si la institución suministra el archivo oficial, se coloca en
`frontend/src/assets/enacom.svg` y se activa en `BrandBar.vue`.
