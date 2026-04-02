#!/bin/bash
# ========================================================
# Codex-Console VPS (Ubuntu/Debian) 一键安装初始化脚本
# 适用环境: Google Cloud Platform (GCP) 等 Ubuntu VPS
# 运行方式: sudo bash vps_install.sh
# ========================================================

set -e

echo "============================================="
echo "🚀 开始初始化 Codex-Console VPS 运行环境..."
echo "============================================="

# 1. 更新系统并安装必要的系统依赖 (Xvfb 用于虚拟屏幕头)
echo "📦 [1/4] 正在安装系统依赖 (git, xvfb, python 等)..."
apt-get update -y
apt-get install -y curl git xvfb python3 python3-pip python3-venv

# 2. 安装 uv 超级包管理器
echo "⚡ [2/4] 正在安装或更新 uv 包管理器..."
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
    echo "uv 安装成功！"
else
    echo "uv 已安装，跳过。"
fi

# 3. 同步和构建 Python 虚拟环境
echo "🐍 [3/4] 正在通过 uv 构建项目依赖..."
uv sync

# 4. 安装 Playwright 及 Linux 系统字体/渲染库
echo "🌐 [4/4] 正在安装 Playwright 无头浏览器依赖..."
uv run playwright install chromium
uv run playwright install-deps chromium

echo "============================================="
echo "🎉 环境配置全部彻底完成！"
echo "============================================="
echo ""
echo "💡 【使用说明】:"
echo "为了 100% 绕过 ChatGPT 的反爬检测，务必通过 xvfb-run 假装有屏幕来运行："
echo ""
echo "   xvfb-run uv run python batch_register.py"
echo ""
echo "============================================="
