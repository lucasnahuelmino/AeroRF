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

La fase publicada de trabajo (**AeroRF 2.6**) cerró la retirada funcional de
Expedientes (la calculadora ahora guarda sus análisis en un historial propio),
la importación CSV robusta de emisoras FM, la exportación PNG confiable del
mapa, y la calculadora arrancando vacía con datos de ejemplo opcionales. El
detalle y la verificación de cada fase están en [RETOMAR.md](./RETOMAR.md) y
[AERORF_CHANGELOG.md](./AERORF_CHANGELOG.md); consultarlos antes de tratar
cualquier cosa como publicada.

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

La **Calculadora RF** trabaja en dos modos con una sola entrada de datos:
**Armónicos** (una fila por emisora contra la referencia, con
`armónica = fundamental × orden` y la diferencia en kHz, y los estados
Exacta / En tolerancia / Fuera de tolerancia) e **Intermodulación** (el
motor completo con detalle del producto, «candidatos matemáticos» de
`Referencia /2 /3 /4` y exportación CSV/JSON). Los límites de parámetros
los fija el motor y la pantalla los valida antes de pedir, y no muestra
probabilidades porque el motor no las calcula. **Expedientes** quedó retirado como dependencia funcional en AeroRF 2.6 (Bloque 1): la calculadora guarda sus análisis en un historial propio (`POST /rf/analisis`, tabla `analisis_rf`), y el inspector ya no ofrece asociar objetos a expedientes. Las rutas antiguas vuelven al mapa; los datos históricos y el API legado `/expedientes/*` siguen intactos en el backend.

