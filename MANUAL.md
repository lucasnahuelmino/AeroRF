# Manual de uso — AeroRF

Guía de las cuatro secciones y las diez herramientas del mapa. Para quien opera
la herramienta, no para quien la mantiene.

> Para instalar y para el diseño interno, ver **[README.md](README.md)** y
> **[AERORF_ARCHITECTURE.md](AERORF_ARCHITECTURE.md)**.

---

## Antes de empezar

Dos cosas que conviene tener presentes al trabajar:

**Todo dato declara de dónde viene.** Cada punto, cada tramo de trayectoria y
cada valor guardado lleva su procedencia: *observado*, *histórico*, *en vivo*,
*calculado* o *introducido por el usuario*. Cuando un dato no existe, AeroRF
muestra «dato no disponible». No rellena, no estima, no completa. Es lo que hace
que un expediente suyo sea defendible.

**La correlación no es causalidad.** La herramienta informa qué tan cerca está
una fuente de interferencia de una aeronave. Que dos cosas estén cerca no
significa que una moleste a la otra, y ningún informe de AeroRF sugiere lo
contrario.

---

## La barra superior

Está presente en **todas** las secciones. Es fina a propósito, para no robarle
altura al mapa.

| Elemento | Qué hace |
|---|---|
| Marca **AeroRF** | Vuelve al mapa, que es la pantalla principal. |
| **Mapa · Panel · Expedientes · Calculadora RF** | Navegación. El elemento activo lleva un filo celeste. |
| **Tres puntos** | Estado: backend, OpenSky, canal de vuelos en vivo. Verde = bien, ámbar = atención, gris = inactivo. Pasá el cursor sobre cada uno para el detalle. |
| **ENACOM** | Lockup institucional: Dirección Nacional de Control y Fiscalización. |

---

## Sección 1 — Mapa

La pantalla principal. Todo el trabajo geográfico ocurre acá.

### Estructura

```
┌──────────────────────────────────────────────────────────────┐
│  barra superior (48 px)                                       │
├──────────────────────────────────────────────────────────────┤
│  herramientas │              MAPA              │ inspector    │
│  Capas        │                               │              │
│  Vuelos       ├───────────────────────────────┤              │
│  Aeropuertos  │  coordenadas · escala · hora   │              │
│  Expediente   ├───────────────────────────────┤              │
│               │  línea de tiempo (opcional)    │              │
└──────────────────────────────────────────────────────────────┘
```

Los dos paneles laterales se pliegan y se arrastran por su borde: el mapa toma
todo el ancho que le dejen. Los anchos quedan recordado.

### Las cuatro pestañas del panel izquierdo

**Herramientas.** Opciones de la herramienta activa: unidades, radio, longitud,
azimut, colores. Los valores que escriba son los que se usan.

**Capas.** Diecisiete capas, cada una con visibilidad, opacidad, bloqueo y
cantidad de objetos. El bloqueo impide editar lo que contiene.

**Vuelos.** Búsqueda en OpenSky, lista de seguimiento de hasta 5 aeronaves,
grabación de trayectorias y reproducción.

**Aeropuertos.** Lo publicado (105 aeródromos de 8 países) sumado a los
sitios de su propia lista —EAVA, CCTE, aeroclubs—, con filtro por país y
distancia desde un aeropuerto a cualquier punto del mapa. Los aeropuertos
se dibujan con un avión: para cambiar el dibujo basta con reemplazar
`frontend/public/iconos/aeropuerto.svg` (mismo nombre, ver `LEEME.txt`).

**Expediente.** Vincular los objetos del mapa a un expediente en curso.

### El panel derecho: inspector

Muestra el objeto seleccionado: propiedades, geometría, notas e historial. Es
append-only: las notas se conservan para siempre y no se sobrescriben, y cada
cambio de un campo queda registrado con su valor anterior.

**Aquí es donde está toda la información de un objeto.** Al hacer clic en un
objeto no aparece ninguna ventana sobre el mapa: el mapa queda despejado y los
datos se leen en este panel, que además permite editarlos. Un clic ya selecciona;
el doble clic también, y conviene para líneas finas como un radial, donde el
blanco es de tres píxeles.

---

## Las diez herramientas del mapa

Se activan desde la barra superior. La barra muestra siempre una instrucción
de la herramienta activa.

### Herramientas de captura

