@echo off
chcp 65001 >nul
rem Збирає ChessAssistant.exe на Windows. Потрібен Python 3.10+ (python.org, галочка "Add to PATH").
cd /d "%~dp0"
python -m pip install --upgrade pip || goto :error
python -m pip install -r requirements.txt pyinstaller==6.16.0 || goto :error
python -m PyInstaller --noconfirm --onefile --console --name ChessAssistant ^
  --hidden-import pynput.keyboard._win32 --hidden-import pynput.mouse._win32 ^
  chess_assistant.py || goto :error
echo.
echo Готово: dist\ChessAssistant.exe
echo Покладіть поруч stockfish.exe (https://stockfishchess.org/download/) і запускайте.
pause
exit /b 0
:error
echo Помилка збірки.
pause
exit /b 1
