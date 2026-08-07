@echo off
rem ============================================================
rem  IDML 句读回注工具 — 一键重新打包脚本（Nuitka）
rem  产物: dist\IDML句读回注工具.exe （单文件，无 Python 依赖）
rem  前置: 已创建打包 venv（Python 3.12 + tkinter + nuitka）:
rem        C:\Users\Admin\.workbuddy\binaries\python\envs\pack312
rem  说明: 首次运行会自动下载 MinGW64 编译器，耗时较长属正常。
rem ============================================================
chcp 65001 >nul
set PY=C:\Users\Admin\.workbuddy\binaries\python\envs\pack312\Scripts\python.exe
if not exist "%PY%" (
    echo [错误] 打包 venv 不存在，请先执行:
    echo   "C:\Users\Admin\AppData\Local\Programs\Python\Python312\python.exe" -m venv "C:\Users\Admin\.workbuddy\binaries\python\envs\pack312"
    echo   "C:\Users\Admin\.workbuddy\binaries\python\envs\pack312\Scripts\pip.exe" install nuitka ordered-set zstandard
    pause
    exit /b 1
)

cd /d "%~dp0"
"%PY%" -m nuitka ^
    --onefile ^
    --windows-console-mode=disable ^
    --enable-plugin=tk-inter ^
    --mingw64 ^
    --assume-yes-for-downloads ^
    --onefile-tempdir-spec="{TEMP}/jd_onefile_{PID}_{TIME_US}" ^
    --output-dir="%~dp0..\dist" ^
    --product-name="IDML句读回注工具" ^
    --product-version="1.5.5" ^
    --file-description="IDML 句读结果回注工具（图形界面 + 拖拽命令行 + 窗口拖拽）" ^
    --output-filename="IDML句读回注工具.exe" ^
    launcher.py

echo.
echo ============================================================
echo 打包完成，产物位于: %~dp0..\dist\IDML句读回注工具.exe
echo ============================================================
pause