| Herramienta | Cómo se usa | Qué crea |
|---|---|---|
| **Seleccionar** | Clic en un objeto para inspeccionarlo. Clic en vacío para deseleccionar. | — |
| **Punto** | Un clic en el mapa. | Un punto. |
| **Anotación** | Un clic, después escribí el texto. | Una nota geolocalizada. |

**La fuente del punto.** Al elegir **Punto**, las opciones muestran
**Fuente del punto**: Sin fuente (punto simple), FM, TPRS u Otra fuente. La
fuente se dibuja con su propio icono en el mapa, y también se cambia después
desde el inspector, sobre un punto ya dibujado. Los dibujos viven en
`frontend/public/iconos/` (`fm.svg`, `tprs.svg`, `otro.svg`): para cambiar
uno, reemplace el archivo conservando el nombre (instrucciones en
`LEEME.txt`).

### Herramientas de forma

| Herramienta | Cómo se usa | Qué crea |
|---|---|---|
| **Línea** | Clic en cada vértice. Doble clic o `Enter` para cerrar. `Esc` cancela. | Una polilínea, con su longitud. |
| **Polígono** | Igual que la línea, mínimo 3 vértices. | Un área. |
| **Traza** | Clic para agregar vértices a una traza abierta. | Un recorrido con longitud acumulada. |

**Se acumulan.** Dibujar una segunda línea no modifica la primera: cada forma
se guarda como un objeto independiente y todas conviven. Lo mismo con los
polígonos, las trazas y los círculos. Puede dibujar tantas líneas como necesite.

**Retroceso** quita el último vértice mientras dibuja.

### Herramientas de medida sobre el mapa

| Herramienta | Cómo se usa | Qué crea |
|---|---|---|
| **Círculo** | Clic para fijar el centro, después mueva el puntero para definir el radio. `Enter` confirma. | Un círculo exacto, con el radio en NM y km. |
| **Radial** | Clic para el origen, mueva para fijar azimut y longitud. | Un radial sobre el círculo máximo de la Tierra, no una recta en el plano. |
| **Medir** | Clic en A, clic en B. Clic sucesivos para multipunto. | Una lectura, no un objeto. Guardala si la quiere conservar. |
| **Cobertura** | Dibuje el contorno de un área. | Un polígono de cobertura. |

**El radio tecleado se respeta.** Si escribe 20 NM en el panel de herramientas
y hace clic sin mover el puntero, obtiene 20 NM. El puntero ajusta; no pisa lo
que escribió.

**Unidades.** NM, km o metros, a elección. Las distancias se muestran siempre en
las dos unidades principales, porque un expediente puede pedir una y el otro
lector entender la otra.

---

## Sección 2 — Panel

Estado del sistema en un vistazo: cuántos objetos hay en el mapa, cuántos
expedientes están abiertos, cuántas fuentes y eventos RF, cuántas aeronaves
están en seguimiento.

Si OpenSky no está configurado, aparece arriba un aviso que explica qué
configurar. El resto de la herramienta funciona igual sin eso.

---

## Sección 3 — Expedientes

Un expediente es un caso de investigación: un conjunto de objetos del mapa,
notas, mediciones y Radio_events, con su historial.

**Para crear uno:** botón «Nuevo» arriba a la derecha. Complete número,
asunto y fechas.

**Para vincular objetos:** vaya al mapa, seleccione un objeto, y en el panel
derecho use «asociar a expediente». El objeto quedavinculado y aparece en la
ficha del expediente.

**Historial.** Cada cambio de un objeto queda registrado con su valor anterior
y el nuevo. No se puede perder: es lo que sostiene una denuncia.

---

## Sección 4 — Calculadora RF

Motor de cálculo de frecuencias, sin mapa. Para el trabajo de gabinete.

- **Armónicos:** hasta qué frecuencia llega un equipo, y a qué nivel.
- **Intermodulación:** qué combinaciones de dos frecuencias generan una tercera
  no deseable, y cuál de ellas cae dentro de una banda aeronáutica.
- **Bandas aeronáuticas:** referencia de las bandas de vuelo.

### Guardar un resultado en un expediente

1. Haga el cálculo y seleccione el resultado que le interesa.
2. En **Análisis detallado**, elija el **expediente de destino** en el
   desplegable. Si la lista está vacía, cree primero un expediente desde
   **Expedientes**.
3. Pulse **Guardar en Expediente**. El aviso de abajo confirma en qué
   expediente quedó y con qué número de evento. Si algo falla, el aviso lo
   dice en rojo y no se guardó nada.

