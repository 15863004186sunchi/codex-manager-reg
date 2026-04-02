"""
ChatGPT 注册客户端模块
使用 curl_cffi 模拟浏览器行为
"""

import random
import uuid
import time
import math
from urllib.parse import urlparse

try:
    from curl_cffi import requests as curl_requests
except ImportError:
    print("❌ 需要安装 curl_cffi: pip install curl_cffi")
    import sys
    sys.exit(1)

from .sentinel_token import build_sentinel_token
from .utils import (
    FlowState,
    build_browser_headers,
    decode_jwt_payload,
    describe_flow_state,
    extract_flow_state,
    generate_datadog_trace,
    normalize_flow_url,
    random_delay,
    seed_oai_device_cookie,
)


# Chrome 指纹配置
_CHROME_PROFILES = [
    {
        "major": 131, "impersonate": "chrome131",
        "build": 6778, "patch_range": (69, 205),
        "sec_ch_ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    },
    {
        "major": 133, "impersonate": "chrome133a",
        "build": 6943, "patch_range": (33, 153),
        "sec_ch_ua": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
    },
    {
        "major": 136, "impersonate": "chrome136",
        "build": 7103, "patch_range": (48, 175),
        "sec_ch_ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
    },
]


def _random_chrome_version():
    """随机选择一个 Chrome 版本"""
    profile = random.choice(_CHROME_PROFILES)
    major = profile["major"]
    build = profile["build"]
    patch = random.randint(*profile["patch_range"])
    full_ver = f"{major}.0.{build}.{patch}"
    ua = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{full_ver} Safari/537.36"
    return profile["impersonate"], major, full_ver, ua, profile["sec_ch_ua"]


class ChatGPTClient:
    """ChatGPT 注册客户端"""
    
    BASE = "https://chatgpt.com"
    AUTH = "https://auth.openai.com"
    
    def __init__(self, proxy=None, verbose=True, browser_mode="protocol"):
        """
        初始化 ChatGPT 客户端
        
        Args:
            proxy: 代理地址
            verbose: 是否输出详细日志
            browser_mode: protocol | headless | headed
        """
        self.proxy = proxy
        self.verbose = verbose
        self.browser_mode = browser_mode or "protocol"
        self.device_id = str(uuid.uuid4())
        self.accept_language = random.choice([
            "en-US,en;q=0.9",
            "en-US,en;q=0.9,zh-CN;q=0.8",
            "en,en-US;q=0.9",
            "en-US,en;q=0.8",
        ])
        
        # 随机 Chrome 版本
        self.impersonate, self.chrome_major, self.chrome_full, self.ua, self.sec_ch_ua = _random_chrome_version()
        
        # 创建 session
        self.session = curl_requests.Session(impersonate=self.impersonate)
        
        if self.proxy:
            self.session.proxies = {"http": self.proxy, "https": self.proxy}
        
        # 设置基础 headers
        self.session.headers.update({
            "User-Agent": self.ua,
            "Accept-Language": self.accept_language,
            "sec-ch-ua": self.sec_ch_ua,
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-ch-ua-arch": '"x86"',
            "sec-ch-ua-bitness": '"64"',
            "sec-ch-ua-full-version": f'"{self.chrome_full}"',
            "sec-ch-ua-platform-version": f'"{random.randint(10, 15)}.0.0"',
        })
        
        # 设置 oai-did cookie
        seed_oai_device_cookie(self.session, self.device_id)
        self.last_registration_state = FlowState()

    # ==========================================
    # 拟人化行为模拟 (Behavioral Simulation)
    # ==========================================
    
    def _bezier_curve(self, p0, p1, p2, p3, t):
        """计算三阶贝塞尔曲线上的点"""
        x = (1-t)**3 * p0[0] + 3*(1-t)**2 * t * p1[0] + 3*(1-t) * t**2 * p2[0] + t**3 * p3[0]
        y = (1-t)**3 * p0[1] + 3*(1-t)**2 * t * p1[1] + 3*(1-t) * t**2 * p2[1] + t**3 * p3[1]
        return x, y

    def _human_move_mouse(self, page, target_x, target_y, steps=15):
        """模拟人类带抖动的鼠标移动轨迹"""
        # 获取当前位置 (如果无法获取，则从随机位置开始)
        current_x, current_y = random.randint(0, 100), random.randint(0, 100)
        
        # 随机控制点以生成曲线
        p0 = (current_x, current_y)
        p3 = (target_x, target_y)
        p1 = (current_x + random.randint(-100, 100), current_y + random.randint(-100, 100))
        p2 = (target_x + random.randint(-100, 100), target_y + random.randint(-100, 100))
        
        for i in range(steps + 1):
            t = i / steps
            x, y = self._bezier_curve(p0, p1, p2, p3, t)
            # 加入微小抖动
            x += random.uniform(-1, 1)
            y += random.uniform(-1, 1)
            page.mouse.move(x, y)
            time.sleep(random.uniform(0.01, 0.03))

    def _human_click(self, page, selector, timeout=10000):
        """先移动到目标再点击，模拟真人"""
        locator = page.locator(selector).first
        locator.wait_for(state="visible", timeout=timeout)
        
        # 获取元素中心坐标
        box = locator.bounding_box()
        if box:
            center_x = box["x"] + box["width"] / 2
            center_y = box["y"] + box["height"] / 2
            
            self._human_move_mouse(page, center_x, center_y)
            time.sleep(random.uniform(0.1, 0.3))
            locator.click()
            self._log(f"🖱️ [Human] 点击了元素: {selector}")
        else:
            locator.click()

    def _human_type(self, page, selector, text, delay_range=(0.05, 0.2)):
        """模拟人手敲击键盘，带有随机延迟"""
        page.locator(selector).first.click()
        for char in text:
            page.keyboard.type(char)
            time.sleep(random.uniform(*delay_range))
        self._log(f"⌨️ [Human] 完成内容录入: {'*' * len(text)}")
    
    def _log(self, msg):
        """输出日志"""
        if self.verbose:
            print(f"  {msg}")

    def _browser_pause(self, low=0.15, high=0.45):
        """在 headed 模式下加入轻微停顿，模拟有头浏览器节奏。"""
        if self.browser_mode == "headed":
            random_delay(low, high)

    def _headers(
        self,
        url,
        *,
        accept,
        referer=None,
        origin=None,
        content_type=None,
        navigation=False,
        fetch_mode=None,
        fetch_dest=None,
        fetch_site=None,
        extra_headers=None,
    ):
        return build_browser_headers(
            url=url,
            user_agent=self.ua,
            sec_ch_ua=self.sec_ch_ua,
            chrome_full_version=self.chrome_full,
            accept=accept,
            accept_language=self.accept_language,
            referer=referer,
            origin=origin,
            content_type=content_type,
            navigation=navigation,
            fetch_mode=fetch_mode,
            fetch_dest=fetch_dest,
            fetch_site=fetch_site,
            headed=self.browser_mode == "headed",
            extra_headers=extra_headers,
        )

    def _reset_session(self):
        """重置浏览器指纹与会话，用于绕过偶发的 Cloudflare/SPA 中间页。"""
        self.device_id = str(uuid.uuid4())
        self.impersonate, self.chrome_major, self.chrome_full, self.ua, self.sec_ch_ua = _random_chrome_version()
        self.accept_language = random.choice([
            "en-US,en;q=0.9",
            "en-US,en;q=0.9,zh-CN;q=0.8",
            "en,en-US;q=0.9",
            "en-US,en;q=0.8",
        ])

        self.session = curl_requests.Session(impersonate=self.impersonate)
        if self.proxy:
            self.session.proxies = {"http": self.proxy, "https": self.proxy}

        self.session.headers.update({
            "User-Agent": self.ua,
            "Accept-Language": self.accept_language,
            "sec-ch-ua": self.sec_ch_ua,
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"Windows"',
            "sec-ch-ua-arch": '"x86"',
            "sec-ch-ua-bitness": '"64"',
            "sec-ch-ua-full-version": f'"{self.chrome_full}"',
            "sec-ch-ua-platform-version": f'"{random.randint(10, 15)}.0.0"',
        })
        seed_oai_device_cookie(self.session, self.device_id)

    def _state_from_url(self, url, method="GET"):
        state = extract_flow_state(
            current_url=normalize_flow_url(url, auth_base=self.AUTH),
            auth_base=self.AUTH,
            default_method=method,
        )
        if method:
            state.method = str(method).upper()
        return state

    def _state_from_payload(self, data, current_url=""):
        return extract_flow_state(
            data=data,
            current_url=current_url,
            auth_base=self.AUTH,
        )

    def _state_signature(self, state: FlowState):
        return (
            state.page_type or "",
            state.method or "",
            state.continue_url or "",
            state.current_url or "",
        )

    def _is_registration_complete_state(self, state: FlowState):
        current_url = (state.current_url or "").lower()
        continue_url = (state.continue_url or "").lower()
        page_type = state.page_type or ""
        return (
            page_type in {"callback", "chatgpt_home", "oauth_callback"}
            or ("chatgpt.com" in current_url and "redirect_uri" not in current_url)
            or ("chatgpt.com" in continue_url and "redirect_uri" not in continue_url and page_type != "external_url")
        )

    def _state_is_password_registration(self, state: FlowState):
        return state.page_type in {"create_account_password", "password"}

    def _state_is_email_otp(self, state: FlowState):
        target = f"{state.continue_url} {state.current_url}".lower()
        return state.page_type == "email_otp_verification" or "email-verification" in target or "email-otp" in target

    def _state_is_about_you(self, state: FlowState):
        target = f"{state.continue_url} {state.current_url}".lower()
        return state.page_type == "about_you" or "about-you" in target

    def _state_requires_navigation(self, state: FlowState):
        if (state.method or "GET").upper() != "GET":
            return False
        if state.page_type == "external_url" and state.continue_url:
            return True
        if state.continue_url and state.continue_url != state.current_url:
            return True
        return False

    def _follow_flow_state(self, state: FlowState, referer=None):
        """跟随服务端返回的 continue_url，推进注册状态机。"""
        target_url = state.continue_url or state.current_url
        if not target_url:
            return False, "缺少可跟随的 continue_url"

        try:
            self._browser_pause()
            r = self.session.get(
                target_url,
                headers=self._headers(
                    target_url,
                    accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                    referer=referer,
                    navigation=True,
                ),
                allow_redirects=True,
                timeout=30,
            )
            final_url = str(r.url)
            self._log(f"follow -> {r.status_code} {final_url}")

            content_type = (r.headers.get("content-type", "") or "").lower()
            if "application/json" in content_type:
                try:
                    next_state = self._state_from_payload(r.json(), current_url=final_url)
                except Exception:
                    next_state = self._state_from_url(final_url)
            else:
                next_state = self._state_from_url(final_url)

            self._log(f"follow state -> {describe_flow_state(next_state)}")
            return True, next_state
        except Exception as e:
            self._log(f"跟随 continue_url 失败: {e}")
            return False, str(e)

    def _get_cookie_value(self, name, domain_hint=None):
        """读取当前会话中的 Cookie。"""
        for cookie in self.session.cookies.jar:
            if cookie.name != name:
                continue
            if domain_hint and domain_hint not in (cookie.domain or ""):
                continue
            return cookie.value
        return ""

    def get_next_auth_session_token(self):
        """获取 ChatGPT next-auth 会话 Cookie。"""
        return self._get_cookie_value("__Secure-next-auth.session-token", "chatgpt.com")

    def fetch_chatgpt_session(self):
        """请求 ChatGPT Session 接口并返回原始会话数据。"""
        url = f"{self.BASE}/api/auth/session"
        self._browser_pause()
        response = self.session.get(
            url,
            headers=self._headers(
                url,
                accept="application/json",
                referer=f"{self.BASE}/",
                fetch_site="same-origin",
            ),
            timeout=30,
        )
        if response.status_code != 200:
            return False, f"/api/auth/session -> HTTP {response.status_code}"

        try:
            data = response.json()
        except Exception as exc:
            return False, f"/api/auth/session 返回非 JSON: {exc}"

        access_token = str(data.get("accessToken") or "").strip()
        if not access_token:
            return False, "/api/auth/session 未返回 accessToken"
        return True, data

    def reuse_session_and_get_tokens(self):
        """
        复用注册阶段已建立的 ChatGPT 会话，直接读取 Session / AccessToken。

        Returns:
            tuple[bool, dict|str]: 成功时返回标准化 token/session 数据；失败时返回错误信息。
        """
        state = self.last_registration_state or FlowState()
        self._log("步骤 1/4: 跟随注册回调 external_url ...")
        if state.page_type == "external_url" or self._state_requires_navigation(state):
            ok, followed = self._follow_flow_state(
                state,
                referer=state.current_url or f"{self.AUTH}/about-you",
            )
            if not ok:
                return False, f"注册回调落地失败: {followed}"
            self.last_registration_state = followed
        else:
            self._log("注册回调已落地，跳过额外跟随")

        self._log("步骤 2/4: 检查 __Secure-next-auth.session-token ...")
        session_cookie = self.get_next_auth_session_token()
        if not session_cookie:
            return False, "缺少 __Secure-next-auth.session-token，注册回调可能未落地"

        self._log("步骤 3/4: 请求 ChatGPT /api/auth/session ...")
        ok, session_or_error = self.fetch_chatgpt_session()
        if not ok:
            return False, session_or_error

        session_data = session_or_error
        access_token = str(session_data.get("accessToken") or "").strip()
        session_token = str(session_data.get("sessionToken") or session_cookie or "").strip()
        user = session_data.get("user") or {}
        account = session_data.get("account") or {}
        jwt_payload = decode_jwt_payload(access_token)
        auth_payload = jwt_payload.get("https://api.openai.com/auth") or {}

        account_id = (
            str(account.get("id") or "").strip()
            or str(auth_payload.get("chatgpt_account_id") or "").strip()
        )
        user_id = (
            str(user.get("id") or "").strip()
            or str(auth_payload.get("chatgpt_user_id") or "").strip()
            or str(auth_payload.get("user_id") or "").strip()
        )

        normalized = {
            "access_token": access_token,
            "session_token": session_token,
            "account_id": account_id,
            "user_id": user_id,
            "workspace_id": account_id,
            "expires": session_data.get("expires"),
            "user": user,
            "account": account,
            "auth_provider": session_data.get("authProvider"),
            "raw_session": session_data,
        }

        self._log("步骤 4/4: 已从复用会话中提取 accessToken")
        if account_id:
            self._log(f"Session Account ID: {account_id}")
        if user_id:
            self._log(f"Session User ID: {user_id}")
        return True, normalized
    
    def visit_homepage(self):
        """访问首页，建立 session"""
        self._log("访问 ChatGPT 首页...")
        url = f"{self.BASE}/"
        try:
            self._browser_pause()
            r = self.session.get(
                url,
                headers=self._headers(
                    url,
                    accept="text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
                    navigation=True,
                ),
                allow_redirects=True,
                timeout=30,
            )
            return r.status_code == 200
        except Exception as e:
            self._log(f"访问首页失败: {e}")
            return False
    
    def get_csrf_token(self):
        """获取 CSRF token"""
        self._log("获取 CSRF token...")
        url = f"{self.BASE}/api/auth/csrf"
        try:
            r = self.session.get(
                url,
                headers=self._headers(
                    url,
                    accept="application/json",
                    referer=f"{self.BASE}/",
                    fetch_site="same-origin",
                ),
                timeout=30,
            )
            
            if r.status_code == 200:
                data = r.json()
                token = data.get("csrfToken", "")
                if token:
                    self._log(f"CSRF token: {token[:20]}...")
                    return token
        except Exception as e:
            self._log(f"获取 CSRF token 失败: {e}")
        
        return None
    
    def signin(self, email, csrf_token):
        """
        提交邮箱，获取 authorize URL
        
        Returns:
            str: authorize URL
        """
        self._log(f"提交邮箱: {email}")
        url = f"{self.BASE}/api/auth/signin/openai"
        
        params = {
            "prompt": "login",
            "ext-oai-did": self.device_id,
            "auth_session_logging_id": str(uuid.uuid4()),
            "screen_hint": "login_or_signup",
            "login_hint": email,
        }
        
        form_data = {
            "callbackUrl": f"{self.BASE}/",
            "csrfToken": csrf_token,
            "json": "true",
        }

        try:
            self._browser_pause()
            r = self.session.post(
                url,
                params=params,
                data=form_data,
                headers=self._headers(
                    url,
                    accept="application/json",
                    referer=f"{self.BASE}/",
                    origin=self.BASE,
                    content_type="application/x-www-form-urlencoded",
                    fetch_site="same-origin",
                ),
                timeout=30
            )
            
            if r.status_code == 200:
                data = r.json()
                authorize_url = data.get("url", "")
                if authorize_url:
                    self._log(f"获取到 authorize URL")
                    return authorize_url
        except Exception as e:
            self._log(f"提交邮箱失败: {e}")
        
        return None
    
    def authorize(self, url, max_retries=3):
        """
        访问 authorize URL，跟随重定向（带重试机制）
        这是关键步骤，建立 auth.openai.com 的 session
        
        Returns:
            str: 最终重定向的 URL
        """
        for attempt in range(max_retries):
            try:
                if attempt > 0:
                    self._log(f"访问 authorize URL... (尝试 {attempt + 1}/{max_retries})")
                    time.sleep(1)  # 重试前等待
                else:
                    self._log("访问 authorize URL...")

                self._browser_pause()
                r = self.session.get(
                    url,
                    headers=self._headers(
                        url,
                        accept="text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                        referer=f"{self.BASE}/",
                        navigation=True,
                    ),
                    allow_redirects=True,
                    timeout=30,
                )
                
                final_url = str(r.url)
                self._log(f"重定向到: {final_url}")
                return final_url
                
            except Exception as e:
                error_msg = str(e)
                is_tls_error = "TLS" in error_msg or "SSL" in error_msg or "curl: (35)" in error_msg
                
                if is_tls_error and attempt < max_retries - 1:
                    self._log(f"Authorize TLS 错误 (尝试 {attempt + 1}/{max_retries}): {error_msg[:100]}")
                    continue
                else:
                    self._log(f"Authorize 失败: {e}")
                    return ""
        
        return ""
    
    def callback(self, callback_url=None, referer=None):
        """完成注册回调"""
        self._log("执行回调...")
        url = callback_url or f"{self.AUTH}/api/accounts/authorize/callback"
        ok, _ = self._follow_flow_state(
            self._state_from_url(url),
            referer=referer or f"{self.AUTH}/about-you",
        )
        return ok
    
    def register_user(self, email, password):
        """
        注册用户（邮箱 + 密码）
        
        Returns:
            tuple: (success, message)
        """
        self._log(f"注册用户: {email}")
        url = f"{self.AUTH}/api/accounts/user/register"
        
        headers = self._headers(
            url,
            accept="application/json",
            referer=f"{self.AUTH}/create-account/password",
            origin=self.AUTH,
            content_type="application/json",
            fetch_site="same-origin",
        )
        headers.update(generate_datadog_trace())
        
        payload = {
            "username": email,
            "password": password,
        }
        
        try:
            self._browser_pause()
            r = self.session.post(url, json=payload, headers=headers, timeout=30)
            
            if r.status_code == 200:
                data = r.json()
                self._log("注册成功")
                return True, "注册成功"
            else:
                try:
                    error_data = r.json()
                    error_msg = error_data.get("error", {}).get("message", r.text[:200])
                except:
                    error_msg = r.text[:200]
                self._log(f"注册失败: {r.status_code} - {error_msg}")
                return False, f"HTTP {r.status_code}: {error_msg}"
                
        except Exception as e:
            self._log(f"注册异常: {e}")
            return False, str(e)
    
    def send_email_otp(self):
        """触发发送邮箱验证码"""
        self._log("触发发送验证码...")
        url = f"{self.AUTH}/api/accounts/email-otp/send"

        try:
            self._browser_pause()
            r = self.session.get(
                url,
                headers=self._headers(
                    url,
                    accept="application/json, text/plain, */*",
                    referer=f"{self.AUTH}/create-account/password",
                    fetch_site="same-origin",
                ),
                allow_redirects=True,
                timeout=30,
            )
            return r.status_code == 200
        except Exception as e:
            self._log(f"发送验证码失败: {e}")
            return False
    
    def verify_email_otp(self, otp_code, return_state=False):
        """
        验证邮箱 OTP 码
        
        Args:
            otp_code: 6位验证码
            
        Returns:
            tuple: (success, message)
        """
        self._log(f"验证 OTP 码: {otp_code}")
        url = f"{self.AUTH}/api/accounts/email-otp/validate"
        
        headers = self._headers(
            url,
            accept="application/json",
            referer=f"{self.AUTH}/email-verification",
            origin=self.AUTH,
            content_type="application/json",
            fetch_site="same-origin",
        )
        headers.update(generate_datadog_trace())
        
        payload = {"code": otp_code}
        
        try:
            self._browser_pause()
            r = self.session.post(url, json=payload, headers=headers, timeout=30)
            
            if r.status_code == 200:
                try:
                    data = r.json()
                except Exception:
                    data = {}
                next_state = self._state_from_payload(data, current_url=str(r.url) or f"{self.AUTH}/about-you")
                self._log(f"验证成功 {describe_flow_state(next_state)}")
                return (True, next_state) if return_state else (True, "验证成功")
            else:
                try:
                    error_msg = r.text[:200]
                except Exception:
                    error_msg = ""
                self._log(f"验证失败: {r.status_code} - {error_msg}")
                return False, f"HTTP {r.status_code}: {error_msg}".strip()
                
        except Exception as e:
            self._log(f"验证异常: {e}")
            return False, str(e)
    
    def create_account(self, first_name, last_name, birthdate, return_state=False):
        """
        完成账号创建（提交姓名和生日）
        
        Args:
            first_name: 名
            last_name: 姓
            birthdate: 生日 (YYYY-MM-DD)
            
        Returns:
            tuple: (success, message)
        """
        name = f"{first_name} {last_name}"
        self._log(f"完成账号创建: {name}")
        url = f"{self.AUTH}/api/accounts/create_account"

        sentinel_token = build_sentinel_token(
            self.session,
            self.device_id,
            flow="authorize_continue",
            user_agent=self.ua,
            sec_ch_ua=self.sec_ch_ua,
            impersonate=self.impersonate,
        )
        if sentinel_token:
            self._log("create_account: 已生成 sentinel token")
        else:
            self._log("create_account: 未生成 sentinel token，降级继续请求")
        
        headers = self._headers(
            url,
            accept="application/json",
            referer=f"{self.AUTH}/about-you",
            origin=self.AUTH,
            content_type="application/json",
            fetch_site="same-origin",
            extra_headers={
                "oai-device-id": self.device_id,
            },
        )
        if sentinel_token:
            headers["openai-sentinel-token"] = sentinel_token
        headers.update(generate_datadog_trace())
        
        payload = {
            "name": name,
            "birthdate": birthdate,
        }
        
        try:
            self._browser_pause()
            r = self.session.post(url, json=payload, headers=headers, timeout=30)
            
            if r.status_code == 200:
                try:
                    data = r.json()
                except Exception:
                    data = {}
                next_state = self._state_from_payload(data, current_url=str(r.url) or self.BASE)
                self._log(f"账号创建成功 {describe_flow_state(next_state)}")
                return (True, next_state) if return_state else (True, "账号创建成功")
            else:
                error_msg = r.text[:200]
                self._log(f"创建失败: {r.status_code} - {error_msg}")
                return False, f"HTTP {r.status_code}"
                
        except Exception as e:
            self._log(f"创建异常: {e}")
            return False, str(e)
    def _playwright_hybrid_flow(self, email, password, first_name, last_name, birthdate, skymail_client, auth_url):
        """混合驱动：使用 Playwright 完成高风险注册流程（带清空缓存策略），完成后回收 Session Token。"""
        import tempfile
        import sys
        from playwright.sync_api import sync_playwright
        
        # 调试环境：记录 sys.path 确认为何 uv 环境下 import 失败
        try:
            from playwright_stealth import stealth_sync
        except ImportError:
            self._log(f"⚠️ 未检测到 playwright-stealth 库! sys.executable: {sys.executable}")
            # self._log(f"sys.path: {sys.path[:5]} ...")
            stealth_sync = None

        self._log("🌟 启动 Playwright Hybrid Flow (Headful + Stealth)...")
        with sync_playwright() as p:
            # 每次均使用系统临时目录作为上下文，实现彻底清空缓存和旧有登录状态
            with tempfile.TemporaryDirectory() as temp_dir:
                
                # 配置代理字典供 Playwright 识别
                pw_proxy = None
                if self.proxy:
                    parsed = urlparse(self.proxy)
                    if parsed.username and parsed.password:
                        pw_proxy = {
                            "server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}",
                            "username": parsed.username,
                            "password": parsed.password
                        }
                    else:
                        pw_proxy = {"server": self.proxy}

                browser = p.chromium.launch_persistent_context(
                    user_data_dir=temp_dir,
                    headless=False,  # 保持有界面以应对极端风控
                    args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
                    user_agent=self.ua,
                    viewport={"width": 1280, "height": 800},
                    proxy=pw_proxy
                )
                page = browser.new_page()
                
                # 开启指纹隐藏插件
                if stealth_sync:
                    stealth_sync(page)
                    self._log("🛡️ [Stealth] 已启用浏览器指纹混淆插件。")
                
                # 注入关键的 oai-did 确保从协议层传过去的 session 是一致的
                try:
                    browser.add_cookies([
                        {"name": "oai-did", "value": self.device_id, "domain": ".chatgpt.com", "path": "/"},
                        {"name": "oai-did", "value": self.device_id, "domain": ".openai.com", "path": "/"}
                    ])
                except Exception as e:
                    self._log(f"注入 oai-did Cookie 失败: {e}")

                try:
                    self._log(f"通过真实浏览器访问授权链接 (auth_url)...")
                    # 避免 networkidle 死等，改用 domcontentloaded
                    page.goto(auth_url, wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(3000) # 让 React 组件渲染

                    # 如果页面依然要求输入邮箱
                    try:
                        email_input_sel = "input[type='email'], input[name='email'], input[name='username']"
                        email_input = page.locator(email_input_sel).first
                        if email_input.is_visible():
                            self._log("📝 [Playwright] 填入注册邮箱...")
                            self._human_type(page, email_input_sel, email)
                            self._human_click(page, "button[type='submit'], button:has-text('Continue')")
                            page.wait_for_timeout(3000)
                    except Exception:
                        pass
                    
                    # 1. 密码填写 (绕过 Stage 1 风控)
                    try:
                        self._log("📝 [Playwright] 准备填写密码...")
                        pwd_input_sel = "input[type='password'], input[name='password']"
                        # 等待元素出现
                        page.wait_for_selector(pwd_input_sel, timeout=30000)
                        self._human_type(page, pwd_input_sel, password)
                        
                        # 重点：点击继续并验证页面是否跳转 (即验证码页面是否出现)
                        self._log("🖱️ [Playwright] 点击 Continue 并观察页面变动...")
                        self._human_click(page, "button[type='submit'], button:has-text('Continue')")
                        
                        # 等待验证码页面或者个人资料页面出现 (如果是登录流会直接过，如果是注册流会进 OTP)
                        # 我们等待 input[inputmode='numeric'] 或者输入框消失
                        try:
                            page.wait_for_function("() => !document.querySelector('input[type=\"password\"]') || document.querySelector('input[inputmode=\"numeric\"]')", timeout=20000)
                        except Exception:
                            self._log("⚠️ 密码提交后页面未显著跳转，可能存在隐藏验证码或网络拥堵。")
                        
                        page.wait_for_timeout(5000)
                    except Exception as e:
                        current_url = page.url
                        page.screenshot(path="registration_error_pwd.png")
                        return False, f"Playwright 阶段填写密码失败 (URL: {current_url}): {e}"
                    
                    # 2. 获取并填写验证码
                    self._log("📧 [Playwright] 等待并获取邮件验证码...")
                    otp_code = skymail_client.wait_for_verification_code(email, timeout=90)
                    if not otp_code:
                        return False, "未收到邮箱验证码，流程终止！"
                    
                    try:
                        self._log(f"🔑 [Playwright] 正在确认验证码输入框 (URL: {page.url})...")
                        # 验证码输入框等待设置为 60 秒，以对抗超慢代理或二次验证
                        page.locator("input[inputmode='numeric']").first.wait_for(timeout=60000)
                        # 这里直接使用 human_type 在第一个输入框上，通常会自动跳转
                        self._human_type(page, "input[inputmode='numeric']", otp_code, delay_range=(0.1, 0.3))
                        page.wait_for_timeout(5000)
                    except Exception as e:
                        page.screenshot(path="registration_error_otp.png")
                        return False, f"Playwright 阶段填写验证码失败 (URL: {page.url}): {e}"
                    
                    # 3. 填写个人资料 (绕过 Stage 2 风控，带 so-token)
                    try:
                        self._log("👤 [Playwright] 填写个人资料 (Name / Birthdate)...")
                        name_sel = "input[name='name'], input[id='name']"
                        page.wait_for_selector(name_sel, timeout=30000)
                        
                        self._human_type(page, name_sel, f"{first_name} {last_name}")
                        page.wait_for_timeout(1000)
                        
                        bday_sel = "input[name='birthday'], input[id='birthday'], input[name='birthdate']"
                        self._human_type(page, bday_sel, birthdate)
                        page.wait_for_timeout(1000)
                        
                        self._human_click(page, "button[type='submit'], button:has-text('Agree'), button:has-text('Finish')")
                    except Exception as e:
                        self._log(f"填写个人资料超时或跳过: {e}")
                    
                    # 4. 等待成功重定向与 Session 获取
                    self._log("⏳ [Playwright] 等待重定向至 chatgpt.com 以收取战利品...")
                    try:
                        page.wait_for_url("https://chatgpt.com/**", timeout=30000)
                    except Exception:
                        pass
                    
                    # 将 Playwright 中的有效 Cookie 传回给当前的对象会话
                    cookies = browser.cookies()
                    found_auth = False
                    for c in cookies:
                        # 对于 httpx / curl_cffi，这里设置 domain 的方式：
                        if c["name"] == "__Secure-next-auth.session-token":
                            self.session.cookies.set(c["name"], c["value"], domain=c["domain"])
                            found_auth = True
                    
                    if found_auth:
                        self._log("✅ [Playwright] 成功萃取 __Secure-next-auth.session-token！")
                        return True, "注册成功 (Hybrid)"
                    else:
                        return False, "未能抓取到 next-auth 会话令牌，请检查页面是否成功跳转。"
                finally:
                    browser.close()

    def register_complete_flow(self, email, password, first_name, last_name, birthdate, skymail_client):
        """
        完整的注册流程（基于原版 run_register 方法）
        
        Args:
            email: 邮箱
            password: 密码
            first_name: 名
            last_name: 姓
            birthdate: 生日
            skymail_client: Skymail 客户端（用于获取验证码）
            
        Returns:
            tuple: (success, message)
        """
        from urllib.parse import urlparse
        
        max_auth_attempts = 3
        final_url = ""
        final_path = ""

        for auth_attempt in range(max_auth_attempts):
            if auth_attempt > 0:
                self._log(f"预授权阶段重试 {auth_attempt + 1}/{max_auth_attempts}...")
                self._reset_session()

            # 1. 访问首页
            if not self.visit_homepage():
                if auth_attempt < max_auth_attempts - 1:
                    continue
                return False, "访问首页失败"

            # 2. 获取 CSRF token
            csrf_token = self.get_csrf_token()
            if not csrf_token:
                if auth_attempt < max_auth_attempts - 1:
                    continue
                return False, "获取 CSRF token 失败"

            # 3. 提交邮箱，获取 authorize URL
            auth_url = self.signin(email, csrf_token)
            if not auth_url:
                if auth_attempt < max_auth_attempts - 1:
                    continue
                return False, "提交邮箱失败"

            # 【核心分流点】混合模式下，在此处接管 Playwright
            if self.browser_mode == "hybrid":
                self._log("🔧 当前模式为 Hybrid，将启用 Playwright 接管 Sentinel 风控节点。")
                return self._playwright_hybrid_flow(
                    email, password, first_name, last_name, birthdate, skymail_client, auth_url
                )

            # 4. 访问 authorize URL（关键步骤！）
            final_url = self.authorize(auth_url)
            if not final_url:
                if auth_attempt < max_auth_attempts - 1:
                    continue
                return False, "Authorize 失败"

            final_path = urlparse(final_url).path
            self._log(f"Authorize → {final_path}")

            # /api/accounts/authorize 实际上常对应 Cloudflare 403 中间页，不要继续走 authorize_continue。
            if "api/accounts/authorize" in final_path or final_path == "/error":
                self._log(f"检测到 Cloudflare/SPA 中间页，准备重试预授权: {final_url[:160]}...")
                if auth_attempt < max_auth_attempts - 1:
                    continue
                return False, f"预授权被拦截: {final_path}"

            break
        
        state = self._state_from_url(final_url)
        self._log(f"注册状态起点: {describe_flow_state(state)}")

        register_submitted = False
        otp_verified = False
        account_created = False
        seen_states = {}

        for _ in range(12):
            signature = self._state_signature(state)
            seen_states[signature] = seen_states.get(signature, 0) + 1
            if seen_states[signature] > 2:
                return False, f"注册状态卡住: {describe_flow_state(state)}"

            if self._is_registration_complete_state(state):
                self.last_registration_state = state
                self._log("✅ 注册流程完成")
                return True, "注册成功"

            if self._state_is_password_registration(state):
                self._log("全新注册流程")
                if register_submitted:
                    return False, "注册密码阶段重复进入"
                success, msg = self.register_user(email, password)
                if not success:
                    return False, f"注册失败: {msg}"
                register_submitted = True
                if not self.send_email_otp():
                    self._log("发送验证码接口返回失败，继续等待邮箱中的验证码...")
                state = self._state_from_url(f"{self.AUTH}/email-verification")
                continue

            if self._state_is_email_otp(state):
                self._log("等待邮箱验证码...")
                otp_code = skymail_client.wait_for_verification_code(email, timeout=90)
                if not otp_code:
                    return False, "未收到验证码"

                tried_codes = {otp_code}
                for _ in range(3):
                    success, next_state = self.verify_email_otp(otp_code, return_state=True)
                    if success:
                        otp_verified = True
                        state = next_state
                        self.last_registration_state = state
                        break

                    err_text = str(next_state or "")
                    is_wrong_code = any(
                        marker in err_text.lower()
                        for marker in (
                            "wrong_email_otp_code",
                            "wrong code",
                            "http 401",
                        )
                    )
                    if not is_wrong_code:
                        return False, f"验证码失败: {next_state}"

                    self._log("验证码疑似过期/错误，尝试获取新验证码...")
                    otp_code = skymail_client.wait_for_verification_code(
                        email,
                        timeout=45,
                        exclude_codes=tried_codes,
                    )
                    if not otp_code:
                        return False, "未收到新的验证码"
                    tried_codes.add(otp_code)

                if not otp_verified:
                    return False, "验证码失败: 多次尝试仍无效"
                continue

            if self._state_is_about_you(state):
                if account_created:
                    return False, "填写信息阶段重复进入"
                success, next_state = self.create_account(
                    first_name,
                    last_name,
                    birthdate,
                    return_state=True,
                )
                if not success:
                    return False, f"创建账号失败: {next_state}"
                account_created = True
                state = next_state
                self.last_registration_state = state
                continue

            if self._state_requires_navigation(state):
                success, next_state = self._follow_flow_state(
                    state,
                    referer=state.current_url or f"{self.AUTH}/about-you",
                )
                if not success:
                    return False, f"跳转失败: {next_state}"
                state = next_state
                self.last_registration_state = state
                continue

            if (not register_submitted) and (not otp_verified) and (not account_created):
                self._log(f"未知起始状态，回退为全新注册流程: {describe_flow_state(state)}")
                state = self._state_from_url(f"{self.AUTH}/create-account/password")
                continue

            return False, f"未支持的注册状态: {describe_flow_state(state)}"

        return False, "注册状态机超出最大步数"
