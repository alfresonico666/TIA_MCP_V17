# Capacidades de TIA_MCP_V17

Lista viva de **lo que el MCP puede hacer, lo que no, y por qué**. Mantenla al día en cada versión.
Leyenda: ✅ disponible · 🧪 disponible pero sin verificar en todos los casos · ❌ fuera de alcance · 🗺️ planeado.

> Todo trabaja sobre **copias** de proyectos y **offline**. El MCP **nunca** descarga a un PLC ni se conecta online:
> la descarga la hace siempre una persona desde TIA Portal.

## 1. Sesión y proyecto — `tia_sesion`, `tia_proyecto`

| Función | Estado | Notas |
|---|---|---|
| Conectarse a un TIA abierto o iniciarlo (con o sin interfaz) | ✅ | La 1.ª vez TIA pide autorizar a Python: "Sí a todo" |
| Abrir proyecto `.ap17` (normal o **solo lectura**) | ✅ | Solo en rutas permitidas (copias) |
| Crear proyecto nuevo | ✅ | Nombres sin acentos ni espacios |
| Desarchivar `.zap17` → copia en ruta permitida | ✅ | El `.zap17` original no se toca |
| Guardar, cerrar, archivar `.zap17` (entregas / GitHub Release) | ✅ | |
| Bloqueo si TIA tiene abierto un proyecto que no es copia | ✅ | Regla de seguridad |
| Proyectos V13–V16 (actualizar a V17) | ❌ | El equipo solo usa V17 |

## 2. Hardware y red PROFINET — `tia_hardware`, `tia_red`

| Función | Estado | Notas |
|---|---|---|
| Listar dispositivos y módulos (referencia, firmware, slot, IP) | ✅ | |
| Agregar CPU por referencia (ej. `6ES7 214-1BG40-0XB0/V4.5`) | ✅ | |
| Ver interfaces: IP, máscara, nombre PROFINET, subred, sistema IO, rol | ✅ | |
| Cambiar IP / máscara / **nombre PROFINET** | ✅ | Configuración del proyecto, no del equipo real |
| Crear/conectar subred (PN/IE_1) | ✅ | |
| **Asignar un equipo al sistema IO del PLC** (servo, lector DMC, ET 200, variador) | ✅ | Lo conecta a la subred del PLC si hace falta |
| Agregar equipo por referencia de catálogo | ✅ | SINAMICS V90/S210 requieren su HSP instalado en TIA |
| Agregar equipo por **GSDML** (`GSD:archivo.xml/DAP/...`) | 🧪 | El GSDML debe estar instalado en TIA |
| Insertar módulos/submódulos (p. ej. **telegramas** de un drive, módulos ET 200) | 🧪 | `insertar_modulo` con slot |
| Ver y **cambiar direcciones E/S** (%I/%Q) de cada módulo | ✅ | |
| Asignar nombre PROFINET al equipo real / buscar equipos en la red | ❌ | Requiere ir online |
| Parámetros internos de drives (Startdrive, V-ASSISTANT) | ❌ | No los expone Openness V17 |

## 3. Programa — `tia_bloques`, `tia_programar`, `tia_compilar`

