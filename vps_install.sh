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
if command -v dnf &> /dev/null; then
    echo "使用 dnf (CentOS/RHEL) 进行安装..."
    dnf install -y epel-release || true
    dnf config-manager --set-enabled crb || true
    dnf install -y curl git python3 python3-pip util-linux
    # CentOS 10 已移除旧版 Xvfb，现采用 xwayland-run 与 mutter 作为无头显示服务器
    dnf install -y --enablerepo=crb --enablerepo=epel xwayland-run mutter dbus-x11 || true
elif command -v yum &> /dev/null; then
    echo "使用 yum (CentOS 7/8) 进行安装..."
    yum install -y epel-release || true
    yum install -y curl git xorg-x11-server-Xvfb python3 python3-pip
elif command -v apt-get &> /dev/null; then
    echo "使用 apt-get (Ubuntu/Debian) 进行安装..."
    apt-get update -y
    apt-get install -y curl git xvfb python3 python3-pip python3-venv
else
    echo "❌ 无法识别的包管理器，请手动安装: curl, git, xvfb, python3"
fi

# 特别处理 CentOS 10 下 Xvfb 被废弃的问题
# 我们使用官方的 xwfb-run (由 xwayland-run 提供) 来代替 xvfb-run
if command -v xwfb-run &> /dev/null; then
    echo "检测到 xwayland-run 环境，正在建立 xvfb-run 的向后兼容代理脚本..."
cat <<'EOF' > /usr/local/bin/xvfb-run
#!/bin/bash
# CentOS 10 兼容层：将旧的 xvfb-run 调用转发给新的 xwfb-run，加上 -- 以防止劫持子命令的参数
exec xwfb-run -- "$@"
EOF
    chmod +x /usr/local/bin/xvfb-run
    echo "xvfb-run 兼容代理创建完成！"
    
elif ! command -v xvfb-run &> /dev/null; then
    # 如果不仅没有 xwfb-run，连原本的 xvfb-run 也不在（例如极度精简的 Ubuntu/Debian）
    if command -v Xvfb &> /dev/null; then
        echo "回退机制：系统存在 Xvfb 但无 xvfb-run，正在植入通用包装脚本..."
        curl -sL https://raw.githubusercontent.com/nexusformat/Xvfb-Run/master/xvfb-run -o /usr/local/bin/xvfb-run || true
        chmod +x /usr/local/bin/xvfb-run
    else
        echo "警告：系统中既没有 Xvfb 也没有 Wayland，无头模式可能无法运行！"
    fi
fi

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
echo "🐍 [3/4] 正在通过 uv 构建项目依赖 (含 Playwright)..."
uv sync --all-extras
uv pip install playwright-stealth

# 4. 安装 Playwright 及 Linux 系统字体/渲染库
echo "🌐 [4/4] 正在安装 Playwright 无头浏览器依赖..."
uv run python -m playwright install chromium

if command -v dnf &> /dev/null || command -v yum &> /dev/null; then
    echo "检测到 CentOS/RHEL，正在手动安装 Chromium 运行补丁包 (跳过 Playwright apt 脚本)..."
    PKG_MGR=$(command -v dnf || command -v yum)
    $PKG_MGR install -y \
        alsa-lib at-spi2-atk atk cairo cairo-gobject cups-libs dbus-libs \
        expat fontconfig freetype gdk-pixbuf2 glib2 gtk3 libdrm libgbm \
        libwayland-client libwayland-cursor libwayland-egl libxkbcommon \
        libX11 libXcomposite libXdamage libXext libXfixes libXi libXrandr \
        libXrender libXtst mesa-libgbm pango libXScrnSaver
else
    echo "检测到 Ubuntu/Debian，正在通过 Playwright 官方工具安装依赖..."
    uv run python -m playwright install-deps chromium
fi

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
