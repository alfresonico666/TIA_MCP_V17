# CLAUDE.md – TIA_MCP_V17

Servidor MCP en Python (SDK `mcp` 2.x, `MCPServer`) + pythonnet sobre TIA Portal V17 Openness.
Usuario: programador PLC Siemens. Responder **en español** y explicar paso a paso.

## Comandos
- Pruebas offline: `.venv\Scripts\python -m pytest`
- Linter: `.venv\Scripts\ruff check src tests`
- Verificar instalación: `.venv\Scripts\python -m tia_mcp --verificar`
- Prueba en vivo con TIA: `.venv\Scripts\python scripts\prueba_en_vivo.py [--interfaz]`

## Reglas de arquitectura
1. Solo `src/tia_mcp/openness/` importa .NET/Openness. `simaticml/`, `analisis/`, `scl/` son Python puro y llevan pruebas.
2. `herramientas/` es una capa delgada: valida parámetros, llama servicios, formatea texto. Sin lógica de negocio.
3. Toda llamada a Openness pasa por `EjecutorTia` (un solo hilo STA). Nunca llamar Openness desde otro hilo.
4. Nada de `print` en el servidor: stdout es el canal MCP. Logging a stderr.
5. Errores esperables = subclases de `ErrorTia` con mensaje accionable en español.
6. Nuevas instrucciones KOP: copiar pines/plantillas de un export REAL de V17 y marcar `confirmado`.
7. Actualizar `CAPACIDADES.md` con cada función nueva o limitación descubierta.

## Seguridad (no negociable)
- Nunca agregar descarga al PLC, ir online, forzar ni RUN/STOP.
- Solo abrir/crear proyectos en rutas permitidas (`seguridad.GuardiaRutas`).
- Nunca subir a GitHub proyectos `.ap17/.zap17`, `.pruebas/` ni exportaciones de clientes.

## Versiones
Tag git + GitHub Release `vN_DescripcionSinEspaciosNiAcentos` (ej. `v1_ServidorMCPBase`).

## Notas Openness V17 (aprendidas)
- No hay API de CrossReference: se calcula en `analisis/referencias.py`.
- `GenerateOptions.None` → `getattr(GenerateOptions, "None")` en Python.
- Export no sobrescribe: borrar el archivo antes. Bloques inconsistentes no se exportan: compilar antes.
- PContact/NContact usan el pin `pre` (no `in`). Temporizadores/contadores/PID son `<Part Version=..>` con `<Instance>`.
- OB nuevos de usuario: número libre ≥ 123 (o el fijo del tipo, p. ej. OB30 alarma cíclica).
