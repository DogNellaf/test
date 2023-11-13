@echo off
IF NOT EXIST venv (
    py -m pip install venv
    py -m venv venv
)

call venv\Scripts\Activate.bat
pip install -r requirements.txt

python main.py

pause