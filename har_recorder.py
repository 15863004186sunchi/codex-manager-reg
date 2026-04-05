"""
HAR 录制工具 — 录制 OpenAI 注册/登录/OAuth 全流程

用法:
    python har_recorder.py
    python har_recorder.py --proxy http://127.0.0.1:7890
    python har_recorder.py --url https://chatgpt.com/ --timeout 15

录制完成后将生成的 .har 文件发给 Claude 分析。

工作原理:
    使用 Playwright 内置的 context.record_har() 捕获浏览器全部 HTTP 流量
    (包括 XHR/fetch/重定向/iframe)，输出标准 HAR 1.2 格式。
    同时集成了 semi_auto_reg.py 的 OAuth 浮动按钮和本地回调服务器，
    支持完整的注册 → 登录 → OAuth 授权全流程录制。
"""

import os
import sys
import json
import time
import queue
import shutil
import socket
import tempfile
import threading
import datetime
import argparse
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# 将项目根目录添加到 sys.path，以便导入项目模块
sys.path.insert(0, os.getcwd())

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("❌ 需要安装 playwright: pip install playwright && playwright install chromium")
    sys.exit(1)

try:
    from src.core.openai.oauth import generate_oauth_url, submit_callback_url
    from src.config.constants import OAUTH_REDIRECT_URI
    _OAUTH_AVAILABLE = True
except Exception as e:
    print(f"[Warning] OAuth 模块加载失败，OAuth 功能将不可用: {e}")
    _OAUTH_AVAILABLE = False
    OAUTH_REDIRECT_URI = "http://localhost:1455/auth/callback"


# ── 常量 ──────────────────────────────────────────────────────────────────────

OUTPUT_DIR = Path("data/har")
CALLBACK_PORT = 1455

