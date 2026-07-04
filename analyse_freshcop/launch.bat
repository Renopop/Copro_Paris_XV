@echo off
REM ============================================================
REM  FRESHCOP - Module interactif (Windows)
REM  Double-cliquez sur ce fichier pour ouvrir l'application.
REM ============================================================
setlocal
cd /d "%~dp0"
chcp 65001 >nul

REM -- Choisir l'interpreteur Python (python, sinon py) --
set "PY=python"
where python >nul 2>nul || set "PY=py"
%PY% --version >nul 2>nul
if errorlevel 1 (
    echo.
    echo [FRESHCOP] Python est introuvable.
    echo Installez Python depuis https://www.python.org/downloads/
    echo en cochant "Add Python to PATH", puis relancez ce fichier.
    echo.
    pause
    exit /b 1
)

REM -- Installer les dependances au premier lancement (si Streamlit absent) --
%PY% -c "import streamlit" >nul 2>nul
if errorlevel 1 (
    echo.
    echo [FRESHCOP] Premiere utilisation : installation des dependances...
    echo Cela peut prendre une a deux minutes.
    echo.
    %PY% -m pip install -r requirements.txt
    if errorlevel 1 (
        echo.
        echo [FRESHCOP] Echec de l'installation des dependances.
        echo Verifiez votre connexion internet et reessayez.
        echo.
        pause
        exit /b 1
    )
)

REM -- Lancer l'application (le navigateur s'ouvre automatiquement) --
echo.
echo [FRESHCOP] Ouverture du module interactif dans votre navigateur...
echo Laissez cette fenetre ouverte. Fermez-la (ou Ctrl+C) pour arreter.
echo.
%PY% -m streamlit run app_interactif.py

echo.
echo [FRESHCOP] Application arretee.
pause
endlocal
