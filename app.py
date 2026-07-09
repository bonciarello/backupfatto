"""BackupFatto — Generatore di script di backup personalizzati."""

import os
import re
from datetime import datetime
from flask import Flask, request, jsonify, render_template, send_from_directory

app = Flask(__name__)


# ── Routes ──────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/robots.txt")
def robots():
    return send_from_directory("static", "robots.txt")


@app.route("/sitemap.xml")
def sitemap():
    return send_from_directory("static", "sitemap.xml")


@app.route("/api/generate", methods=["POST"])
def generate():
    data = request.get_json(silent=True) or {}

    source = data.get("source", "").strip()
    destination = data.get("destination", "").strip()
    script_type = data.get("scriptType", "powershell")
    exclude_subfolders = data.get("excludeSubfolders", False)
    compress_zip = data.get("compressZip", False)
    filter_extensions = data.get("filterExtensions", False)
    extensions_raw = data.get("extensions", "").strip()

    # ── Validation ───────────────────────────────────────────────
    errors = []
    if not source:
        errors.append("Il percorso sorgente è obbligatorio.")
    if not destination:
        errors.append("Il percorso destinazione è obbligatorio.")
    if filter_extensions and not extensions_raw:
        errors.append("Specifica almeno un'estensione per attivare il filtro.")
    if script_type not in ("powershell", "batch"):
        errors.append("Tipo di script non valido.")

    # Sanitize extensions
    extensions = []
    if filter_extensions and extensions_raw:
        for ext in re.split(r"[,;\s]+", extensions_raw):
            ext = ext.strip().lstrip(".")
            if ext and re.match(r"^[a-zA-Z0-9_\-]+$", ext):
                extensions.append(ext)
        if not extensions:
            errors.append("Nessuna estensione valida. Usa lettere, numeri e trattini, separati da virgole.")

    if errors:
        return jsonify({"success": False, "errors": errors}), 400

    # ── Generate ─────────────────────────────────────────────────
    if script_type == "powershell":
        script = _generate_powershell(
            source, destination, exclude_subfolders, compress_zip,
            bool(extensions), extensions,
        )
    else:
        script = _generate_batch(
            source, destination, exclude_subfolders, compress_zip,
            bool(extensions), extensions,
        )

    return jsonify({
        "success": True,
        "script": script,
        "scriptType": script_type,
        "filename": _filename(script_type),
    })


# ── Script generators ───────────────────────────────────────────────

def _filename(script_type: str) -> str:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    ext = ".ps1" if script_type == "powershell" else ".bat"
    return f"backup_{ts}{ext}"