| Función | Estado | Notas |
|---|---|---|
| Listar bloques (tipo, número, lenguaje, consistencia, carpeta) | ✅ | |
| **Leer KOP/FUP como lógica en texto** (`"Motor" := ("Marcha" OR "Motor") AND ...`) | ✅ | Para que Claude entienda y diagnostique escalones |
| Leer SCL/STL/DB como fuente | ✅ | |
| XML SimaticML crudo de cualquier bloque | ✅ | |
| **Crear FB/FC/OB en KOP** desde JSON | ✅ | Validado contra XSD V17 antes de importar |
| KOP: contactos NA/NC, bobinas, set/reset, serie, paralelo, flancos P/N | ✅ | |
| KOP: comparadores (==, <>, >, >=, <, <=) | ✅ | |
| KOP: **TON / TOF / TP**, **CTU / CTD**, R_TRIG, SR / RS | ✅ | Multiinstancia (#T1) o DB individual |
| KOP: MOVE, ADD, SUB, MUL, DIV, CONV, NORM_X, SCALE_X | ✅ | |
| KOP: CTUD, F_TRIG | 🧪 | Formato por analogía, sin export real V17 |
| KOP: llamadas a FB (con instancia) y FC, con tipos leídos de TIA | ✅ | |
| KOP: caja **PID_Compact** | 🧪 | La versión depende del firmware |
| **Importar SCL** (FB, FC, OB, DB, varios bloques a la vez) | ✅ | Con verificación previa (bloques sin cerrar, acentos) |
| Importar XML SimaticML | ✅ | |
| Crear DB de instancia, borrar bloques, carpetas de bloques | ✅ | |
| **Respaldo automático**: si un bloque existente no compila tras cambiarlo, se restaura | ✅ | |
| **Compilar** y devolver errores con ubicación (bloque › red) | ✅ | Claude los corrige y reintenta |
| Arrays con índice en KOP generado | ❌ | Usar SCL para esa lógica |
| GRAPH, STL nuevo, bloques de seguridad (F) | ❌ | Openness V17 no los crea/edita de forma fiable |
| Bloques con protección de know-how | ❌ | Se listan pero no se leen |

## 4. Tipos de datos de usuario (UDT) — `tia_udt`

| Función | Estado | Notas |
|---|---|---|
| Listar y leer UDT (estructura, valores iniciales, comentarios) | ✅ | |
| **Crear / modificar UDT** con SCL (`TYPE "UDT_Motor" ... END_TYPE`) | ✅ | Varios a la vez |
| Usar UDT en interfaces KOP (`"tipo": "\"UDT_Motor\""`) y en tags | ✅ | El tipo va entre comillas |
| Borrar UDT | ✅ | |

## 5. Variables (tags) — `tia_tags`

| Función | Estado | Notas |
|---|---|---|
| Listar tablas, leer tabla, buscar por nombre/dirección/comentario | ✅ | |
| Crear o actualizar tags con comentario (idempotente) | ✅ | |
| Borrar tags | ✅ | |
| **Ocupación de direcciones y solapamientos** (%I/%Q/%M) | ✅ | |
| **Siguiente dirección libre** por área y tipo | ✅ | |
| **Organizar tags en tablas por categoría** (LVDTs, finales de carrera, pulsadores, pilotos, válvulas, motores, analógicas, E/S digitales, marcas) | ✅ | Reglas por **prefijo, texto en el nombre, comentario, dirección (`%IW*`) o tipo**; la primera que coincide gana |
| └ Modo **simulación** (muestra el plan sin tocar nada) | ✅ | Es el modo por defecto; `aplicar=true` lo ejecuta |
| └ Reglas propias o sugeridas | ✅ | `reglas_sugeridas` muestra las de fábrica |
| Renombrar tags | ❌ | Openness V17 no lo permite (nombre de solo lectura) |
| Constantes de usuario, tablas de observación/forzado | 🗺️ | |

## 6. Regulación PID y objetos tecnológicos — `tia_tecnologia`

| Función | Estado | Notas |
|---|---|---|
| Crear **PID_Compact**, PID_3Step, PID_Temp | ✅ | Indicar versión según firmware |
| Leer y **escribir parámetros** (límites, escalado, ganancias) | 🧪 | Muestra valor anterior → nuevo |
| Llamada al PID en OB de alarma cíclica (OB30) por SCL o KOP | ✅ | |
| Autoajuste (puesta en servicio) del PID | ❌ | Requiere ir online |
| Ejes de movimiento (TO_PositioningAxis), contadores rápidos | 🗺️ | |

## 7. Diagnóstico y referencias cruzadas — `tia_analisis`

Openness V17 **no** tiene API de referencias cruzadas: el MCP las calcula leyendo todos los bloques
(KOP/FUP por XML y SCL por su fuente).

| Función | Estado | Notas |
|---|---|---|
| **Referencias cruzadas** de un operando (lee / escribe / instancia, bloque y red) | ✅ | Incluye miembros `"DB".campo` |
| Quién llama a un bloque y con qué instancia | ✅ | |
| **Árbol de llamadas** desde los OB | ✅ | Detecta recursión |
| Bloques nunca llamados | ✅ | |
| Diagnóstico: **doble bobina**, set sin reset, **instancia compartida**, marcas leídas sin escribir, **direcciones solapadas**, bloques no llamados, inconsistentes, DB de instancia huérfanos, redes vacías, tags sin uso | ✅ | Cada regla es una función: fácil de ampliar |
| Estado online / valores en vivo / búfer de diagnóstico | ❌ | Requiere ir online |

## 8. Aprender de proyectos anteriores — `tia_conocimiento`

| Función | Estado | Notas |
|---|---|---|
| **Aprender** de un `.ap17` (copia) o `.zap17`: se abre en solo lectura y se exporta todo | ✅ | Nunca se guarda el proyecto |
| `PERFIL_ESTILO.md`: prefijos y estilo de nombres, estructura, % comentado, instrucciones más usadas, multiinstancia vs DB, árbol de llamadas, redes de ejemplo | ✅ | Claude lo lee antes de programar |
| Exportar el programa (XML + `.scl` + `.txt` legible + UDT + tags) para **versionarlo en Git** | ✅ | `tia_bloques` → `exportar_todo` |

## 9. Seguridad (por diseño)

- ✅ Solo abre/crea proyectos en **rutas permitidas** (`_copias`, `*/tia_proyecto`, configurable).
- ✅ Se niega a tocar un proyecto abierto que no sea copia.
- ✅ Modo **solo lectura** del servidor (`TIA_MCP_SOLO_LECTURA=1`) para diagnosticar sin riesgo.
- ❌ **Descarga al PLC, ir online, forzar valores, RUN/STOP**: no existen en el MCP y no se agregarán.

## 10. Planeado 🗺️

- Tablas de observación y de forzado (solo edición offline).
- Librerías globales y tipos de librería.
- Textos de alarma y listas de textos.
- Ejes de movimiento y objetos tecnológicos de conteo.
- Plantillas propias de bloques KOP a partir de proyectos aprendidos.