# Chrome 版本指纹（与 semi_auto_reg.py 对齐）
_CHROME_PROFILES = [
    {"major": 131, "build": 6778, "patch_range": (69, 205),
     "sec_ch_ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"'},
    {"major": 133, "build": 6943, "patch_range": (33, 153),
     "sec_ch_ua": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"'},
    {"major": 136, "build": 7103, "patch_range": (48, 175),
     "sec_ch_ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"'},
]

def _random_chrome_version():
    import random
    profile = random.choice(_CHROME_PROFILES)
    full_ver = f"{profile['major']}.0.{profile['build']}.{random.randint(*profile['patch_range'])}"
    ua = (f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
          f"(KHTML, like Gecko) Chrome/{full_ver} Safari/537.36")
    return full_ver, ua, profile["sec_ch_ua"]

# stealth JS：消除自动化特征
_STEALTH_JS = """
() => {
    const p = Object.getPrototypeOf(navigator);
    if ('webdriver' in p) delete p.webdriver;

    Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
    Object.defineProperty(navigator, 'languages', { get: () => ['zh-CN', 'zh', 'en'] });

    if (!window.chrome) window.chrome = { runtime: {} };

    const origQuery = window.navigator.permissions.query;
    window.navigator.permissions.query = (params) =>
        params.name === 'notifications'
            ? Promise.resolve({ state: Notification.permission })
            : origQuery(params);
}
"""

# 浮动按钮 JS — 纯语句体，不包裹箭头函数
# add_init_script 需要直接可执行的语句，不是函数表达式
# evaluate() 调用时用 (function(){...})() 自执行形式
_BUTTON_SCRIPT_BODY = (
    """
(function() {
    if (document.getElementById('oai-har-btn')) return;

    var style = document.createElement('style');
    style.textContent = [
        '#oai-har-panel{position:fixed;bottom:20px;right:20px;z-index:2147483647;',
        'display:flex;flex-direction:column;gap:8px;align-items:flex-end;',
        'font-family:-apple-system,BlinkMacSystemFont,sans-serif}',
        '#oai-har-btn{padding:10px 18px;background:#10a37f;color:white;',
        'border:none;border-radius:8px;cursor:pointer;',
        'box-shadow:0 4px 12px rgba(0,0,0,0.3);font-weight:bold;font-size:13px}',
        '#oai-har-btn:disabled{background:#888;cursor:not-allowed}',
        '#oai-har-stop{padding:8px 14px;background:#e53e3e;color:white;',
        'border:none;border-radius:8px;cursor:pointer;font-size:12px;',
        'box-shadow:0 4px 12px rgba(0,0,0,0.3)}',
        '#oai-manual-box{padding:12px;background:white;border-radius:10px;',
        'box-shadow:0 6px 20px rgba(0,0,0,0.25);width:280px;',
        'display:none;flex-direction:column;gap:8px;',
        'border:1px solid #10a37f;font-size:12px}',
        '#oai-callback-url{padding:6px;border:1px solid #ccc;border-radius:4px;',
        'font-size:11px;width:100%;box-sizing:border-box}',
        '#oai-submit-url{padding:6px;background:#10a37f;color:white;',
        'border:none;border-radius:4px;cursor:pointer;font-weight:bold}'
    ].join('');
    document.head.appendChild(style);

    var panel = document.createElement('div');
    panel.id = 'oai-har-panel';

    var btn = document.createElement('button');
    btn.id = 'oai-har-btn';
    btn.textContent = '触发 OAuth（录制）';
    btn.addEventListener('click', function() {
        if (window.__oai_extracting) return;
        window.__oai_extracting = true;
        btn.textContent = '正在拉取授权...';
        btn.disabled = true;
        window.__oai_trigger = true;
        setTimeout(function() {
            var mb = document.getElementById('oai-manual-box');
            if (mb) mb.style.display = 'flex';
        }, 1000);
    });

    var stopBtn = document.createElement('button');
    stopBtn.id = 'oai-har-stop';
    stopBtn.textContent = '结束录制 保存HAR';
    stopBtn.addEventListener('click', function() { window.__oai_stop = true; });

    var box = document.createElement('div');
    box.id = 'oai-manual-box';

    var boxTitle = document.createElement('div');
    boxTitle.style.cssText = 'font-weight:bold;color:#10a37f';
    boxTitle.textContent = '手动提交回调 URL（备用）';

    var boxHint = document.createElement('div');
    boxHint.style.color = '#666';
    boxHint.textContent = '若跳转 localhost 无反应，复制地址栏 URL 粘贴到下方：';

    var urlInput = document.createElement('input');
    urlInput.type = 'text';
    urlInput.id = 'oai-callback-url';
    urlInput.placeholder = 'http://localhost:__PORT__/auth/callback?code=...';

    var submitBtn = document.createElement('button');
    submitBtn.id = 'oai-submit-url';
    submitBtn.textContent = '提交并交换 Token';
    submitBtn.addEventListener('click', function() {
        var val = urlInput.value.trim();
        if (val) { window.__oai_manual_url = val; submitBtn.textContent = '处理中...'; }
    });

    box.appendChild(boxTitle);
    box.appendChild(boxHint);
    box.appendChild(urlInput);
    box.appendChild(submitBtn);

    panel.appendChild(box);
    panel.appendChild(btn);
    panel.appendChild(stopBtn);
    document.body.appendChild(panel);
})();
"""
).replace("__PORT__", str(CALLBACK_PORT))

# evaluate() 用这个（已经是自执行函数，直接传字符串即可）
_INJECT_BUTTON_JS = _BUTTON_SCRIPT_BODY


# ── OAuth 回调服务器（完整移植自 semi_auto_reg.py）─────────────────────────────

class OAuthCallbackServer:
    """本地 HTTP 服务器，监听 OAuth 回调，捕获 code + state。"""

    def __init__(self, port: int = CALLBACK_PORT):
        self.port = port
        self.result_queue: queue.Queue = queue.Queue(maxsize=1)
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        # 检查端口是否已被占用
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            if s.connect_ex(("localhost", self.port)) == 0:
                raise RuntimeError(
                    f"端口 {self.port} 已被占用！请关闭占用程序后重试。"
                )

        result_queue = self.result_queue

        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                parsed = urlparse(self.path)
                if parsed.path == "/auth/callback":
                    params = parse_qs(parsed.query)
                    result_queue.put({
                        "code": params.get("code", [""])[0],
                        "state": params.get("state", [""])[0],
                        "error": params.get("error", [""])[0],
                        "raw_query": parsed.query,
                    })
                    html = (
                        b"<html><body><h2 style='font-family:sans-serif;color:#10a37f'>"
                        b"\xe2\x9c\x85 Authorization successful! You may close this tab.</h2>"
                        b"</body></html>"
                    )
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(html)))
                    self.end_headers()
                    self.wfile.write(html)
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, fmt, *args):
                pass  # 静默

        self._server = HTTPServer(("localhost", self.port), _Handler)
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        print(f"  [OAuth-Server] 本地回调服务器已启动: http://localhost:{self.port}")

    def wait_for_callback(self, timeout: int = 120) -> dict | None:
        try:
            return self.result_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server = None


