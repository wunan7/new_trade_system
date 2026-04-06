@echo off
REM ============================================================
REM  A股智能交易系统 - 每日自动化流水线
REM  运行时间: 每交易日 19:30 (在 finance_data 19:00 更新后)
REM
REM  流程: 因子计算 → 信号生成 → 风控过滤 → 仓位计算 → 模拟成交 → NAV记录
REM  非交易日自动跳过
REM
REM  Windows 任务计划程序配置:
REM    程序: C:\Users\wunan\projects\new_solution\scripts\run_trading_daily.bat
REM    触发器: 每天 19:30
REM ============================================================

cd /d C:\Users\wunan\projects\new_solution

echo ================================================== >> logs\trading_daily.log
echo [%date% %time%] Trading pipeline started >> logs\trading_daily.log

"C:\Users\wunan\AppData\Local\Programs\Python\Python311\python.exe" "C:\Users\wunan\projects\new_solution\scripts\run_daily.py" >> logs\trading_daily.log 2>&1

echo [%date% %time%] Trading pipeline finished (exit code: %ERRORLEVEL%) >> logs\trading_daily.log
