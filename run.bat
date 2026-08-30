@echo off
setlocal
chcp 65001 >nul
title StockPulse Studio
cd /d "%~dp0"

echo ========================================================
echo   StockPulse Studio - 智能股票趋势与多维选股系统
echo   支持市场：A股 / 美股 / ETF
echo ========================================================
echo.

set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe"
if exist "%PYTHON_EXE%" goto :run

where py >nul 2>&1
if not errorlevel 1 (
    py -3 -c "import sys" >nul 2>&1
    if not errorlevel 1 goto :run_py
)

where python >nul 2>&1
if not errorlevel 1 (
    python -c "import sys" >nul 2>&1
    if not errorlevel 1 goto :run_python
)

echo [错误] 未找到可用的 Python 3。
echo 请安装 Python 3.10 或更高版本，并重新运行本脚本。
goto :failed

:run
"%PYTHON_EXE%" -c "import streamlit" >nul 2>&1
if errorlevel 1 goto :missing_deps
"%PYTHON_EXE%" -m streamlit run app.py --server.port 8501 --browser.gatherUsageStats false
goto :done

:run_py
py -3 -c "import streamlit" >nul 2>&1
if errorlevel 1 goto :missing_deps
py -3 -m streamlit run app.py --server.port 8501 --browser.gatherUsageStats false
goto :done

:run_python
python -c "import streamlit" >nul 2>&1
if errorlevel 1 goto :missing_deps
python -m streamlit run app.py --server.port 8501 --browser.gatherUsageStats false
goto :done

:missing_deps
echo [错误] 当前 Python 环境缺少项目依赖。
echo 请先在本目录执行：pip install -r requirements.txt

:failed
pause
exit /b 1

:done
if errorlevel 1 pause
endlocal
