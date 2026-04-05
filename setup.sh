#!/bin/bash
# OpenAI OAuth工具快速安装脚本

echo "=================================="
echo "OpenAI OAuth工具 - 快速安装"
echo "=================================="

# 检查Python版本
echo ""
echo "[1/4] 检查Python版本..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
echo "Python版本: $python_version"

if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到Python3，请先安装Python 3.8+"
    exit 1
fi

# 创建虚拟环境
echo ""
echo "[2/4] 创建虚拟环境..."
if [ ! -d ".venv_oauth" ]; then
    python3 -m venv .venv_oauth
    echo "✅ 虚拟环境创建成功"
else
    echo "✅ 虚拟环境已存在"
fi

# 激活虚拟环境
echo ""
echo "[3/4] 激活虚拟环境..."
source .venv_oauth/bin/activate

# 安装依赖
echo ""
echo "[4/4] 安装依赖..."
pip install --upgrade pip
pip install -r requirements_oauth.txt

# 安装Playwright浏览器
echo ""
echo "安装Playwright浏览器..."
python -m playwright install chromium

echo ""
echo "=================================="
echo "✅ 安装完成！"
echo "=================================="
echo ""
echo "使用方法:"
echo "1. 激活虚拟环境: source .venv_oauth/bin/activate"
echo "2. 运行简化示例: python simple_example.py"
echo "3. 运行完整流程: python openai_auto_register_oauth.py"
echo ""
echo "详细文档:"
echo "- README_OAUTH.md - 使用指南"
echo "- OPENAI_OAUTH_ANALYSIS.md - 详细分析"
echo "- SUMMARY.md - 项目总结"
echo ""