# ── 代理检测（移植自 semi_auto_reg.py）─────────────────────────────────────────

def _detect_proxy(proxy_override: str | None) -> tuple[dict | None, str | None]:
    """
    返回 (playwright_proxy_config, proxy_url_string)。
    优先级：命令行参数 > data/proxies_webshare.txt > 本地 VPN 自动检测。
    """
    if proxy_override:
        print(f"  [Proxy] 使用手动代理: {proxy_override}")
        cfg = {"server": proxy_override}
        return cfg, proxy_override

    proxy_file = os.path.join("data", "proxies_webshare.txt")
    if os.path.exists(proxy_file):
        try:
            with open(proxy_file) as f:
                proxies = [l.strip() for l in f if l.strip() and not l.startswith("#")]
            if proxies:
                import random
                p_url = random.choice(proxies)
                parts = p_url.split(":")
                if len(parts) == 4:
                    host, port, user, pwd = parts
                    cfg = {"server": f"http://{host}:{port}", "username": user, "password": pwd}
                    url_str = f"http://{user}:{pwd}@{host}:{port}"
                else:
                    cfg = {"server": p_url}
                    url_str = p_url
                print(f"  [Proxy] 使用 Webshare 代理: {cfg['server']}")
                return cfg, url_str
        except Exception as e:
            print(f"  [Proxy] 加载代理文件失败: {e}")

    # 自动检测本地 VPN
    for port in [7890, 10808, 10809, 1080, 8080, 8888]:
        try:
            s = socket.create_connection(("127.0.0.1", port), timeout=0.3)
            s.close()
            url_str = f"http://127.0.0.1:{port}"
            print(f"  [Proxy] 自动检测到本地代理: {url_str}")
            return {"server": url_str}, url_str
        except OSError:
            pass

    print("  [Proxy] 未检测到代理，使用直连（若出现 403 请配置代理）")
    return None, None


# ── 核心录制逻辑 ───────────────────────────────────────────────────────────────

