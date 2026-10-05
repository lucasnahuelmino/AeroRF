# AeroRF

**Plataforma GIS para el análisis de interferencias aeronáuticas**

AeroRF es una herramienta de investigación geográfica para el estudio de
interferencias en las bandas de comunicaciones aeronáuticas. Permite medir
distancias y áreas de protección, documentar hallazgos en expedientes y
correlacionar espacialmente fuentes de interferencia con el tráfico aéreo
real, dejando en cada caso constancia de **de dónde viene cada dato**.

Desarrollado para la **Dirección Nacional de Control y Fiscalización
(ENACOM)**.

---

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
suposición, y en un expediente de la medida es lo único que hace defendible el
documento.

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

## Las cinco secciones

La barra superior está presente en **todas** las secciones, así que siempre se
sabe dónde se está y siempre se puede ir a otro lugar.

| Sección | Para qué es |
|---|---|
| **Mapa** | La herramienta principal. Todo el trabajo geográfico ocurre acá. |
| **Panel** | Estado del sistema: objetos, expedientes, fuentes, y aeronaves en seguimiento. |
| **Expedientes** | Casos de investigación. Cada expediente agrupa objetos, notas e historial. |
| **Calculadora RF** | Frecuencias, armónicos e intermodulación. Motor de cálculo, sin mapa. |
| **Espectro** | Análisis espectral de mediciones. |

El detalle de cada una está en **[MANUAL.md](MANUAL.md)**.

---

## Cómo está construido

### Backend

FastAPI sobre Uvicorn. Se eligió sobre Flask (que sugería la especificación)
porque el repositorio ya usaba FastAPI, porque el WebSocket de vuelos necesita
soporte nativo de ASGI, y porque la validación con Pydantic cubre los contratos
de la API. Cambiar de framework habría duplicado la arquitectura y perdido el
WebSocket.

- **19 tablas** en SQLAlchemy. `map_objects` es la raíz única de todo objeto
  espacial del operador, con tablas satélite 1:1 para fuentes RF, antenas,
  eventos, mediciones y referencias.
- **Geometría doble**: columnas `Float` de latitud y longitud indexadas, para
  consultas espaciales portables, más una columna JSON `geometry` en GeoJSON.
  Migrar a PostGIS es un `ALTER TABLE`.
- **86 endpoints** bajo `/api/v1`.

### Frontend

Vue 3 con Vite, Tailwind, Pinia y Leaflet.

- **`MapEngine`** es una clase, no un composable: maneja los objetos de Leaflet
  y no debe ser reactivado por Vue. Los componentes hablan con el store, el
  store empuja al motor, y nunca al revés.
- **`map/geo.js`** implementa la geodesia sin importar Leaflet, para poder
  probarla en Node y compararla con el backend.
- **Cuatro stores**: `map`, `flights`, `system`, `expedientes`.

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
| Python (336) | Lógica de negocio, geodesia, API, persistencia | `pytest -m "not integration"` |
| Integración (7) | WebSocket contra el backend real | `pytest -m integration` |
| Paridad (675) | Geodesia JS contra Python, número a número | `node tests/geo_parity.mjs` |
| Componentes (78) | Montaje real en jsdom: shell, paneles, motores | `npm test` |
| Layout (15) | Proporciones del shell, leídas del CSS construido | `npm run test:layout` |
| Objetos (11) | Traducción de geometría, cierre de anillos | `npm run test:objects` |
| Aeropuertos (43) | Datos, capa conmutable, medición, lista del operador | `npm run test:airports` |
| Barra (12) | Botones de herramientas, área de clic | `npm run test:toolbar` |
| Marca (14) | Cabecera, menú, lockup institucional | `npm run test:brandbar` |

**Total: 343 en Python, 161 en el navegador, 675 de paridad.**

Ninguna prueba por defecto toca la red. OpenSky se ejercita con
`httpx.MockTransport`, y los contratos están fijados a **capturas reales** de su
API, no a lo que dice su documentación.

La paridad geodesica merece una nota: `geo_parity.mjs` ejecuta los mismos
vectores en Node y en Python y compara los resultados como texto. Cualquier
divergencia de unadecimal fallaría ambos lados.

---

## Documentación

- **[MANUAL.md](MANUAL.md)** — guía de uso: cada sección, cada herramienta, los
  atajos de teclado y el flujo de trabajo recomendado.
- **[AERORF_ARCHITECTURE.md](AERORF_ARCHITECTURE.md)** — decisiones de diseño y
  sus motivos, para quien tenga que mantener el código.
- **[AERORF_AUDIT.md](AERORF_AUDIT.md)** — qué se encontró al examinar el
  sistema.
- **[AERORF_CHANGELOG.md](AERORF_CHANGELOG.md)** — qué cambió y por qué.
- **[RETOMAR.md](RETOMAR.md)** — estado actual y qué queda pendiente.

---

## Estructura

```
AeroRF/
├── app/
│   ├── api/routes/     86 endpoints
│   ├── core/           geodesia, unidades, tiempo, config, logging
│   ├── models/         19 tablas SQLAlchemy
│   └── services/       lógica de negocio
├── frontend/src/
│   ├── components/gis/ paneles del shell
│   ├── map/            MapEngine, dibujo, medición, aeronaves
│   ├── stores/         estado de Pinia
│   └── views/          las cinco secciones
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
