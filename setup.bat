@echo off
REM OpenAI OAuth工具快速安装脚本 (Windows)

echo ==================================
echo OpenAI OAuth工具 - 快速安装
echo ==================================

REM 检查Python版本
echo.
echo [1/4] 检查Python版本...
python --version
if errorlevel 1 (
    echo ❌ 未找到Python，请先安装Python 3.8+
    pause
    exit /b 1
)

REM 创建虚拟环境
echo.
echo [2/4] 创建虚拟环境...
if not exist ".venv_oauth" (
    python -m venv .venv_oauth
    echo ✅ 虚拟环境创建成功
) else (
    echo ✅ 虚拟环境已存在
)

REM 激活虚拟环境
echo.
echo [3/4] 激活虚拟环境...
call .venv_oauth\Scripts\activate.bat

REM 安装依赖
echo.
echo [4/4] 安装依赖...
python -m pip install --upgrade pip
pip install -r requirements_oauth.txt

REM 安装Playwright浏览器
echo.
echo 安装Playwright浏览器...
python -m playwright install chromium

echo.
echo ==================================
echo ✅ 安装完成！
echo ==================================
echo.
echo 使用方法:
echo 1. 激活虚拟环境: .venv_oauth\Scripts\activate.bat
echo 2. 运行简化示例: python simple_example.py
echo 3. 运行完整流程: python openai_auto_register_oauth.py
echo.
echo 详细文档:
echo - README_OAUTH.md - 使用指南
echo - OPENAI_OAUTH_ANALYSIS.md - 详细分析
echo - SUMMARY.md - 项目总结
echo.
pause
