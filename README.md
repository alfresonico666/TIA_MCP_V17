# TIA_MCP_V17

Servidor **MCP** (Model Context Protocol) para que **Claude Code** programe, diagnostique y documente
proyectos de **Siemens TIA Portal V17** (S7-1200 / S7-1500) usando **TIA Openness**. Gratis y de código abierto.

- Programa en **KOP (Ladder)** y **SCL**, crea **UDT**, **PID_Compact**, tags y bloques, y **compila solo**.
- **Lee** escalones KOP como lógica en texto, calcula **referencias cruzadas**, **árbol de llamadas** y
  **diagnostica** problemas típicos (doble bobina, instancias compartidas, direcciones solapadas...).
- **Red PROFINET**: IP, nombres PROFINET, subred, asignar servos / lectores DMC / ET 200 al PLC, direcciones E/S.
- **Organiza tags** en tablas por categoría (LVDTs, finales de carrera, E/S...) con simulación previa.
- **Aprende** el estilo del equipo a partir de proyectos anteriores (`PERFIL_ESTILO.md`).
- **Seguro por diseño**: solo trabaja sobre copias, nunca descarga al PLC ni va online.

👉 Lista completa de lo que puede y no puede hacer: **[CAPACIDADES.md](CAPACIDADES.md)**

## Requisitos

