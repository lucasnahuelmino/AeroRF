/**
 * composables/useAirport.js
 * ─────────────────────────
 * La lista de sitios que el operador cargó para visualizar en el mapa:
 * aeropuertos, sitios de las áreas de control (ACC/EAVA), CCTE y aeroclubs.
 *
 * ── Procedencia ──────────────────────────────────────────────────────────
 * Cargada por el operador en octubre de 2026 desde su lista de trabajo.
 * No es un archivo generado: las coordenadas son las que él entregó. Por eso
 * `airports.spec.js` le aplica las mismas salvaguardas que al archivo
 * publicado — identificadores únicos y coordenadas en rango — porque un dato
 * mal copiado se ve igual que uno válido.
 *
 * ── Cómo se usa ──────────────────────────────────────────────────────────
 * `map/airports.js` la aplana y la dibuja junto a lo publicado: un sitio que
 * coincide con un aeropuerto del archivo publicado (≤ 2 km) se dibuja una
 * sola vez, enriquecido con sus códigos ICAO/IATA; el resto se dibuja como
 * sitio de la lista. Los aeropuertos usan el icono de `public/iconos/
 * aeropuerto.svg` — cambiar la imagen es reemplazar el archivo, sin tocar
 * código.
 *
 * La estructura `{ group, options }` también sirve como fuente de selectores
 * agrupados (optgroup), de modo que el mapa y cualquier buscador leen la
 * misma lista: una sola verdad, no dos.
 */

