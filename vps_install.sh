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
    dnf install -y curl git python3 python3-pip util-linux xorg-x11-xauth
    dnf install -y --enablerepo=crb --enablerepo=epel xorg-x11-server-Xvfb xvfb || true
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

# 特别处理 CentOS 下 xvfb-run 脚本缺失的问题 (RHEL/CentOS 常见坑)
if ! command -v xvfb-run &> /dev/null; then
    if command -v Xvfb &> /dev/null; then
        echo "检测到 Xvfb 已安装但缺少 xvfb-run 脚本，正在植入通用包装脚本..."
        cat <<'EOF' > /usr/local/bin/xvfb-run
#!/bin/bash
# Build-Depends on xvfb, xbase-clients, and xfonts-base.
set -e
PROGNAME=xvfb-run
SERVERNUM=99
AUTHFILE=""
ERRORFILE=/dev/null
STARTWAIT=3
XVFBARGS="-screen 0 1280x1024x24 -ac +extension GLX +render -noreset"
LISTENTCP="-nolisten tcp"
XAUTHPROTO=.

# Find a free server number by looking at .X*-lock files in /tmp.
find_free_servernum() {
    i=$SERVERNUM
    while [ -f /tmp/.X$i-lock ]; do
        i=$(($i + 1))
    done
    echo $i
}

# Simple parse of command line for common options
while [ $# -gt 0 ]; do
    case "$1" in
        -a|--auto-servernum) SERVERNUM=$(find_free_servernum) ;;
        -n|--server-num) SERVERNUM="$2"; shift ;;
        -s|--server-args) XVFBARGS="$2"; shift ;;
        -w|--wait) STARTWAIT="$2"; shift ;;
        --) shift; break ;;
        -*) ;; # skip unknown options
        *) break ;;
    esac
    shift
done

if [ -z "$*" ]; then
    echo "Usage: xvfb-run [options] command"
    exit 2
fi

if ! command -v xauth >/dev/null; then
    echo "error: xauth command not found"
    exit 3
fi

if [ -z "$AUTHFILE" ]; then
    XVFB_RUN_TMPDIR="$(mktemp --directory --tmpdir xvfb-run.XXXXXX)"
    AUTHFILE="$XVFB_RUN_TMPDIR/Xauthority"
fi

MCOOKIE=$(mcookie)
XAUTHORITY=$AUTHFILE xauth source - << EOX >>"$ERRORFILE" 2>&1
add :$SERVERNUM $XAUTHPROTO $MCOOKIE
EOX

XAUTHORITY=$AUTHFILE Xvfb ":$SERVERNUM" $XVFBARGS $LISTENTCP >>"$ERRORFILE" 2>&1 &
XVFBPID=$!
sleep "$STARTWAIT"

set +e
DISPLAY=:$SERVERNUM XAUTHORITY=$AUTHFILE "$@"
RETVAL=$?
set -e

kill $XVFBPID
rm -rf "$XVFB_RUN_TMPDIR"
exit $RETVAL
EOF
        chmod +x /usr/local/bin/xvfb-run
        echo "xvfb-run 脚本修复完成！"
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