| | |
|---|---|
| Windows 10/11 | Openness solo existe en Windows |
| TIA Portal **V17** con **Openness** | Viene en el instalador de TIA (componente "TIA Openness") |
| Usuario en el grupo **"Siemens TIA Openness"** | Luego cerrar sesión de Windows |
| Python **3.10 – 3.13** | https://www.python.org (marcar "Add to PATH") |
| [Claude Code](https://claude.com/claude-code) | El cliente que usa el MCP |

## Instalación (una vez por PC)

```powershell
git clone https://github.com/alfresonico666/TIA_MCP_V17.git
cd TIA_MCP_V17
powershell -ExecutionPolicy Bypass -File .\instalar.ps1
```

El instalador comprueba TIA y Openness, crea el entorno Python, instala dependencias, verifica la
instalación y registra el servidor en Claude Code como **`tia-v17`** (disponible en todos tus proyectos).
Con `-SoloLectura` lo registra en modo solo lectura (para diagnosticar sin modificar nada).

Comprobar:

```powershell
.venv\Scripts\python -m tia_mcp --verificar      # instalación
.venv\Scripts\python scripts\prueba_en_vivo.py   # prueba completa contra TIA (crea un proyecto en .pruebas\)
```

En Claude Code escribe `/mcp`: debe aparecer `tia-v17` conectado.

> **Primera conexión**: TIA muestra un aviso de seguridad de Openness pidiendo autorizar a `python.exe`.
> Responde **"Sí a todo"**.

## Uso

Habla con Claude en lenguaje natural, por ejemplo:

- *"Conéctate a TIA y abre la copia `C:\Users\yo\Proyectos\_copias\Linea3\Linea3.ap17`"*
- *"Haz un FB en KOP de arranque/paro con retención y un TON de 5 s de confirmación, y llámalo en el OB1"*
- *"Crea un UDT para motores y un FB en SCL que lo use"*
- *"Configura un PID_Compact para la temperatura del horno en el OB30"*
- *"¿Dónde se escribe `Motor_Bomba`? Haz un diagnóstico del programa"*
- *"Agrega el servo V90 a la red con IP 192.168.0.30 y nombre `servo-eje-x` y asígnalo al PLC"*
- *"Organiza los tags por categorías, primero muéstrame la simulación"*
- *"Aprende del proyecto `C:\...\_copias\Prensa2023.zap17` y programa igual"*

### Herramientas (12 herramientas, 62 acciones)

| Herramienta | Para qué |
|---|---|
| `tia_sesion` | Conectar / estado / desconectar |
| `tia_proyecto` | Abrir, crear, desarchivar, guardar, cerrar, archivar |
| `tia_hardware` | Dispositivos y CPU |
| `tia_red` | PROFINET: IP, nombres, subred, sistema IO, módulos, direcciones E/S |
| `tia_bloques` | Leer bloques (KOP como texto, SCL como fuente), XML, exportar para Git |
| `tia_programar` | Crear KOP (JSON), importar SCL/XML, DB de instancia, borrar |
| `tia_udt` | Tipos de datos de usuario |
| `tia_compilar` | Compilar y devolver errores con ubicación |
| `tia_tags` | Tablas, ocupación de direcciones, siguiente libre, organizar por categorías |
| `tia_tecnologia` | PID_Compact / PID_3Step / PID_Temp y sus parámetros |
| `tia_analisis` | Referencias cruzadas, árbol de llamadas, diagnóstico |
| `tia_conocimiento` | Aprender de proyectos anteriores y leer su perfil de estilo |

## Configuración (variables de entorno opcionales)

| Variable | Por defecto | Uso |
|---|---|---|
| `TIA_MCP_RUTAS_PERMITIDAS` | `%USERPROFILE%\Proyectos\_copias;%USERPROFILE%\Proyectos\*\tia_proyecto` | Dónde se permite abrir/crear proyectos (`;` separa, admite `*`) |
| `TIA_MCP_DIR_TIA` | `C:\Program Files\Siemens\Automation\Portal V17` | Instalación de TIA |
| `TIA_MCP_DIR_CONOCIMIENTO` | `%USERPROFILE%\Proyectos\_conocimiento_tia` | Salida de "aprender" (código de clientes: fuera del repo) |
| `TIA_MCP_SOLO_LECTURA` | vacío | `1` = no permite escribir |

Para cambiarlas: `claude mcp add --scope user -e TIA_MCP_RUTAS_PERMITIDAS="D:\Copias" tia-v17 -- <repo>\.venv\Scripts\python.exe -m tia_mcp`

## Arquitectura

```
src/tia_mcp/
├─ herramientas/   capa MCP delgada: una herramienta con `action` por área (sin lógica de negocio)
├─ openness/       ÚNICA capa que toca .NET/TIA (hilo STA dedicado, sesión, proyecto, bloques, tags, red...)
├─ simaticml/      Python puro: generador KOP (JSON → XML), lector XML → lógica en texto, validador XSD
├─ analisis/       Python puro: referencias, árbol de llamadas, diagnóstico, direcciones, estilo, organizar tags
├─ scl/            Python puro: verificación previa y usos de operandos en SCL
├─ seguridad.py    guardia de rutas (solo copias)
└─ servidor.py     arma el servidor y registra las herramientas
```

Decisiones tomadas a partir de otros MCP de TIA (TiaCommander, heilingbrunner/tiaportal-mcp, eponce00/tiaopen-mcp, Macsion):
herramientas agrupadas por `action` (menos contexto para el LLM), respuestas compactas con tope y aviso de truncado,
errores como `isError` con mensaje accionable, **un solo hilo STA** para Openness (TIA rechaza llamadas cruzadas),
respaldo y restauración al sobrescribir, logging solo a stderr (stdout es el canal MCP) y pruebas offline contra
los XSD oficiales. Formatos de KOP verificados con exports reales de V17.

## Desarrollo

```powershell
.venv\Scripts\python -m pytest                    # pruebas offline (generador, lector, análisis, seguridad)
.venv\Scripts\ruff check src tests scripts        # estilo
.venv\Scripts\python scripts\prueba_en_vivo.py    # contra TIA real
```

- Nueva regla de diagnóstico: una función en `analisis/diagnostico.py` agregada a `REGLAS`.
- Nueva instrucción KOP: agrégala a `simaticml/kop/instrucciones.py` copiando pines de un export real de V17.
- Cada función nueva o limitación descubierta se documenta en [CAPACIDADES.md](CAPACIDADES.md).

## Licencia

MIT. No afiliado a Siemens. "SIMATIC", "TIA Portal" y "STEP 7" son marcas de Siemens AG.
