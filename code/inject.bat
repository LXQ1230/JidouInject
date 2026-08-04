@echo off
REM Accept drag-and-drop: 1st file = IDML, 2nd file = punctuation result
REM -X utf8: force UTF-8 encoding to avoid GBK errors on Windows console
python -X utf8 "%~dp0inject.py" --idml "%~1" --result "%~2"
pause
