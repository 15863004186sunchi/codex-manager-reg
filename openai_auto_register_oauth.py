#!/usr/bin/env python3
"""
OpenAI自动注册和OAuth获取Refresh Token
基于HAR文件分析的完整流程实现
"""
import asyncio
import hashlib
import base64
import secrets
import json
import re
from typing import Dict, Optional, Tuple
from urllib.parse import urlencode, parse_qs, urlparse
from playwright.async_api import async_playwright, Page, BrowserContext
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


class OpenAIAuthClient:
    """OpenAI认证客户端 - 模拟真实浏览器行为"""
    
    # 关键配置
    BASE_URL = "https://chatgpt.com"
    AUTH_URL = "https://auth.openai.com"
    CLIENT_ID = "app_X8zY6vW2pQ9tR3dE7nK1jL5gH"  # ChatGPT Web客户端ID
    CLI_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"  # CLI客户端ID (用于获取refresh token)
    REDIRECT_URI = "https://chatgpt.com/api/auth/callback/openai"
    CLI_REDIRECT_URI = "http://localhost:1455/auth/callback"
    
    def __init__(self, headless: bool = False):
        self.headless = headless
        self.browser = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.device_id = self._generate_device_id()
        
    def _generate_device_id(self) -> str:
        """生成设备ID (UUID格式)"""
        import uuid
        return str(uuid.uuid4())
    
    def _generate_pkce_pair(self) -> Tuple[str, str]:
        """生成PKCE code_verifier和code_challenge"""
        # 生成code_verifier (43-128个字符)
        code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
        
        # 生成code_challenge (SHA256哈希)
        code_challenge = base64.urlsafe_b64encode(
            hashlib.sha256(code_verifier.encode('utf-8')).digest()
        ).decode('utf-8').rstrip('=')
        
        return code_verifier, code_challenge
    
    async def init_browser(self):
        """初始化浏览器"""
        playwright = await async_playwright().start()
        
        # 使用真实的浏览器指纹
        self.browser = await playwright.chromium.launch(
            headless=self.headless,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--no-sandbox',
            ]
        )
        
        # 创建上下文，模拟真实浏览器
        self.context = await self.browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.7103.92 Safari/537.36',
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
            extra_http_headers={
                'Accept-Language': 'zh-CN',
                'sec-ch-ua': '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"',
                'sec-ch-ua-mobile': '?0',
                'sec-ch-ua-platform': '"Windows"',
            }
        )
        
        # 注入反检测脚本
        await self.context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
            
            // 覆盖Chrome自动化标识
            window.chrome = {
                runtime: {}
            };
            
            // 覆盖permissions
            const originalQuery = window.navigator.permissions.query;
            window.navigator.permissions.query = (parameters) => (
                parameters.name === 'notifications' ?
                    Promise.resolve({ state: Notification.permission }) :
                    originalQuery(parameters)
            );
        """)
        
        self.page = await self.context.new_page()
        logger.info(f"浏览器初始化完成，设备ID: {self.device_id}")
    
    async def register_account(self, email: str, password: str) -> bool:
        """
        注册新账号
        
        Args:
            email: 邮箱地址
            password: 密码
            
        Returns:
            是否成功进入邮箱验证页面
        """
        logger.info(f"开始注册账号: {email}")
        
        try:
            # 1. 访问ChatGPT首页
            await self.page.goto(self.BASE_URL, wait_until='networkidle')
            await asyncio.sleep(2)
            
            # 2. 点击注册按钮
            try:
                # 尝试多种可能的选择器
                signup_selectors = [
                    'button:has-text("Sign up")',
                    'a:has-text("Sign up")',
                    '[data-testid="signup-button"]',
                    'text=Sign up'
                ]
                
                for selector in signup_selectors:
                    try:
                        await self.page.click(selector, timeout=5000)
                        logger.info("点击注册按钮成功")
                        break
                    except:
                        continue
                else:
                    # 如果没有找到注册按钮，直接访问注册页面
                    logger.info("未找到注册按钮，直接访问注册页面")
                    auth_url = f"{self.AUTH_URL}/create-account/password"
                    await self.page.goto(auth_url, wait_until='networkidle')
                
            except Exception as e:
                logger.warning(f"点击注册按钮失败: {e}，尝试直接访问注册页面")
                auth_url = f"{self.AUTH_URL}/create-account/password"
                await self.page.goto(auth_url, wait_until='networkidle')
            
            await asyncio.sleep(2)
            
            # 3. 填写邮箱
            email_input = await self.page.wait_for_selector('input[type="email"], input[name="username"], input[autocomplete="username"]', timeout=10000)
            await email_input.fill(email)
            await asyncio.sleep(0.5)
            
            # 4. 点击继续按钮
            continue_button = await self.page.wait_for_selector('button[type="submit"], button:has-text("Continue")', timeout=5000)
            await continue_button.click()
            await asyncio.sleep(2)
            
            # 5. 填写密码
            password_input = await self.page.wait_for_selector('input[type="password"], input[name="password"]', timeout=10000)
            await password_input.fill(password)
            await asyncio.sleep(0.5)
            
            # 6. 提交注册表单
            submit_button = await self.page.wait_for_selector('button[type="submit"], button:has-text("Continue")', timeout=5000)
            await submit_button.click()
            
            # 7. 等待跳转到邮箱验证页面
            await self.page.wait_for_url('**/email-verification**', timeout=30000)
            logger.info("成功进入邮箱验证页面")
            
            return True
            
        except Exception as e:
            logger.error(f"注册失败: {e}")
            # 保存截图用于调试
            await self.page.screenshot(path=f'register_error_{email}.png')
            return False
    
    async def verify_email(self, verification_code: str) -> bool:
        """
        验证邮箱
        
        Args:
            verification_code: 6位验证码
            
        Returns:
            是否验证成功
        """
        logger.info(f"开始验证邮箱，验证码: {verification_code}")
        
        try:
            # 等待验证码输入框
            code_input = await self.page.wait_for_selector('input[type="text"], input[name="code"]', timeout=10000)
            
            # 输入验证码
            await code_input.fill(verification_code)
            await asyncio.sleep(0.5)
            
            # 提交验证码
            submit_button = await self.page.wait_for_selector('button[type="submit"], button:has-text("Continue")', timeout=5000)
            await submit_button.click()
            
            # 等待验证完成
            await asyncio.sleep(3)
            
            # 检查是否成功登录
            current_url = self.page.url
            if 'chatgpt.com' in current_url and 'auth' not in current_url:
                logger.info("邮箱验证成功，已登录")
                return True
            else:
                logger.warning(f"验证后URL异常: {current_url}")
                return False
                
        except Exception as e:
            logger.error(f"邮箱验证失败: {e}")
            await self.page.screenshot(path='verify_error.png')
            return False
    
    async def get_refresh_token_via_oauth(self) -> Optional[Dict[str, str]]:
        """
        通过OAuth流程获取refresh token
        使用CLI客户端ID和PKCE流程
        
        Returns:
            包含access_token和refresh_token的字典，失败返回None
        """
        logger.info("开始OAuth流程获取refresh token")
        
        try:
            # 1. 生成PKCE参数
            code_verifier, code_challenge = self._generate_pkce_pair()
            logger.info(f"生成PKCE参数: code_challenge={code_challenge[:20]}...")
            
            # 2. 构建OAuth授权URL
            state = secrets.token_urlsafe(32)
            auth_params = {
                'client_id': self.CLI_CLIENT_ID,
                'code_challenge': code_challenge,
                'code_challenge_method': 'S256',
                'codex_cli_simplified_flow': 'true',
                'id_token_add_organizations': 'true',
                'prompt': 'login',
                'redirect_uri': self.CLI_REDIRECT_URI,
                'response_type': 'code',
                'scope': 'openid email profile offline_access',
                'state': state
            }
            
            auth_url = f"{self.AUTH_URL}/oauth/authorize?{urlencode(auth_params)}"
            logger.info(f"访问OAuth授权URL")
            
            # 3. 访问授权页面
            await self.page.goto(auth_url, wait_until='networkidle')
            await asyncio.sleep(3)
            
            # 4. 等待重定向到回调URL
            # 由于localhost:1455不存在，我们需要拦截重定向
            authorization_code = None
            
            async def handle_response(response):
                nonlocal authorization_code
                url = response.url
                if self.CLI_REDIRECT_URI in url:
                    parsed = urlparse(url)
                    params = parse_qs(parsed.query)
                    if 'code' in params:
                        authorization_code = params['code'][0]
                        logger.info(f"获取到authorization code: {authorization_code[:20]}...")
            
            self.page.on('response', handle_response)
            
            # 等待获取code
            for _ in range(30):  # 最多等待30秒
                if authorization_code:
                    break
                await asyncio.sleep(1)
            
            if not authorization_code:
                # 尝试从当前URL获取
                current_url = self.page.url
                if 'code=' in current_url:
                    parsed = urlparse(current_url)
                    params = parse_qs(parsed.query)
                    authorization_code = params.get('code', [None])[0]
            
            if not authorization_code:
                logger.error("未能获取authorization code")
                await self.page.screenshot(path='oauth_error.png')
                return None
            
            # 5. 使用authorization code交换token
            logger.info("使用authorization code交换token")
            
            token_url = f"{self.AUTH_URL}/oauth/token"
            token_data = {
                'client_id': self.CLI_CLIENT_ID,
                'code': authorization_code,
                'code_verifier': code_verifier,
                'grant_type': 'authorization_code',
                'redirect_uri': self.CLI_REDIRECT_URI
            }
            
            # 使用page.evaluate执行fetch请求
            token_response = await self.page.evaluate(f"""
                async () => {{
                    const response = await fetch('{token_url}', {{
                        method: 'POST',
                        headers: {{
                            'Content-Type': 'application/x-www-form-urlencoded'
                        }},
                        body: new URLSearchParams({json.dumps(token_data)})
                    }});
                    return await response.json();
                }}
            """)
            
            if 'access_token' in token_response and 'refresh_token' in token_response:
                logger.info("成功获取tokens")
                return {
                    'access_token': token_response['access_token'],
                    'refresh_token': token_response['refresh_token'],
                    'expires_in': token_response.get('expires_in', 3600)
                }
            else:
                logger.error(f"Token响应异常: {token_response}")
                return None
                
        except Exception as e:
            logger.error(f"OAuth流程失败: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    async def close(self):
        """关闭浏览器"""
        if self.browser:
            await self.browser.close()
            logger.info("浏览器已关闭")


async def main():
    """主函数 - 演示完整流程"""
    
    # 配置
    email = "test_user_" + secrets.token_hex(4) + "@example.com"
    password = "SecurePassword123!"
    
    logger.info("="*80)
    logger.info("OpenAI自动注册和OAuth流程")
    logger.info("="*80)
    logger.info(f"邮箱: {email}")
    logger.info(f"密码: {password}")
    logger.info("="*80)
    
    client = OpenAIAuthClient(headless=False)  # 设置为False可以看到浏览器操作
    
    try:
        # 1. 初始化浏览器
        await client.init_browser()
        
        # 2. 注册账号
        register_success = await client.register_account(email, password)
        
        if not register_success:
            logger.error("注册失败，流程终止")
            return
        
        # 3. 等待用户手动输入验证码
        logger.info("="*80)
        logger.info("请检查邮箱并输入验证码")
        logger.info("="*80)
        verification_code = input("请输入6位验证码: ").strip()
        
        # 4. 验证邮箱
        verify_success = await client.verify_email(verification_code)
        
        if not verify_success:
            logger.error("邮箱验证失败，流程终止")
            return
        
        # 5. 获取refresh token
        logger.info("="*80)
        logger.info("开始获取refresh token")
        logger.info("="*80)
        
        tokens = await client.get_refresh_token_via_oauth()
        
        if tokens:
            logger.info("="*80)
            logger.info("成功获取tokens!")
            logger.info("="*80)
            logger.info(f"Access Token: {tokens['access_token'][:50]}...")
            logger.info(f"Refresh Token: {tokens['refresh_token'][:50]}...")
            logger.info(f"Expires In: {tokens['expires_in']} seconds")
            
            # 保存到文件
            output_file = f"tokens_{email.split('@')[0]}.json"
            with open(output_file, 'w') as f:
                json.dump({
                    'email': email,
                    'password': password,
                    'tokens': tokens
                }, f, indent=2)
            logger.info(f"Tokens已保存到: {output_file}")
        else:
            logger.error("获取tokens失败")
        
    except Exception as e:
        logger.error(f"流程执行失败: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        # 等待一段时间以便查看结果
        await asyncio.sleep(5)
        await client.close()


if __name__ == '__main__':
    asyncio.run(main())