def _generate_powershell(source, dest, no_sub, zip_it, do_filter, exts):
    lines = []
    L = lines.append

    L("<#")
    L(".SYNOPSIS")
    L("    Script di backup generato da BackupFatto")
    L(".DESCRIPTION")
    L("    Copia i file dalla cartella sorgente alla destinazione")
    L("    applicando le regole specificate dall'utente.")
    L(".LINK")
    L("    https://cristianporco.it/app/backupfatto/")
    L("#>")
    L("")
    L("$ErrorActionPreference = \"Stop\"")
    L("")
    L("# ==========================================")
    L("#  CONFIGURAZIONE")
    L("# ==========================================")
    L(f"$Source      = \"{source}\"")
    L(f"$Destination = \"{dest}\"")
    L("$Timestamp   = Get-Date -Format \"yyyyMMdd_HHmmss\"")
    L("")
    L("# Crea la cartella di destinazione se non esiste")
    L("if (-not (Test-Path $Destination)) {")
    L("    New-Item -ItemType Directory -Path $Destination -Force | Out-Null")
    L("}")
    L("")
    L("Write-Host \"╔══════════════════════════════════════╗\" -ForegroundColor Cyan")
    L("Write-Host \"║  BackupFatto — Backup personalizzato  ║\" -ForegroundColor Cyan")
    L("Write-Host \"╚══════════════════════════════════════╝\" -ForegroundColor Cyan")
    L("Write-Host \"\"")
    L("Write-Host \"Sorgente:      $Source\" -ForegroundColor Gray")
    L("Write-Host \"Destinazione:  $Destination\" -ForegroundColor Gray")

    if do_filter:
        ext_str = ", ".join(f"*.{e}" for e in exts)
        L(f"Write-Host \"Filtro estensioni: {ext_str}\" -ForegroundColor Gray")
    if no_sub:
        L("Write-Host \"Sottocartelle:  ESCLUSE\" -ForegroundColor DarkYellow")
    if zip_it:
        L("Write-Host \"Compressione ZIP: SÌ\" -ForegroundColor Gray")
    L("Write-Host \"\"")
    L("")
    L("try {")

    # ── Copy logic ────────────────────────────────────────────
    L("")
    L("    Write-Host \"[1/2] Copia dei file in corso...\" -ForegroundColor Yellow")

    if do_filter:
        ext_include = ", ".join(f"\"*.{e}\"" for e in exts)
        if no_sub:
            L(f"    $Files = Get-ChildItem -Path $Source -Include {ext_include}")
        else:
            L(f"    $Files = Get-ChildItem -Path $Source -Recurse -Include {ext_include}")
        L("    if ($Files) {")
        L("        $Files | Copy-Item -Destination $Destination -Force -PassThru |")
        L("            ForEach-Object { Write-Host \"  Copiato: $($_.Name)\" -ForegroundColor DarkGray }")
        L("    } else {")
        L("        Write-Host \"  Nessun file corrispondente trovato.\" -ForegroundColor DarkYellow")
        L("    }")
    else:
        if no_sub:
            L("    $Files = Get-ChildItem -Path \"$Source\\*\" -File")
        else:
            L("    $Files = Get-ChildItem -Path \"$Source\\*\" -File -Recurse")
        L("    if ($Files) {")
        L("        $Files | Copy-Item -Destination $Destination -Force -PassThru |")
        L("            ForEach-Object { Write-Host \"  Copiato: $($_.Name)\" -ForegroundColor DarkGray }")
        L("    } else {")
        L("        Write-Host \"  Nessun file trovato nella sorgente.\" -ForegroundColor DarkYellow")
        L("    }")

    L("")
    L("    Write-Host \"Copia completata.\" -ForegroundColor Green")

    # ── ZIP logic ─────────────────────────────────────────────
    if zip_it:
        L("")
        L("    Write-Host \"[2/2] Compressione ZIP in corso...\" -ForegroundColor Yellow")
        L("    $ZipName = \"backup_$Timestamp.zip\"")
        L("    $ZipPath = Join-Path $Destination $ZipName")
        L("    $AllFiles = Get-ChildItem -Path $Destination -File | Where-Object { $_.Name -ne $ZipName }")
        L("    if ($AllFiles) {")
        L("        Compress-Archive -Path $AllFiles.FullName -DestinationPath $ZipPath -Force")
        L("        Write-Host \"Archivio creato: $ZipPath\" -ForegroundColor Green")
        L("        Write-Host \"Dimensione: $([math]::Round((Get-Item $ZipPath).Length / 1KB, 1)) KB\" -ForegroundColor Gray")
        L("    } else {")
        L("        Write-Host \"Nessun file da comprimere.\" -ForegroundColor DarkYellow")
        L("    }")
    else:
        L("    Write-Host \"[2/2] Saltato (compressione non richiesta)\" -ForegroundColor DarkGray")

    L("")
    L("    Write-Host \"\"")
    L("    Write-Host \"✓ Backup completato con successo!\" -ForegroundColor Green")
    L("    Write-Host \"  Ora: $(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')\" -ForegroundColor Gray")
    L("")
    L("} catch {")
    L("    Write-Host \"\"")
    L("    Write-Host \"✗ ERRORE durante il backup:\" -ForegroundColor Red")
    L("    Write-Host \"  $_\" -ForegroundColor Red")
    L("    exit 1")
    L("}")
    L("")
    L("# Tieni aperta la finestra se lanciato da explorer")
    L("if ($Host.Name -eq \"ConsoleHost\" -and $MyInvocation.Line -eq \"\") {")
    L("    Write-Host \"`nPremi un tasto per uscire...\" -ForegroundColor DarkGray")
    L("    $null = $Host.UI.RawUI.ReadKey(\"NoEcho,IncludeKeyDown\")")
    L("}")

    return "\n".join(lines)


