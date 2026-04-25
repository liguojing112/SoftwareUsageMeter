@echo off
setlocal

echo ========================================
echo   SoftwareUsageMeter build script
echo ========================================
echo.

echo [1/4] Stop old SoftwareUsageMeter.exe processes...
taskkill /IM SoftwareUsageMeter.exe /F >nul 2>&1

echo [2/4] Install requirements...
pip install -r requirements.txt
if errorlevel 1 (
    echo Failed to install requirements.
    pause
    exit /b 1
)

echo [3/4] Build exe...
pyinstaller build.spec --clean --noconfirm
if errorlevel 1 (
    echo Build failed.
    pause
    exit /b 1
)

echo [4/4] Generate clean config.json...
python -c "import json; json.dump({'rate':1.0,'export_rate':1.0,'default_export_count':1,'admin_password':'8c6976e5b5410415bde908bd4dee15dfb167a9c873fc4bb8a81f6f2ab448a918','qr_code_path':'','wechat_qr_code_path':'','alipay_qr_code_path':'','wallpaper_path':'','process_name':'PixCake.exe','export_window_keywords':['\u5bfc\u51fa','Export'],'monitor_interval_ms':2000}, open('dist/config.json','w',encoding='utf-8'), ensure_ascii=False, indent=2); print('config.json OK')"
if errorlevel 1 (
    echo Failed to generate config.json.
    pause
    exit /b 1
)

echo.
if exist "dist\SoftwareUsageMeter.exe" (
    echo ========================================
    echo   Build succeeded!
    echo   Output: dist\SoftwareUsageMeter.exe
    echo   Output: dist\config.json
    echo ========================================
) else (
    echo ========================================
    echo   Build finished but exe not found
    echo ========================================
    pause
    exit /b 1
)

echo.
pause
