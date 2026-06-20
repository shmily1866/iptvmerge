@echo off
echo ===================================================
echo   AptvMerge Dockerized - Local Windows Test Script
echo ===================================================
echo.
echo 1. Installing requirements...
pip install -r requirements.txt

echo.
echo 2. Starting Web Service...
echo Please open your browser and navigate to: http://127.0.0.1:38080
echo.
python main.py

pause
