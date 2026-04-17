@echo off
chcp 65001 >nul
echo ========================================
echo   计时计费系统 - 打包脚本
echo ========================================
echo.

echo [1/3] 检查依赖...
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo 正在安装 PyInstaller...
    pip install pyinstaller
)

echo [2/3] 安装项目依赖...
pip install -r requirements.txt

echo [3/3] 开始打包...
pyinstaller build.spec --clean --noconfirm

echo.
if exist "dist\SoftwareUsageMeter.exe" (
    echo ========================================
    echo   打包成功！
    echo   输出文件：dist\SoftwareUsageMeter.exe
    echo ========================================
) else (
    echo ========================================
    echo   打包失败，请检查错误信息
    echo ========================================
)

echo.
pause