def _generate_batch(source, dest, no_sub, zip_it, do_filter, exts):
    lines = []
    L = lines.append

    L("@echo off")
    L("setlocal enabledelayedexpansion")
    L("REM ==============================================")
    L("REM  BackupFatto — Script di backup personalizzato")
    L("REM  Generato il: " + datetime.now().strftime("%Y-%m-%d %H:%M"))
    L("REM  https://cristianporco.it/app/backupfatto/")
    L("REM ==============================================")
    L("")
    L("REM === CONFIGURAZIONE ===")
    L(f"set \"SOURCE={source}\"")
    L(f"set \"DEST={dest}\"")
    L("")
    L("REM === INTESTAZIONE ===")
    L("echo ╔══════════════════════════════════════╗")
    L("echo ║  BackupFatto — Backup personalizzato  ║")
    L("echo ╚══════════════════════════════════════╝")
    L("echo.")
    L("echo Sorgente:      %SOURCE%")
    L("echo Destinazione:  %DEST%")

    if do_filter:
        ext_str = ", ".join(f"*.{e}" for e in exts)
        L(f"echo Filtro estensioni: {ext_str}")
    if no_sub:
        L("echo Sottocartelle:  ESCLUSE")
    if zip_it:
        L("echo Compressione ZIP: SI")
    L("echo.")
    L("")
    L("REM === CREA DESTINAZIONE ===")
    L("if not exist \"%DEST%\" (")
    L("    echo Creazione cartella di destinazione...")
    L("    mkdir \"%DEST%\"")
    L("    if errorlevel 1 (")
    L("        echo ERRORE: impossibile creare la cartella di destinazione")
    L("        pause")
    L("        exit /b 1")
    L("    )")
    L(")")
    L("")
    L("REM === COPIA FILE ===")
    L("echo [1/2] Copia dei file in corso...")

    if do_filter:
        L("set \"COPIATI=0\"")
        for ext in exts:
            if no_sub:
                L(f"for %%f in (\"%SOURCE%\\*.{ext}\") do (")
            else:
                L(f"for /r \"%SOURCE%\" %%f in (*.{ext}) do (")
            L("    copy /y \"%%f\" \"%DEST%\\\" >nul 2>&1")
            L("    if not errorlevel 1 (")
            L("        echo   Copiato: %%~nxf")
            L("        set /a COPIATI+=1")
            L("    )")
            L(")")
        L("if %COPIATI%==0 echo   Nessun file corrispondente trovato.")
    else:
        if no_sub:
            L("for %%f in (\"%SOURCE%\\*\") do (")
            L("    if not exist \"%SOURCE%\\%%~nxf\\\" (")
            L("        copy /y \"%%f\" \"%DEST%\\\" >nul 2>&1")
            L("        if not errorlevel 1 echo   Copiato: %%~nxf")
            L("    )")
            L(")")
        else:
            L("xcopy \"%SOURCE%\\*\" \"%DEST%\\\" /E /I /H /Y")
            L("if errorlevel 1 (")
            L("    echo   Alcuni file potrebbero non essere stati copiati.")
            L(") else (")
            L("    echo   Copia completata con xcopy /E /I /H /Y")
            L(")")

    L("")
    L("echo Copia completata.")
    L("")

    # ── ZIP logic ─────────────────────────────────────────────
    if zip_it:
        L("REM === COMPRESSIONE ZIP ===")
        L("echo [2/2] Compressione ZIP in corso...")
        L("set ZIPNAME=backup_%date:~-4%%date:~-7,2%%date:~-10,2%_%time:~0,2%%time:~3,2%%time:~6,2%.zip")
        L("set ZIPNAME=%ZIPNAME: =0%")
        L("set \"ZIPPATH=%DEST%\\%ZIPNAME%\"")
        L("powershell -NoProfile -Command \"& { param($d,$z); if (Test-Path $d) { $files = Get-ChildItem -Path $d -File | Where-Object { $_.Name -ne (Split-Path $z -Leaf) }; if ($files) { Compress-Archive -Path $files.FullName -DestinationPath $z -Force } } }\" -d \"%DEST%\" -z \"%ZIPPATH%\"")
        L("if exist \"%ZIPPATH%\" (")
        L("    echo Archivio creato: %ZIPPATH%")
        L(") else (")
        L("    echo Nessun file da comprimere o errore nella compressione.")
        L(")")
    else:
        L("echo [2/2] Saltato (compressione non richiesta)")
    L("")
    L("REM === COMPLETATO ===")
    L("echo.")
    L("echo ✓ Backup completato!")
    L("echo.")
    L("pause")

    return "\n".join(lines)


# ── Main ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 4600))
    app.run(host="0.0.0.0", port=port, debug=False)