def record_har(
    start_url: str,
    output_path: Path,
    headless: bool = False,
    proxy_override: str | None = None,
    timeout_minutes: int = 10,
) -> None:
    """
    打开带 HAR 录制的浏览器，集成 OAuth 浮动按钮和本地回调服务器。
    用户手动完成全流程后按 Enter 或点击"结束录制"按钮保存 HAR。
    """
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    proxy_config, proxy_url = _detect_proxy(proxy_override)

    print(f"\n{'='*60}")
    print("  HAR 录制器 (含 OAuth 支持)")
    print(f"{'='*60}")
    print(f"  起始 URL  : {start_url}")
    print(f"  输出文件  : {output_path.resolve()}")
    print(f"  最长录制  : {timeout_minutes} 分钟")
    print(f"  OAuth 模块: {'✅ 可用' if _OAUTH_AVAILABLE else '❌ 不可用（仅录制流量）'}")
    print(f"{'='*60}")
    print()
    print("  操作指引:")
    print("  1. 浏览器打开后，正常完成注册/登录全流程")
    print("  2. 进入 ChatGPT 聊天界面后，点击右下角 [🚀 触发 OAuth] 按钮")
    print("  3. 完成 OAuth 授权（会自动提取 Refresh Token）")
    print("  4. 点击 [⏹ 结束录制保存 HAR] 或回到终端按 Enter")
    print()

    temp_dir = tempfile.mkdtemp(prefix="har_rec_")

    # OAuth 状态
    oauth_ctx = {
        "pending": False,
        "start_info": None,
        "server_active": False,
    }
    captured_tokens: dict = {}

    with sync_playwright() as p:
        try:
            # 完全对齐 semi_auto_reg.py 的启动方式（经过验证可用）
            # launch_persistent_context 同时支持 record_har_path，HAR 在 close() 时落盘
            chrome_ver, ua, sec_ch_ua = _random_chrome_version()
            print(f"  [Fingerprint] Chrome/{chrome_ver}")

            context = p.chromium.launch_persistent_context(
                user_data_dir=temp_dir,
                headless=headless,
                proxy=proxy_config,
                record_har_path=str(output_path),
                record_har_mode="full",
                record_har_content="embed",
                user_agent=ua,
                extra_http_headers={
                    "sec-ch-ua": sec_ch_ua,
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"',
                },
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized",
                ],
                no_viewport=True,
            )

            # 尝试加载 playwright-stealth
            stealth_fn = None
            try:
                import playwright_stealth as ps
                stealth_fn = getattr(ps, "stealth_sync", getattr(ps, "stealth", None))
                if stealth_fn and not callable(stealth_fn):
                    stealth_fn = getattr(stealth_fn, "stealth_sync", None) or getattr(stealth_fn, "stealth", None)
            except Exception:
                pass

            page = context.new_page()

            if stealth_fn and callable(stealth_fn):
                stealth_fn(page)
                print("  [Stealth] playwright-stealth 已加载")

            # ── 响应拦截：顺手抓 token ────────────────────────────────────────
            def on_response(response):
                try:
                    url = response.url
                    if not ("openai" in url or "chatgpt" in url or "auth0" in url):
                        return
                    status = response.status
                    if status not in (200, 201, 302):
                        return

                    # Cookie 中的 refresh_token
                    for k, v in response.headers.items():
                        if "set-cookie" in k.lower() and "refresh_token" in v.lower():
                            import re
                            m = re.search(r"refresh_token=(rt_[^;]+)", v)
                            if m:
                                captured_tokens["refresh_token"] = m.group(1)
                                print(f"  [Token] 从 Cookie 捕获到 refresh_token！")

                    # JSON body 中的 token
                    ct = response.headers.get("content-type", "")
                    if "application/json" in ct:
                        try:
                            data = response.json()
                            if isinstance(data, dict):
                                for k, v in data.items():
                                    if v and isinstance(v, str):
                                        if "refresh_token" in k.lower():
                                            captured_tokens["refresh_token"] = v
                                            print(f"  [Token] 从 JSON 捕获到 refresh_token！")
                                        elif "access_token" in k.lower() and "refresh_token" not in captured_tokens:
                                            captured_tokens["access_token"] = v
                        except Exception:
                            pass
                except Exception:
                    pass

            page.on("response", on_response)

            # ── 导航日志 ─────────────────────────────────────────────────────
            def on_nav(frame):
                if frame != page.main_frame:
                    return
                url = frame.url
                print(f"  [Nav] {url[:100]}")

                # OAuth 回调通过 framenavigated 备用处理
                if _OAUTH_AVAILABLE and url.startswith(OAUTH_REDIRECT_URI):
                    if oauth_ctx["pending"] and oauth_ctx["start_info"] and not oauth_ctx["server_active"]:
                        _do_token_exchange(url, oauth_ctx, proxy_url, page, captured_tokens)

            page.on("framenavigated", on_nav)
            page.on("requestfailed", lambda req: print(f"  [Fail] {req.url[:80]}"))
            # 每次页面 load 完成后重新注入按钮（SPA 跳转后按钮会消失）
            page.on("load", lambda _: _inject_button(page, verbose=True))

            # ── 导航到起始页 ─────────────────────────────────────────────────
            page.goto(start_url, wait_until="domcontentloaded", timeout=30_000)
            time.sleep(1)  # 等 DOM 稳定后再注入
            _inject_button(page, verbose=True)

            # ── 主循环：轮询按钮状态，等待用户完成操作 ───────────────────────
            stop_event = threading.Event()

            def _wait_enter():
                input()
                stop_event.set()

            threading.Thread(target=_wait_enter, daemon=True).start()

            deadline = time.time() + timeout_minutes * 60
            print("  [等待] 完成浏览器操作后，按 Enter 或点击 [⏹ 结束录制] 保存 HAR...\n")

            while not stop_event.is_set() and time.time() < deadline:
                try:
                    # 检查停止信号
                    stop_flag = page.evaluate("window.__oai_stop")
                    if stop_flag:
                        print("  [停止] 检测到停止信号，保存 HAR...")
                        stop_event.set()
                        break

                    # 检查 OAuth 触发
                    triggered = page.evaluate("window.__oai_trigger")
                    if triggered and _OAUTH_AVAILABLE:
                        page.evaluate("window.__oai_trigger = false")
                        print("\n  [OAuth] 按钮触发，启动 OAuth 流程...")
                        _run_oauth_flow(page, oauth_ctx, proxy_url, captured_tokens)

                    # 检查手动回调 URL 输入
                    manual_url = page.evaluate("window.__oai_manual_url")
                    if manual_url and _OAUTH_AVAILABLE:
                        page.evaluate("window.__oai_manual_url = null")
                        print(f"\n  [OAuth] 收到手动回调 URL: {manual_url[:60]}...")
                        if oauth_ctx["pending"] and oauth_ctx["start_info"]:
                            _do_token_exchange(manual_url, oauth_ctx, proxy_url, page, captured_tokens)

                    # 重新注入按钮（防止页面跳转后消失）
                    _inject_button(page)

                except Exception:
                    pass  # 页面跳转中 evaluate 会短暂抛异常，忽略

                time.sleep(0.8)

            if not stop_event.is_set():
                print(f"\n  [超时] {timeout_minutes} 分钟已到，自动保存 HAR。")

        finally:
            print("\n  正在保存 HAR（关闭浏览器）...")
            try:
                context.close()  # launch_persistent_context 返回的就是 context，close() 触发 HAR 落盘
            except Exception:
                pass
            shutil.rmtree(temp_dir, ignore_errors=True)

    # 打印捕获到的 token 摘要
    if captured_tokens:
        print("\n  捕获到的 Token:")
        for k, v in captured_tokens.items():
            print(f"    {k}: {v[:40]}...")


