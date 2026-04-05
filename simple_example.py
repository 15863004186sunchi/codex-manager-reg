#!/usr/bin/env python3
"""
简化的OpenAI OAuth示例
演示如何使用已有账号获取refresh token
"""
import asyncio
import hashlib
import base64
import secrets
import json
from urllib.parse import urlencode, parse_qs, urlparse
from playwright.async_api import async_playwright


async def get_refresh_token(email: str, password: str):
    """
    使用已有账号获取refresh token
    
    Args:
        email: OpenAI账号邮箱
        password: 账号密码
    """
    
    # OAuth配置
    AUTH_URL = "https://auth.openai.com"
    CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"  # CLI客户端
    REDIRECT_URI = "http://localhost:1455/auth/callback"
    
    # 生成PKCE参数
    code_verifier = base64.urlsafe_b64encode(secrets.token_bytes(32)).decode('utf-8').rstrip('=')
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode('utf-8')).digest()
    ).decode('utf-8').rstrip('=')
    
    print(f"[1/5] 生成PKCE参数")
    print(f"  code_verifier: {code_verifier[:30]}...")
    print(f"  code_challenge: {code_challenge[:30]}...")
    
    # 启动浏览器
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=False)
    context = await browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36'
    )
    page = await context.new_page()
    
    try:
        # 构建OAuth URL
        state = secrets.token_urlsafe(32)
        auth_params = {
            'client_id': CLIENT_ID,
            'code_challenge': code_challenge,
            'code_challenge_method': 'S256',
            'codex_cli_simplified_flow': 'true',
            'id_token_add_organizations': 'true',
            'prompt': 'login',
            'redirect_uri': REDIRECT_URI,
            'response_type': 'code',
            'scope': 'openid email profile offline_access',
            'state': state
        }
        
        auth_url = f"{AUTH_URL}/oauth/authorize?{urlencode(auth_params)}"
        
        print(f"\n[2/5] 访问OAuth授权页面")
        await page.goto(auth_url)
        await asyncio.sleep(2)
        
        # 登录
        print(f"\n[3/5] 登录账号: {email}")
        
        # 输入邮箱
        try:
            email_input = await page.wait_for_selector('input[type="email"], input[name="username"]', timeout=10000)
            await email_input.fill(email)
            await asyncio.sleep(0.5)
            
            # 点击继续
            continue_btn = await page.wait_for_selector('button[type="submit"]', timeout=5000)
            await continue_btn.click()
            await asyncio.sleep(2)
        except:
            print("  可能已经登录，跳过邮箱输入")
        
        # 输入密码
        try:
            password_input = await page.wait_for_selector('input[type="password"]', timeout=10000)
            await password_input.fill(password)
            await asyncio.sleep(0.5)
            
            # 提交
            submit_btn = await page.wait_for_selector('button[type="submit"]', timeout=5000)
            await submit_btn.click()
            await asyncio.sleep(3)
        except:
            print("  可能已经登录，跳过密码输入")
        
        # 等待重定向并获取authorization code
        print(f"\n[4/5] 等待获取authorization code...")
        
        authorization_code = None
        
        # 监听重定向
        async def handle_response(response):
            nonlocal authorization_code
            url = response.url
            if REDIRECT_URI in url:
                parsed = urlparse(url)
                params = parse_qs(parsed.query)
                if 'code' in params:
                    authorization_code = params['code'][0]
                    print(f"  获取到code: {authorization_code[:30]}...")
        
        page.on('response', handle_response)
        
        # 等待最多30秒
        for i in range(30):
            if authorization_code:
                break
            await asyncio.sleep(1)
            
            # 尝试从当前URL获取
            current_url = page.url
            if 'code=' in current_url:
                parsed = urlparse(current_url)
                params = parse_qs(parsed.query)
                if 'code' in params:
                    authorization_code = params['code'][0]
                    print(f"  从URL获取到code: {authorization_code[:30]}...")
                    break
        
        if not authorization_code:
            print("  ❌ 未能获取authorization code")
            await page.screenshot(path='oauth_error.png')
            return None
        
        # 交换token
        print(f"\n[5/5] 交换access token和refresh token...")
        
        token_url = f"{AUTH_URL}/oauth/token"
        token_data = {
            'client_id': CLIENT_ID,
            'code': authorization_code,
            'code_verifier': code_verifier,
            'grant_type': 'authorization_code',
            'redirect_uri': REDIRECT_URI
        }
        
        # 使用fetch API交换token
        token_response = await page.evaluate(f"""
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
            print(f"\n✅ 成功获取tokens!")
            print(f"  Access Token: {token_response['access_token'][:50]}...")
            print(f"  Refresh Token: {token_response['refresh_token'][:50]}...")
            print(f"  Expires In: {token_response.get('expires_in', 'N/A')} seconds")
            
            # 保存到文件
            output = {
                'email': email,
                'access_token': token_response['access_token'],
                'refresh_token': token_response['refresh_token'],
                'expires_in': token_response.get('expires_in'),
                'token_type': token_response.get('token_type', 'Bearer')
            }
            
            filename = f"tokens_{email.split('@')[0]}.json"
            with open(filename, 'w') as f:
                json.dump(output, f, indent=2)
            
            print(f"\n💾 Tokens已保存到: {filename}")
            
            return output
        else:
            print(f"\n❌ Token响应异常:")
            print(json.dumps(token_response, indent=2))
            return None
    
    except Exception as e:
        print(f"\n❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        return None
    
    finally:
        await asyncio.sleep(3)
        await browser.close()
        await playwright.stop()


async def main():
    """主函数"""
    print("="*80)
    print("OpenAI Refresh Token 获取工具")
    print("="*80)
    
    # 从用户输入获取账号信息
    email = input("\n请输入OpenAI账号邮箱: ").strip()
    password = input("请输入密码: ").strip()
    
    if not email or not password:
        print("❌ 邮箱和密码不能为空")
        return
    
    print("\n开始获取refresh token...")
    print("="*80)
    
    result = await get_refresh_token(email, password)
    
    if result:
        print("\n" + "="*80)
        print("🎉 完成！")
        print("="*80)
        print("\n你现在可以使用refresh token来获取新的access token:")
        print(f"\nRefresh Token: {result['refresh_token']}")
        print("\n使用方法:")
        print("""
POST https://auth.openai.com/oauth/token
Content-Type: application/x-www-form-urlencoded

client_id=app_EMoamEEZ73f0CkXaXp7hrann&
grant_type=refresh_token&
refresh_token=YOUR_REFRESH_TOKEN
        """)
    else:
        print("\n" + "="*80)
        print("❌ 获取失败")
        print("="*80)


if __name__ == '__main__':
    asyncio.run(main())
