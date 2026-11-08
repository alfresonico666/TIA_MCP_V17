# Instalador de TIA_MCP_V17 para Claude Code (Windows PowerShell 5.1 o superior).
# Uso (desde la carpeta del repositorio):
#     powershell -ExecutionPolicy Bypass -File .\instalar.ps1
# Opciones:
#     -SoloLectura     registra el servidor en modo solo lectura (diagnostico sin escribir)
#     -SinRegistrar    instala pero no lo registra en Claude Code
param(
    [switch]$SoloLectura,
    [switch]$SinRegistrar
)
$ErrorActionPreference = "Stop"
$Raiz = $PSScriptRoot
$Venv = Join-Path $Raiz ".venv"
$PythonVenv = Join-Path $Venv "Scripts\python.exe"
$DllOpenness = "C:\Program Files\Siemens\Automation\Portal V17\PublicAPI\V17\Siemens.Engineering.dll"

function Paso($texto) { Write-Host "`n==> $texto" -ForegroundColor Cyan }
function Falla($texto) { Write-Host "ERROR: $texto" -ForegroundColor Red; exit 1 }

Paso "1/5 Comprobando TIA Portal V17 y Openness"
if (-not (Test-Path $DllOpenness)) {
    Falla "No se encontro $DllOpenness. Instala TIA Portal V17 con el componente Openness."
}
$grupos = whoami /groups | Out-String
if ($grupos -notmatch "Siemens TIA Openness") {
    Write-Host "AVISO: tu usuario no esta en el grupo 'Siemens TIA Openness'." -ForegroundColor Yellow
    Write-Host "  Ejecuta como administrador:  net localgroup `"Siemens TIA Openness`" $env:USERNAME /add"
    Write-Host "  y luego CIERRA SESION de Windows (o reinicia)."
}

Paso "2/5 Buscando Python 3.10 - 3.13"
$python = $null
foreach ($version in @("3.12", "3.13", "3.11", "3.10")) {
    try {
        & py "-$version" -c "import sys" 2>$null
        if ($LASTEXITCODE -eq 0) { $python = @("py", "-$version"); break }
    } catch { }
}
if ($null -eq $python) {
    Falla "No se encontro Python 3.10-3.13. Instalalo desde https://www.python.org (marca 'Add to PATH')."
}
Write-Host "Usando: $($python -join ' ')"

Paso "3/5 Creando entorno virtual e instalando dependencias"
if (-not (Test-Path $PythonVenv)) {
    & $python[0] $python[1] -m venv $Venv
}
& $PythonVenv -m pip install --quiet --upgrade pip
& $PythonVenv -m pip install --quiet -e "$Raiz[dev]"
if ($LASTEXITCODE -ne 0) {
    # Algunas redes cortan la descarga del indice de 'mcp' en PyPI: se instala desde la URL directa.
    Write-Host "Reintentando 'mcp' desde la URL directa del paquete..." -ForegroundColor Yellow
    $info = Invoke-RestMethod "https://pypi.org/pypi/mcp/json"
    $rueda = ($info.urls | Where-Object { $_.filename -like "*.whl" } | Select-Object -First 1).url
    & $PythonVenv -m pip install --quiet $rueda
    & $PythonVenv -m pip install --quiet -e "$Raiz[dev]"
    if ($LASTEXITCODE -ne 0) { Falla "No se pudieron instalar las dependencias." }
}

Paso "4/5 Verificando la instalacion"
& $PythonVenv -m tia_mcp --verificar

Paso "5/5 Registrando el servidor en Claude Code"
if ($SinRegistrar) {
    Write-Host "Omitido (-SinRegistrar)."
} elseif (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Host "No se encontro el comando 'claude'. Cuando instales Claude Code ejecuta:" -ForegroundColor Yellow
    Write-Host "  claude mcp add --scope user tia-v17 -- `"$PythonVenv`" -m tia_mcp"
} else {
    & claude mcp remove --scope user tia-v17 2>$null | Out-Null
    if ($SoloLectura) {
        & claude mcp add --scope user -e TIA_MCP_SOLO_LECTURA=1 tia-v17 -- $PythonVenv -m tia_mcp
    } else {
        & claude mcp add --scope user tia-v17 -- $PythonVenv -m tia_mcp
    }
    Write-Host "Registrado como 'tia-v17' (disponible en todos tus proyectos). Revisa con: claude mcp list"
}

Write-Host "`nListo. Abre Claude Code y escribe /mcp para ver 'tia-v17' conectado." -ForegroundColor Green
Write-Host "Rutas permitidas por defecto: $env:USERPROFILE\Proyectos\_copias y $env:USERPROFILE\Proyectos\*\tia_proyecto"
