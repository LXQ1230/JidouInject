@echo off
REM 接受拖拽：第一个文件是 IDML，第二个是句读结果 MD
python "%~dp0inject.py" --idml "%~1" --result "%~2"
pause