# ── OAuth 辅助函数 ─────────────────────────────────────────────────────────────

def _inject_button(page, verbose: bool = False) -> None:
    """注入浮动按钮，已存在则跳过。"""
    try:
        page.evaluate(_INJECT_BUTTON_JS)
        if verbose:
            exists = page.evaluate("!!document.getElementById('oai-har-btn')")
            if not exists:
                print("  [Button] ⚠️  按钮注入后在 DOM 中未找到（可能被 CSP 阻止）")
            else:
                print("  [Button] ✅ 按钮注入成功")
    except Exception as e:
        if verbose:
            print(f"  [Button] ⚠️  注入失败: {e}")


def _run_oauth_flow(page, oauth_ctx: dict, proxy_url: str | None, captured_tokens: dict) -> None:
    """生成 OAuth URL，启动回调服务器，导航授权页，等待回调并交换 token。"""
    try:
        start_info = generate_oauth_url(redirect_uri=OAUTH_REDIRECT_URI)
        oauth_ctx["start_info"] = start_info
        oauth_ctx["pending"] = True

        callback_server = OAuthCallbackServer(port=CALLBACK_PORT)
        callback_server.start()
        oauth_ctx["server_active"] = True

        print(f"  [OAuth] 授权 URL: {start_info.auth_url[:80]}...")
        try:
            page.goto(start_info.auth_url, wait_until="commit", timeout=15_000)
        except Exception as e:
            print(f"  [OAuth] goto 返回: {e}")

        print("  [OAuth] 等待授权回调（最长 2 分钟）...")
        result = callback_server.wait_for_callback(timeout=120)
        callback_server.stop()
        oauth_ctx["server_active"] = False

        if not result:
            print("  [OAuth] ❌ 超时，未收到回调")
            oauth_ctx["pending"] = False
            try:
                page.evaluate("window.__oai_extracting = false")
            except Exception:
                pass
            return

        if result.get("error"):
            print(f"  [OAuth] ❌ 回调错误: {result['error']}")
            oauth_ctx["pending"] = False
            try:
                page.evaluate("window.__oai_extracting = false")
            except Exception:
                pass
            return

        print(f"  [OAuth] ✅ 收到授权码: {result['code'][:20]}...")
        full_callback = f"http://localhost:{CALLBACK_PORT}/auth/callback?{result['raw_query']}"
        _do_token_exchange(full_callback, oauth_ctx, proxy_url, page, captured_tokens)

    except Exception as e:
        print(f"  [OAuth] ❌ 流程异常: {e}")
        oauth_ctx["pending"] = False
        try:
            page.evaluate("window.__oai_extracting = false")
        except Exception:
            pass


