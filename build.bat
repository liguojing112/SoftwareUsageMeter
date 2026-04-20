@echo off
setlocal

echo ========================================
echo   SoftwareUsageMeter build script
echo ========================================
echo.

echo [1/5] Stop old SoftwareUsageMeter.exe processes...
taskkill /IM SoftwareUsageMeter.exe /F >nul 2>&1

echo [2/5] Remove old dist\SoftwareUsageMeter.exe if present...
if exist "dist\SoftwareUsageMeter.exe" (
    attrib -r -s -h "dist\SoftwareUsageMeter.exe" >nul 2>&1
    del /F /Q "dist\SoftwareUsageMeter.exe" >nul 2>&1
)

echo [3/5] Check PyInstaller...
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo Installing PyInstaller...
    pip install pyinstaller
)

echo [4/5] Install project requirements...
pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install requirements.
    pause
    exit /b 1
)

echo [5/5] Build exe...
pyinstaller build.spec --clean --noconfirm
if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

echo.
if exist "dist\SoftwareUsageMeter.exe" (
    echo ========================================
    echo   Build succeeded
    echo   Output: dist\SoftwareUsageMeter.exe
    echo ========================================
) else (
    echo ========================================
    echo   Build finished but exe was not found
    echo ========================================
    pause
    exit /b 1
)

echo.
pause