export function useAirport() {
  const airport = [
    {
      group: 'AEROPARQUE JORGE NEWBERY',
      options: [
        {
          value: 'AEROPARQUE JORGE NEWBERY',
          label: 'AEROPARQUE JORGE NEWBERY',
          latitude: -34.558888,
          longitude: -58.416389,
        },
      ],
    },
    {
      group: 'BAHÍA BLANCA',
      options: [
        {
          value: 'BAHÍA BLANCA',
          label: 'BAHÍA BLANCA',
          latitude: -38.7275,
          longitude: -62.15333333,
        },
      ],
    },
    {
      group: 'EZEIZA',
      options: [
        {
          value: 'EZEIZA',
          label: 'EZEIZA',
          latitude: -34.8135,
          longitude: -58.54125,
        },
      ],
    },
    {
      group: 'ACC EZEIZA',
      options: [
        {
          value: 'EZEIZA - EZEIZA (LOCAL)',
          label: 'EZEIZA (LOCAL)',
          latitude: -34.8135,
          longitude: -58.54125,
        },
        {
          value: 'EZEIZA - EAVA SAUCE VIEJO',
          label: 'EAVA SAUCE VIEJO',
          latitude: -31.709206,
          longitude: -60.806161,
        },
        {
          value: 'EZEIZA - EAVA SANTA ROSA',
          label: 'EAVA SANTA ROSA',
          latitude: -36.591944,
          longitude: -64.279444,
        },
        {
          value: 'EZEIZA - EAVA GUALEGUAYCHÚ',
          label: 'EAVA GUALEGUAYCHÚ',
          latitude: -33.01249,
          longitude: -58.61075,
        },
        {
          value: 'EZEIZA - EAVA CONCORDIA',
          label: 'EAVA CONCORDIA',
          latitude: -31.395147,
          longitude: -58.01665,
        },
        {
          value: 'EZEIZA - EAVA ROSARIO',
          label: 'EAVA ROSARIO',
          latitude: -32.917197,
          longitude: -60.780605,
        },
        {
          value: 'EZEIZA - EAVA BAHÍA BLANCA',
          label: 'EAVA BAHÍA BLANCA',
          latitude: -38.714417,
          longitude: -62.163806,
        },
        {
          value: 'EZEIZA - EAVA MAR DEL PLATA',
          label: 'EAVA MAR DEL PLATA',
          latitude: -37.933306,
          longitude: -57.581306,
        },
        {
          value: 'EZEIZA - EAVA PEHUAJÓ',
          label: 'EAVA PEHUAJÓ',
          latitude: -35.840414,
          longitude: -61.860869,
        },
        {
          value: 'EZEIZA - EAVA TANDIL',
          label: 'EAVA TANDIL',
          latitude: -37.237167,
          longitude: -59.238028,
        },
        {
          value: 'EZEIZA - EAVA CHOELE CHOEL',
          label: 'EAVA CHOELE CHOEL',
          latitude: -39.281794,
          longitude: -65.619158,
        },
        {
          value: 'EZEIZA - EAVA CHACHARRAMENDI',
          label: 'EAVA CHACHARRAMENDI',
          latitude: -37.331411,
          longitude: -65.651553,
        },
        {
          value: 'EZEIZA - EAVA NEUQUÉN',
          label: 'EAVA NEUQUÉN',
          latitude: -38.952028,
          longitude: -68.140083,
        },
        {
          value: 'EZEIZA - EAVA PIEDRA DEL ÁGUILA',
          label: 'EAVA PIEDRA DEL ÁGUILA',
          latitude: -39.99875,
          longitude: -70.042167,
        },
        {
          value: 'EZEIZA - EAVA RINCÓN DE LOS SAUCES',
          label: 'EAVA RINCÓN DE LOS SAUCES',
          latitude: -37.390669,
          longitude: -68.926119,
        },
        {
          value: 'EZEIZA - EAVA JUNÍN',
          label: 'EAVA JUNÍN',
          latitude: -34.55075,
          longitude: -60.926,
        },
        {
          value: 'EZEIZA - EAVA RUFINO',
          label: 'EAVA RUFINO',
          latitude: -34.266072,
          longitude: -62.712444,
        },
      ],
    },
    {
      group: 'CÓRDOBA',
      options: [
        {
          value: 'CÓRDOBA',
          label: 'CÓRDOBA',
          latitude: -31.323611,
          longitude: -64.207222,
        },
      ],
    },
    {
      group: 'ACC CÓRDOBA',
      options: [
        {
          value: 'CÓRDOBA - CÓRDOBA (LOCAL)',
          label: 'CÓRDOBA (LOCAL)',
          latitude: -31.323611,
          longitude: -64.207222,
        },
        {
          value: 'CÓRDOBA - EAVA LA POSTA',
          label: 'EAVA LA POSTA',
          latitude: -31.616981,
          longitude: -64.879394,
        },
        {
          value: 'CÓRDOBA - EAVA FRÍAS',
          label: 'EAVA FRÍAS',
          latitude: -28.632211,
          longitude: -65.120792,
        },
        {
          value: 'CÓRDOBA - EAVA ANCASTI',
          label: 'EAVA ANCASTI',
          latitude: -28.534742,
          longitude: -65.609246,
        },
        {
          value: 'CÓRDOBA - EAVA TUCUMÁN',
          label: 'EAVA TUCUMÁN',
          latitude: -26.8369,
          longitude: -65.108397,
        },
        {
          value: 'CÓRDOBA - EAVA SAN JUANCITO',
          label: 'EAVA SAN JUANCITO',
          latitude: -24.375125,
          longitude: -65.009686,
        },
        {
          value: 'CÓRDOBA - EAVA SUSQUES',
          label: 'EAVA SUSQUES',
          latitude: -23.398056,
          longitude: -66.36625,
        },
        {
          value: 'CÓRDOBA - EAVA MARCOS JUÁREZ',
          label: 'EAVA MARCOS JUÁREZ',
          latitude: -32.698789,
          longitude: -62.159847,
        },
        {
          value: 'CÓRDOBA - EAVA RÍO CUARTO',
          label: 'EAVA RÍO CUARTO',
          latitude: -33.089958,
          longitude: -64.1606,
        },
        {
          value: 'CÓRDOBA - EAVA CERES',
          label: 'EAVA CERES',
          latitude: -29.878319,
          longitude: -61.943625,
        },
        {
          value: 'CÓRDOBA - EAVA ANDALGALÁ',
          label: 'EAVA ANDALGALÁ',
          latitude: -27.579259,
          longitude: -66.03255,
        },
        {
          value: 'CÓRDOBA - EAVA MONTE QUEMADO',
          label: 'EAVA MONTE QUEMADO',
          latitude: -25.811208,
          longitude: -62.820853,
        },
        {
          value: 'CÓRDOBA - EAVA TARTAGAL',
          label: 'EAVA TARTAGAL',
          latitude: -22.515314,
          longitude: -63.8046,
        },
      ],
    },
    {
      group: 'RESISTENCIA',
      options: [
        {
          value: 'RESISTENCIA',
          label: 'RESISTENCIA',
          latitude: -27.444184,
          longitude: -59.046406,
        },
      ],
    },
    {
      group: 'ACC RESISTENCIA',
      options: [
        {
          value: 'RESISTENCIA - RESISTENCIA (LOCAL)',
          label: 'RESISTENCIA (LOCAL)',
          latitude: -27.444184,
          longitude: -59.046406,
        },
        {
          value: 'RESISTENCIA - EAVA LAS LOMITAS',
          label: 'EAVA LAS LOMITAS',
          latitude: -24.706389,
          longitude: -60.593333,
        },
        {
          value: 'RESISTENCIA - EAVA FORMOSA',
          label: 'EAVA FORMOSA',
          latitude: -26.182544,
          longitude: -58.172244,
        },
        {
          value: 'RESISTENCIA - EAVA PRESIDENCIA ROQUE SAENZ PEÑA',
          label: 'EAVA PRESIDENCIA ROQUE SAENZ PEÑA',
          latitude: -26.788181,
          longitude: -60.442928,
        },
        {
          value: 'RESISTENCIA - EAVA IGUAZÚ',
          label: 'EAVA IGUAZÚ',
          latitude: -25.603056,
          longitude: -54.57166,
        },
        {
          value: 'RESISTENCIA - EAVA POSADAS',
          label: 'EAVA POSADAS',
          latitude: -27.38573,
          longitude: -55.97049,
        },
        {
          value: 'RESISTENCIA - EAVA PASO DE LOS LIBRES',
          label: 'EAVA PASO DE LOS LIBRES',
          latitude: -29.712828,
          longitude: -57.086554,
        },
        {
          value: 'RESISTENCIA - EAVA RECONQUISTA',
          label: 'EAVA RECONQUISTA',
          latitude: -29.204389,
          longitude: -59.694067,
        },
      ],
    },
    {
      group: 'COMODORO RIVADAVIA',
      options: [
        {
          value: 'COMODORO RIVADAVIA',
          label: 'COMODORO RIVADAVIA',
          latitude: -45.790018,
          longitude: -67.467925,
        },
      ],
    },
    {
      group: 'ACC COMODORO RIVADAVIA',
      options: [
        {
          value: 'COMODORO RIVADAVIA - COMODORO RIVADAVIA (LOCAL)',
          label: 'COMODORO RIVADAVIA (LOCAL)',
          latitude: -45.790018,
          longitude: -67.467925,
        },
        {
          value: 'COMODORO RIVADAVIA - EAVA RÍO GALLEGOS',
          label: 'EAVA RÍO GALLEGOS',
          latitude: -51.611722,
          longitude: -69.306333,
        },
        {
          value: 'COMODORO RIVADAVIA - EAVA RÍO GRANDE',
          label: 'EAVA RÍO GRANDE',
          latitude: -53.7815,
          longitude: -67.753278,
        },
        {
          value: 'COMODORO RIVADAVIA - EAVA RÍO MAYO',
          label: 'EAVA RÍO MAYO',
          latitude: -45.692756,
          longitude: -70.246369,
        },
        {
          value: 'COMODORO RIVADAVIA - EAVA SAN JULIÁN',
          label: 'EAVA SAN JULIÁN',
          latitude: -49.308683,
          longitude: -67.802669,
        },
        {
          value: 'COMODORO RIVADAVIA - EAVA EL CALAFATE',
          label: 'EAVA EL CALAFATE',
          latitude: -50.283806,
          longitude: -72.052556,
        },
        {
          value: 'COMODORO RIVADAVIA - EAVA PUERTO MADRYN',
          label: 'EAVA PUERTO MADRYN',
          latitude: -42.755278,
          longitude: -65.100889,
        },
        {
          value: 'COMODORO RIVADAVIA - EAVA ESQUEL',
          label: 'EAVA ESQUEL',
          latitude: -42.905944,
          longitude: -71.146528,
        },
        {
          value: 'COMODORO RIVADAVIA - EAVA VIEDMA',
          label: 'EAVA VIEDMA',
          latitude: -40.863056,
          longitude: -63.005556,
        },
        {
          value: 'COMODORO RIVADAVIA - EAVA ING. JACOBACCI',
          label: 'EAVA ING. JACOBACCI',
          latitude: -41.322281,
          longitude: -69.571778,
        },
      ],
    },
    {
      group: 'MENDOZA',
      options: [
        {
          value: 'MENDOZA',
          label: 'MENDOZA',
          latitude: -32.823972,
          longitude: -68.799278,
        },
      ],
    },
    {
      group: 'ACC MENDOZA',
      options: [
        {
          value: 'MENDOZA - MENDOZA (LOCAL)',
          label: 'MENDOZA (LOCAL)',
          latitude: -32.823972,
          longitude: -68.799278,
        },
        {
          value: 'MENDOZA - EAVA MALARGÜE',
          label: 'EAVA MALARGÜE',
          latitude: -35.485778,
          longitude: -69.58475,
        },
        {
          value: 'MENDOZA - EAVA SAN JUAN',
          label: 'EAVA SAN JUAN',
          latitude: -31.571,
          longitude: -68.422528,
        },
        {
          value: 'MENDOZA - EAVA VILLA REYNOLDS',
          label: 'EAVA VILLA REYNOLDS',
          latitude: -33.723667,
          longitude: -65.378417,
        },
        {
          value: 'MENDOZA - EAVA RINCÓN DE LOS SAUCES',
          label: 'EAVA RINCÓN DE LOS SAUCES',
          latitude: -37.390669,
          longitude: -68.926119,
        },
      ],
    },
    {
      group: 'CATAMARCA',
      options: [
        {
          value: 'CATAMARCA',
          label: 'CATAMARCA',
          latitude: -28.59305556,
          longitude: -65.75111111,
        },
      ],
    },
    {
      group: 'CONCORDIA',
      options: [
        {
          value: 'CONCORDIA',
          label: 'CONCORDIA',
          latitude: -31.29694444,
          longitude: -57.99666667,
        },
      ],
    },
    {
      group: 'ESCUELA DE AVIACIÓN MILITAR (FAA)',
      options: [
        {
          value: 'ESCUELA DE AVIACIÓN MILITAR (FAA)',
          label: 'ESCUELA DE AVIACIÓN MILITAR (FAA)',
          latitude: -31.443889,
          longitude: -64.283333,
        },
      ],
    },
    {
      group: 'CORRIENTES',
      options: [
        {
          value: 'CORRIENTES',
          label: 'CORRIENTES',
          latitude: -27.44555556,
          longitude: -58.76194444,
        },
      ],
    },
    {
      group: 'GOYA',
      options: [
        {
          value: 'GOYA',
          label: 'GOYA',
          latitude: -29.10595,
          longitude: -59.21874,
        },
      ],
    },
    {
      group: 'DON TORCUATO',
      options: [
        {
          value: 'DON TORCUATO',
          label: 'DON TORCUATO',
          latitude: -34.492778,
          longitude: -58.606944,
        },
      ],
    },
    {
      group: 'EL CALAFATE',
      options: [
        {
          value: 'EL CALAFATE',
          label: 'EL CALAFATE',
          latitude: -50.28,
          longitude: -72.05305556,
        },
      ],
    },
    {
      group: 'EL PALOMAR',
      options: [
        {
          value: 'EL PALOMAR',
          label: 'EL PALOMAR',
          latitude: -34.61,
          longitude: -58.6125,
        },
      ],
    },
    {
      group: 'ESQUEL',
      options: [
        {
          value: 'ESQUEL',
          label: 'ESQUEL',
          latitude: -42.90381,
          longitude: -71.13554,
        },
      ],
    },
    {
      group: 'GENERAL PICO',
      options: [
        {
          value: 'GENERAL PICO',
          label: 'GENERAL PICO',
          latitude: -35.695983,
          longitude: -63.758328,
        },
      ],
    },
    {
      group: 'FORMOSA',
      options: [
        {
          value: 'FORMOSA',
          label: 'FORMOSA',
          latitude: -26.21277778,
          longitude: -58.22805556,
        },
      ],
    },
    {
      group: 'GUALEGUAYCHÚ',
      options: [
        {
          value: 'GUALEGUAYCHÚ',
          label: 'GUALEGUAYCHÚ',
          latitude: -33.00555556,
          longitude: -58.61277778,
        },
      ],
    },
    {
      group: 'SAN SALVADOR DE JUJUY',
      options: [
        {
          value: 'SAN SALVADOR DE JUJUY',
          label: 'SAN SALVADOR DE JUJUY',
          latitude: -24.3925,
          longitude: -65.09777778,
        },
      ],
    },
    {
      group: 'JUNÍN',
      options: [
        {
          value: 'JUNÍN',
          label: 'JUNÍN',
          latitude: -34.545833,
          longitude: -60.930556,
        },
      ],
    },
    {
      group: 'LA PLATA',
      options: [
        {
          value: 'LA PLATA',
          label: 'LA PLATA',
          latitude: -34.969778,
          longitude: -57.893167,
        },
      ],
    },
    {
      group: 'LA RIOJA',
      options: [
        {
          value: 'LA RIOJA',
          label: 'LA RIOJA',
          latitude: -29.38055556,
          longitude: -66.79583333,
        },
      ],
    },
    {
      group: 'AEROCLUB LUJÁN',
      options: [
        {
          value: 'AEROCLUB LUJÁN',
          label: 'AEROCLUB LUJÁN',
          latitude: -34.551094,
          longitude: -59.078683,
        },
      ],
    },
    {
      group: 'MALARGÜE',
      options: [
        {
          value: 'MALARGÜE',
          label: 'MALARGÜE',
          latitude: -35.49527778,
          longitude: -69.57305556,
        },
      ],
    },
    {
      group: 'MARCOS JUAREZ',
      options: [
        {
          value: 'MARCOS JUAREZ',
          label: 'MARCOS JUAREZ',
          latitude: -32.683889,
          longitude: -62.1575,
        },
      ],
    },
    {
      group: 'MAR DEL PLATA',
      options: [
        {
          value: 'MAR DEL PLATA',
          label: 'MAR DEL PLATA',
          latitude: -37.93416667,
          longitude: -57.57333333,
        },
      ],
    },
    {
      group: 'MARIANO MORENO',
      options: [
        {
          value: 'MARIANO MORENO',
          label: 'MARIANO MORENO',
          latitude: -34.56,
          longitude: -58.78972222,
        },
      ],
    },
    {
      group: 'PUERTO IGUAZÚ / CATARATAS DEL IGUAZÚ',
      options: [
        {
          value: 'PUERTO IGUAZÚ / CATARATAS DEL IGUAZÚ',
          label: 'PUERTO IGUAZÚ / CATARATAS DEL IGUAZÚ',
          latitude: -25.73722,
          longitude: -54.47354,
        },
      ],
    },
    {
      group: 'MORÓN',
      options: [
        {
          value: 'MORÓN',
          label: 'MORÓN',
          latitude: -34.67916667,
          longitude: -58.64361111,
        },
      ],
    },
    {
      group: 'NECOCHEA',
      options: [
        {
          value: 'NECOCHEA',
          label: 'NECOCHEA',
          latitude: -38.489444,
          longitude: -58.816389,
        },
      ],
    },
    {
      group: 'NEUQUÉN',
      options: [
        {
          value: 'NEUQUÉN',
          label: 'NEUQUÉN',
          latitude: -38.94888889,
          longitude: -68.15583333,
        },
      ],
    },
    {
      group: 'PARANÁ',
      options: [
        {
          value: 'PARANÁ',
          label: 'PARANÁ',
          latitude: -31.79472222,
          longitude: -60.48027778,
        },
      ],
    },
    {
      group: 'PASO DE LOS LIBRES',
      options: [
        {
          value: 'PASO DE LOS LIBRES',
          label: 'PASO DE LOS LIBRES',
          latitude: -29.68805556,
          longitude: -57.15222222,
        },
      ],
    },
    {
      group: 'POSADAS',
      options: [
        {
          value: 'POSADAS',
          label: 'POSADAS',
          latitude: -27.38573,
          longitude: -55.97049,
        },
      ],
    },
    {
      group: 'PUERTO MADRYN',
      options: [
        {
          value: 'PUERTO MADRYN',
          label: 'PUERTO MADRYN',
          latitude: -42.75916667,
          longitude: -65.10277778,
        },
      ],
    },
    {
      group: 'RÍO CUARTO',
      options: [
        {
          value: 'RÍO CUARTO',
          label: 'RÍO CUARTO',
          latitude: -33.095864,
          longitude: -64.277395,
        },
      ],
    },
    {
      group: 'RÍO GALLEGOS',
      options: [
        {
          value: 'RÍO GALLEGOS',
          label: 'RÍO GALLEGOS',
          latitude: -51.60881,
          longitude: -69.31217,
        },
      ],
    },
    {
      group: 'RÍO GRANDE',
      options: [
        {
          value: 'RÍO GRANDE',
          label: 'RÍO GRANDE',
          latitude: -53.7776,
          longitude: -67.74952,
        },
      ],
    },
    {
      group: 'ROSARIO',
      options: [
        {
          value: 'ROSARIO',
          label: 'ROSARIO',
          latitude: -32.90361111,
          longitude: -60.78444444,
        },
      ],
    },
    {
      group: 'SALTA',
      options: [
        {
          value: 'SALTA',
          label: 'SALTA',
          latitude: -24.85972222,
          longitude: -65.48694444,
        },
      ],
    },
    {
      group: 'SAN CARLOS DE BARILOCHE',
      options: [
        {
          value: 'SAN CARLOS DE BARILOCHE',
          label: 'SAN CARLOS DE BARILOCHE',
          latitude: -41.15111111,
          longitude: -71.15777778,
        },
      ],
    },
    {
      group: 'SAN FERNANDO',
      options: [
        {
          value: 'SAN FERNANDO',
          label: 'SAN FERNANDO',
          latitude: -34.45454,
          longitude: -58.59091,
        },
      ],
    },
    {
      group: 'SAN JUAN',
      options: [
        {
          value: 'SAN JUAN',
          label: 'SAN JUAN',
          latitude: -31.57138889,
          longitude: -68.41833333,
        },
      ],
    },
    {
      group: 'SAN LUIS',
      options: [
        {
          value: 'SAN LUIS',
          label: 'SAN LUIS',
          latitude: -33.27222222,
          longitude: -66.35666667,
        },
      ],
    },
    {
      group: 'SAN RAFAEL',
      options: [
        {
          value: 'SAN RAFAEL',
          label: 'SAN RAFAEL',
          latitude: -34.58781667,
          longitude: -68.40358889,
        },
      ],
    },
    {
      group: 'SANTA FE',
      options: [
        {
          value: 'SANTA FE',
          label: 'SANTA FE',
          latitude: -31.71083333,
          longitude: -60.81138889,
        },
      ],
    },
    {
      group: 'SANTA ROSA',
      options: [
        {
          value: 'SANTA ROSA',
          label: 'SANTA ROSA',
          latitude: -36.58833333,
          longitude: -64.27583333,
        },
      ],
    },
    {
      group: 'SANTIAGO DEL ESTERO',
      options: [
        {
          value: 'SANTIAGO DEL ESTERO',
          label: 'SANTIAGO DEL ESTERO',
          latitude: -27.76555556,
          longitude: -64.31,
        },
      ],
    },
    {
      group: 'TANDIL',
      options: [
        {
          value: 'TANDIL',
          label: 'TANDIL',
          latitude: -37.23437778,
          longitude: -59.22858611,
        },
      ],
    },
    {
      group: 'TERMAS DE RÍO HONDO',
      options: [
        {
          value: 'TERMAS DE RÍO HONDO',
          label: 'TERMAS DE RÍO HONDO',
          latitude: -27.49662,
          longitude: -64.93596,
        },
      ],
    },
    {
      group: 'TRELEW',
      options: [
        {
          value: 'TRELEW',
          label: 'TRELEW',
          latitude: -43.21055556,
          longitude: -65.27027778,
        },
      ],
    },
    {
      group: 'SANTA ROSA DE CONLARA',
      options: [
        {
          value: 'SANTA ROSA DE CONLARA',
          label: 'SANTA ROSA DE CONLARA',
          latitude: -32.38472222,
          longitude: -65.18583333,
        },
      ],
    },
    {
      group: 'VIEDMA',
      options: [
        {
          value: 'VIEDMA',
          label: 'VIEDMA',
          latitude: -40.87027778,
          longitude: -62.99666667,
        },
      ],
    },
    {
      group: 'VILLA REYNOLDS',
      options: [
        {
          value: 'VILLA REYNOLDS',
          label: 'VILLA REYNOLDS',
          latitude: -33.73178,
          longitude: -65.37579,
        },
      ],
    },
    {
      group: 'AEROCLUB COMODORO RIVADAVIA',
      options: [
        {
          value: 'AEROCLUB COMODORO RIVADAVIA',
          label: 'AEROCLUB COMODORO RIVADAVIA',
          latitude: -45.904167,
          longitude: -67.558889,
        },
      ],
    },
    {
      group: 'OTRO - CCTE BUENOS AIRES',
      options: [
        {
          value: 'OTRO - CCTE BUENOS AIRES',
          label: 'OTRO - CCTE BUENOS AIRES',
          latitude: -34.7511,
          longitude: -58.4986,
        },
      ],
    },
    {
      group: 'OTRO - CCTE CABA',
      options: [
        {
          value: 'OTRO - CCTE CABA',
          label: 'OTRO - CCTE CABA',
          latitude: -34.6093056,
          longitude: -58.3750549,
        },
      ],
    },
    {
      group: 'OTRO - CCTE CÓRDOBA',
      options: [
        {
          value: 'OTRO - CCTE CÓRDOBA',
          label: 'OTRO - CCTE CÓRDOBA',
          latitude: -31.3308,
          longitude: -64.1472,
        },
      ],
    },
    {
      group: 'OTRO - CCTE SALTA',
      options: [
        {
          value: 'OTRO - CCTE SALTA',
          label: 'OTRO - CCTE SALTA',
          latitude: -24.7661,
          longitude: -65.4636,
        },
      ],
    },
    {
      group: 'OTRO - CCTE POSADAS',
      options: [
        {
          value: 'OTRO - CCTE POSADAS',
          label: 'OTRO - CCTE POSADAS',
          latitude: -27.3675,
          longitude: -55.9275,
        },
      ],
    },
    {
      group: 'OTRO - CCTE NEUQUÉN',
      options: [
        {
          value: 'OTRO - CCTE NEUQUÉN',
          label: 'OTRO - CCTE NEUQUÉN',
          latitude: -38.9689,
          longitude: -68.0414,
        },
      ],
    },
    {
      group: 'OTRO - CCTE COMODORO RIVADAVIA',
      options: [
        {
          value: 'OTRO - CCTE COMODORO RIVADAVIA',
          label: 'OTRO - CCTE COMODORO RIVADAVIA',
          latitude: -45.8739,
          longitude: -67.5661,
        },
      ],
    },
  ]
  return { airport }
}
