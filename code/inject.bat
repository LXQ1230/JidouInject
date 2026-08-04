@echo off
REM 接受拖拽：第一个文件是 IDML，第二个是句读结果 MD
REM -X utf8: 强制 UTF-8 编码，避免 Unicode 符号触发 GBK 编码错误
python -X utf8 "%~dp0inject.py" --idml "%~1" --result "%~2"
pause
