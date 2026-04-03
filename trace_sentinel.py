import os
import sys
import asyncio
import json
import time
import logging
from urllib.parse import urlparse

# Add project root to sys.path
sys.path.append(os.getcwd())

# Force traffic tracing for underlying http_client
os.environ["TRAFFIC_TRACE"] = "1"

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("Sentinel-Tracer")

# Imports from project
from src.core.anyauto.chatgpt_client import ChatGPTClient
from src.core.anyauto.imap_client import ImapEmailService
from src.core.anyauto.utils import generate_random_name, generate_random_birthday

async def trace_sentinel_flow():
    print("=" * 60)
    print("🚀 OpenAI Sentinel Flow Tracer (High-Fidelity HAR Mode)")
    print("=" * 60)
    
    # 1. Config
    master_email = "geeksunchi@gmail.com"
    master_pass = "jcfk oprb igpm wbwh"
    domain = "flapysun.com"
    
    # Generate a fresh test identity
    first_name, last_name = generate_random_name()
    email_alias = f"{first_name.lower()}.{last_name.lower()}{os.urandom(2).hex()}@{domain}"
    password = f"P@ss{os.urandom(4).hex()}"
    birthdate = generate_random_birthday()
    
    print(f"📧 测试邮箱: {email_alias}")
    print(f"👤 测试身份: {first_name} {last_name} | 生日: {birthdate}")
    print(f"🔑 测试密码: {password}")
    print("-" * 60)

    # 2. Setup Services
    imap_service = ImapEmailService(
        host="imap.gmail.com",
        user=master_email,
        password=master_pass,
        port=993
    )
    
    client = ChatGPTClient(
        email=email_alias,
        password=password,
        proxy=None, # Use system proxy if needed
        browser_mode="hybrid"
    )
    
    # 3. Custom Flow with Extra Logging
    print("\n[Step 1] Initializing ChatGPT Session...")
    try:
        # Pre-registration steps (API level)
        client.session.get("https://chatgpt.com/", timeout=30)
        csrf = client._get_csrf_token()
        print(f"✅ CSRF Token Obtained: {csrf[:15]}...")
        
        # Submit email
        submit_url = f"{client.AUTH}/api/accounts/user/register"
        r = client.session.post(submit_url, json={"email": email_alias}, allow_redirects=True)
        auth_url = str(r.url)
        print(f"✅ Authorize URL Obtained: {auth_url[:50]}...")
        
        # Start Playwright Hybrid Flow
        print("\n[Step 2] Launching Playwright Flow (Headful/Stealth)...")
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            # Note: We use launch instead of launch_persistent_context for cleaner tracing
            browser = p.chromium.launch(headless=False, args=["--no-sandbox", "--disable-blink-features=AutomationControlled"])
            context = browser.new_context(user_agent=client.ua)
            
            # Global Listeners for maximum diagnostic visibility
            page = context.new_page()
            page.on("framenavigated", lambda frame: logger.info(f"🚩 [Nav] {frame.url}"))
            page.on("requestfailed", lambda req: logger.warning(f"❌ [Network] {req.url} -> {req.failure.error_text}"))
            
            # Start Recording
            print(f"👉 访问授权页...")
            page.goto(auth_url, wait_until="domcontentloaded")
            
            # Handle Password Submission with "Oops" detection
            input_pw = "input[type='password'], [name='password']"
            page.wait_for_selector(input_pw, timeout=30000)
            client._human_type(page, input_pw, password)
            
            logger.info("🖱️ 点击 Continue 提交密码...")
            client._human_click(page, "button[type='submit'], button:has-text('Continue')")
            
            # Wait and check for Oops or Sentinel
            page.wait_for_timeout(5000)
            if "Oops" in page.title() or page.locator("button:has-text('Try again')").is_visible():
                logger.error("🛑 命中 Oops/Sentinel 拦截页面！")
                client._inspect_page(page, "[Block Detected]")
                
                logger.info("🔄 点击 Try again 并等待 Sentinel 框架加载...")
                page.locator("button:has-text('Try again')").click(force=True)
                page.wait_for_timeout(5000)
                
                # Check for sentinel frames
                frames = page.frames
                sentinel_frames = [f for f in frames if "sentinel" in f.url]
                if sentinel_frames:
                    logger.info(f"📊 发现 {len(sentinel_frames)} 个 Sentinel 框架，正在等待它们执行...")
                    # Usually we just wait for the main page to enable the Continue button or redirect
                
                logger.info("🔁 尝试二次重试提交...")
                client._human_click(page, "button[type='submit'], button:has-text('Continue')")
            
            # Wait for OTP
            logger.info("⏳ 等待跳转至 email-verification...")
            try:
                page.wait_for_url("**/email-verification**", timeout=15000)
            except:
                logger.warning(f"⚠️ 未能自动跳转至验证码页，当前 URL: {page.url}")
            
            # Capture Final State
            page.screenshot(path="sentinel_trace_final.png")
            print("\n✅ 追踪运行结束。请检查屏幕截图 sentinel_trace_final.png 和控制台日志。")
            
            browser.close()

    except Exception as e:
        logger.exception(f"💥 追踪过程中崩溃: {e}")

if __name__ == "__main__":
    asyncio.run(trace_sentinel_flow())