def _do_token_exchange(
    callback_url: str,
    oauth_ctx: dict,
    proxy_url: str | None,
    page,
    captured_tokens: dict,
) -> None:
    """用 code 换 token，保存到 data/ 目录。"""
    try:
        start_info = oauth_ctx["start_info"]
        print("  [OAuth] 正在用 code 交换 token...")
        result_json = submit_callback_url(
            callback_url=callback_url,
            expected_state=start_info.state,
            code_verifier=start_info.code_verifier,
            redirect_uri=start_info.redirect_uri,
            proxy_url=proxy_url,
        )
        token_data = json.loads(result_json)

        os.makedirs("data", exist_ok=True)
        ts = int(time.time())
        email_prefix = (token_data.get("email") or "unknown").split("@")[0]
        save_path = os.path.join("data", f"ChatGPT_Token_{email_prefix}_{ts}.json")
        with open(save_path, "w", encoding="utf-8") as f:
            json.dump(token_data, f, indent=4, ensure_ascii=False)

        rt = token_data.get("refresh_token", "")
        captured_tokens["refresh_token"] = rt
        print(f"\n  ✅ OAuth 成功！")
        print(f"     邮箱       : {token_data.get('email', 'N/A')}")
        print(f"     refresh_token: {rt[:40]}...")
        print(f"     保存路径   : {os.path.abspath(save_path)}\n")

        oauth_ctx["pending"] = False
        try:
            page.evaluate("window.__oai_extracting = false")
        except Exception:
            pass

    except Exception as e:
        print(f"  [OAuth] ❌ Token 交换失败: {e}")
        oauth_ctx["pending"] = False
        try:
            page.evaluate("window.__oai_extracting = false")
        except Exception:
            pass


# ── HAR 分析摘要 ───────────────────────────────────────────────────────────────

def post_process_har(har_path: Path) -> None:
    """读取 HAR，打印关键请求摘要，帮助确认录制完整性。"""
    try:
        with open(har_path, encoding="utf-8") as f:
            har = json.load(f)
    except Exception as e:
        print(f"  ❌ 读取 HAR 失败: {e}")
        return

    entries = har.get("log", {}).get("entries", [])
    if not entries:
        print("  ⚠️  HAR 为空，录制可能失败。")
        return

    domains: dict[str, int] = {}
    status_counts: dict[int, int] = {}
    interesting: list[dict] = []

    KEYWORDS = [
        "auth", "oauth", "token", "register", "signup", "login",
        "sentinel", "challenge", "callback", "authorize", "session",
        "openai", "chatgpt", "auth0",
    ]

    for e in entries:
        url = e["request"]["url"]
        status = e["response"]["status"]
        domain = url.split("/")[2] if "//" in url else "unknown"
        domains[domain] = domains.get(domain, 0) + 1
        status_counts[status] = status_counts.get(status, 0) + 1
        if any(kw in url.lower() for kw in KEYWORDS):
            interesting.append({
                "method": e["request"]["method"],
                "url": url,
                "status": status,
                "size": e["response"].get("bodySize", -1),
            })

    print(f"\n{'='*60}")
    print(f"  HAR 摘要: {har_path.name}")
    print(f"{'='*60}")
    print(f"  总请求数 : {len(entries)}")
    print(f"  涉及域名 : {len(domains)}")
    print(f"\n  状态码分布:")
    for code, cnt in sorted(status_counts.items()):
        flag = "  ⚠️ " if code >= 400 else "    "
        print(f"{flag}  {code}: {cnt} 次")
    print(f"\n  关键请求（{len(interesting)} 条，最多显示 50 条）:")
    for r in interesting[:50]:
        size_str = f"{r['size']}B" if r["size"] >= 0 else "chunked"
        print(f"    [{r['status']}] {r['method']:6s} {r['url'][:90]}")
    if len(interesting) > 50:
        print(f"    ... 还有 {len(interesting)-50} 条")
    print(f"{'='*60}")
    print(f"\n  HAR 文件: {har_path.resolve()}")
    print("  请将此文件发给 Claude 进行分析。\n")


# ── 入口 ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="录制 OpenAI 注册/OAuth 全流程 HAR")
    parser.add_argument("--url", default="https://chatgpt.com/",
                        help="起始 URL（默认: https://chatgpt.com/）")
    parser.add_argument("--output", default=None,
                        help="HAR 输出路径（默认: data/har/openai_<timestamp>.har）")
    parser.add_argument("--proxy", default=None,
                        help="代理，如 http://127.0.0.1:7890")
    parser.add_argument("--timeout", type=int, default=10,
                        help="最长录制时间（分钟，默认 10）")
    parser.add_argument("--headless", action="store_true",
                        help="无头模式（不建议，录制时需要手动操作）")
    args = parser.parse_args()

    if args.output:
        output_path = Path(args.output)
    else:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        output_path = OUTPUT_DIR / f"openai_{ts}.har"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    record_har(
        start_url=args.url,
        output_path=output_path,
        headless=args.headless,
        proxy_override=args.proxy,
        timeout_minutes=args.timeout,
    )

    if output_path.exists() and output_path.stat().st_size > 100:
        post_process_har(output_path)
    else:
        print("  ❌ HAR 文件未生成或为空，请检查是否有异常。")


if __name__ == "__main__":
    main()