Los resultados guardados aparecen en **Expedientes → detalle → Análisis RF →
Guardados en este expediente**. Se guardan en la base, así que siguen ahí
cuando vuelve a entrar, a diferencia de **Resultados del último cálculo**, que
es lo que arrojó el cálculo de esta sesión y se pierde al salir.

---

## Flujo de trabajo recomendado

**Para una denuncia de interferencia:**

1. **Ubicar.** Abra el mapa. active la capa **Aeropuertos** para tener el
   contexto de qué estación estás cerca.
2. **Medir.** Cree un círculo alrededor de la estación afectada, con el radio
   que sea pertinente. El radio queda en NM y km.
3. **Documentar.** Cree el punto de la fuente, con sus características RF en
   el inspector.
4. **Vincular.** Asocie cada objeto al expediente.
5. **Registrar vuelos.** En **Vuelos**, busque el tráfico que atraviesa la
   zona y agregue hasta 5 aeronaves a la lista de seguimiento. Pulse
   **Trayectoria** para ver su ruta.
6. **Cotejar.** La correlación espacial muestra qué fuentes están dentro del
   radio. **Lea la advertencia:** proximidad no es causalidad.
7. **Exportar.** Desde el expediente, exporte a GeoJSON, KML o CSV.

**Para un estudio de protección:**

1. Delimite el área con un **círculo** o un **polígono**.
2. Use **Medir** para las distancias críticas dentro del área.
3. Compare contra la capa de **aeropuertos** para tener la referencia más cercana.

---

## Atajos de teclado

| Tecla | Acción |
|---|---|
| `Esc` | Cancela la herramienta activa, la medición y el menú contextual. |
| `Enter` | Confirma el dibujo en curso. |
| `Retroceso` | Quita el último vértice. |
| Clic derecho | Abre el menú contextual en el mapa. |
| Doble clic | Cierra una línea o un polígono. |

---

## Preguntas frecuentes

**No me aparecen vuelos en vivo.**
Revise el punto de OpenSky en la barra superior. Ámbar significa que faltan
credenciales: configure `OPENSKY_CLIENT_ID` y `OPENSKY_CLIENT_SECRET` en `.env`
y reinicie el backend. Sin configurarlo, AeroRF funciona para todo lo demás.

**La trayectoria de un avión no crece.**
La trayectoria en vivo se refresca cada 30 segundos mientras el vuelo sigue en
curso. Si el avión aterrizó, la línea queda fija: es correcto, el vuelo
terminó. Los vuelos históricos no se refrescan, porque su trayectoria no puede
cambiar.

**No puedo guardar un círculo.**
Verifique que el radio sea mayor que cero. Un círculo de radio cero no es una
medida, y AeroRF no lo guarda.

**¿Dónde queda lo que dibujo?**
Todo objeto del mapa se guarda en la base de datos, con su historial. Los
aeropuertos y los sitios de su lista **no**: son datos de referencia —
publicados y su propia lista — y se redibujan desde los archivos en cada
arranque. Por eso no puede editarlos ni borrarlos, y es intencional: un
punto de referencia no es una medición suya.

**¿Y si borro algo por error?**
AeroRF guarda una copia de la base de datos en la carpeta `respaldos`, dentro de
la carpeta del proyecto, **cada vez que arranca** y antes de escribir nada. Se
conservan las 10 más recientes; las más viejas se reemplazan solas. Para volver
a un estado anterior: cierre AeroRF, renombre el `aerorf.db` actual y ponga en su
lugar la copia que quiera, quitándole la fecha del nombre. La copia se hace con
el propio SQLite, de modo que incluye lo último escrito aunque el servidor
estuviera corriendo.

**Los datos de OpenSky no coinciden con lo que veo en el radar.**
La resolución de los tracks de OpenSky no es de un punto por segundo. Un vuelo
típico tiene un punto cada decenas de segundos, y más separados cuando el avión
no cambia de rumbo. La respuesta de la API indica cuántos puntos hay y cada
cuánto: lea ese dato antes de concluir que falta información.

**¿AeroRF guarda mis búsquedas?**
Guarda los objetos que usted crea, con su historial. Las consultas a OpenSky
consumen créditos de la cuenta configurada en `.env`, por eso la aplicación
limita la frecuencia y avisa cuando alcanza el límite.

---

## Soporte

Documentación técnica: `AERORF_ARCHITECTURE.md`.
Estado del proyecto: `RETOMAR.md`.
Historial de cambios: `AERORF_CHANGELOG.md`.
