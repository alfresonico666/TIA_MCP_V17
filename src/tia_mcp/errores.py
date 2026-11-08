"""Errores de dominio. Cada mensaje dice qué pasó y qué hacer, en español."""


class ErrorTia(Exception):
    """Base de todos los errores esperables del servidor (se muestran tal cual a Claude)."""


class OpennessNoDisponible(ErrorTia):
    """No se pudo cargar Siemens.Engineering.dll (TIA V17 u Openness no instalados)."""


class TiaNoConectado(ErrorTia):
    def __init__(self) -> None:
        super().__init__("No hay conexión con TIA Portal. Usa primero la herramienta `tia_sesion` "
                         "con action='conectar'.")


class SinProyectoAbierto(ErrorTia):
    def __init__(self) -> None:
        super().__init__("No hay proyecto abierto. Usa `tia_proyecto` con action='abrir', 'crear' "
                         "o 'desarchivar'.")


class RutaNoPermitida(ErrorTia):
    def __init__(self, ruta: object, permitidas: tuple[str, ...]) -> None:
        super().__init__(
            f"Ruta no permitida: {ruta}. Solo se trabaja sobre COPIAS de proyectos, en: "
            f"{'; '.join(permitidas)}. Copia el proyecto ahí (no lo muevas) o ajusta "
            f"TIA_MCP_RUTAS_PERMITIDAS."
        )


class ProyectoAjenoAbierto(ErrorTia):
    def __init__(self, ruta: object) -> None:
        super().__init__(
            f"TIA tiene abierto un proyecto fuera de las rutas permitidas: {ruta}. Por seguridad no "
            f"se toca. Pide al usuario que lo cierre (o que trabaje sobre una copia)."
        )


class NoEncontrado(ErrorTia):
    def __init__(self, que: str, nombre: str, sugerencias: list[str] | None = None) -> None:
        pista = f" ¿Quisiste decir: {', '.join(sugerencias)}?" if sugerencias else ""
        super().__init__(f"No existe {que} '{nombre}'.{pista}")


class EntradaInvalida(ErrorTia):
    """Parámetros o especificaciones mal formadas (JSON KOP, SCL, etc.)."""


class OperacionTiaFallida(ErrorTia):
    """TIA rechazó la operación (importación, compilación, creación...)."""
