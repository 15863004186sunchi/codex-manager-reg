import random
import sys
import json
import time
import tempfile
import shutil
import argparse
import os
from playwright.sync_api import sync_playwright

# --- Chrome Profiles for Fingerprinting ---
_CHROME_PROFILES = [
    {"major": 131, "build": 6778, "patch_range": (69, 205), "sec_ch_ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"'},
    {"major": 133, "build": 6943, "patch_range": (33, 153), "sec_ch_ua": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"'},
    {"major": 136, "build": 7103, "patch_range": (48, 175), "sec_ch_ua": '"Chromium";v="136", "Google Chrome";v="136", "Not.A/Brand";v="99"'},
]

def _random_chrome_version():
    profile = random.choice(_CHROME_PROFILES)
    full_ver = f"{profile['major']}.0.{profile['build']}.{random.randint(*profile['patch_range'])}"
    ua = f"Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{full_ver} Safari/537.36"
    return full_ver, ua, profile["sec_ch_ua"]

# Add project root to sys.path
sys.path.append(os.getcwd())

def launch_semi_auto_browser(proxy_override=None):
    print("=" * 60)
    print("🚀 OpenAI Semi-Auto Registration Tool (Stealth + Proxy)")
    print("=" * 60)
    
    # Fingerprint Randomization
    chrome_full, user_agent, sec_ch_ua = _random_chrome_version()
    print(f"🎭 [Fingerprint] Using Chrome/{chrome_full}")
    print(f"🌍 [Fingerprint] UA: {user_agent}")
    
    # Proxy Detection
    proxy_config = None
    if proxy_override:
        print(f"🌐 [Proxy] Using manual override: {proxy_override}")
        proxy_config = {"server": proxy_override}
    else:
        proxy_file = os.path.join("data", "proxies_webshare.txt")
        if os.path.exists(proxy_file):
            try:
                with open(proxy_file, "r") as f:
                    proxies = [l.strip() for l in f if l.strip() and not l.startswith("#")]
                if proxies:
                    p_url = random.choice(proxies)
                    # Webshare format: host:port:user:pass
                    parts = p_url.split(":")
                    if len(parts) == 4:
                        host, port, user, pwd = parts
                        proxy_config = {
                            "server": f"http://{host}:{port}",
                            "username": user,
                            "password": pwd
                        }
                        print(f"🌐 [Proxy] Using Webshare: {host}:{port}")
                    else:
                        proxy_config = {"server": p_url}
                        print(f"🌐 [Proxy] Using Raw: {p_url}")
            except Exception as e:
                print(f"⚠️ [Proxy] Failed to load proxy list: {e}")
        else:
            print("💡 [Proxy] No proxy file found, using Direct connection.")
    
    print("[Status] Initializing clean browser profile...")

    with sync_playwright() as p:
        # Create a temporary directory for the browser profile
        with tempfile.TemporaryDirectory() as temp_dir:
            print(f"[Status] Profile created at: {temp_dir}")
            
            # Use stealth plugin if available
            stealth_sync = None
            try:
                import playwright_stealth as ps
                stealth_sync = getattr(ps, 'stealth_sync', getattr(ps, 'stealth', None))
                # Deep probe for callable
                if stealth_sync and not hasattr(stealth_sync, '__call__'):
                    if hasattr(stealth_sync, 'stealth_sync'):
                        stealth_sync = getattr(stealth_sync, 'stealth_sync')
                    elif hasattr(stealth_sync, 'stealth'):
                        stealth_sync = getattr(stealth_sync, 'stealth')
            except Exception:
                print("[Warning] Failed to load playwright-stealth, fingerprint might be generic.")

            # Launch headful browser
            browser = p.chromium.launch_persistent_context(
                user_data_dir=temp_dir,
                headless=False,
                proxy=proxy_config,
                user_agent=user_agent,
                extra_http_headers={
                    "sec-ch-ua": sec_ch_ua,
                    "sec-ch-ua-mobile": "?0",
                    "sec-ch-ua-platform": '"Windows"',
                },
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized"
                ],
                no_viewport=True
            )
            
            page = browser.new_page()
            
            # --- Network Interception for Real Tokens ---
            captured_tokens = {"refresh_token": None, "access_token": None}
            def handle_response(response):
                try:
                    if "/api/auth/callback/openai" in response.url or "/oauth/token" in response.url:
                        if response.status == 200:
                            data = response.json()
                            if "refresh_token" in data:
                                captured_tokens["refresh_token"] = data["refresh_token"]
                                print(f"📡 [Network] Detected Real Refresh Token in {response.url.split('/')[-1]}")
                            if "access_token" in data:
                                captured_tokens["access_token"] = data["access_token"]
                except:
                    pass
            page.on("response", handle_response)

            if stealth_sync and callable(stealth_sync):
                stealth_sync(page)
                print("🛡️ [Stealth] Browser fingerprints successfully masked.")
            
            # 注入一个浮动按钮，方便手动提取
            def inject_button(page):
                try:
                    page.evaluate("""() => {
                        if (document.getElementById('oai-extract-btn')) return;
                        const btn = document.createElement('button');
                        btn.id = 'oai-extract-btn';
                        btn.innerText = '🚀 提取并存档 Token';
                        btn.style.position = 'fixed';
                        btn.style.bottom = '20px';
                        btn.style.right = '20px';
                        btn.style.zIndex = '9999';
                        btn.style.padding = '15px 25px';
                        btn.style.backgroundColor = '#10a37f';
                        btn.style.color = 'white';
                        btn.style.border = 'none';
                        btn.style.borderRadius = '30px';
                        btn.style.cursor = 'pointer';
                        btn.style.boxShadow = '0 4px 12px rgba(0,0,0,0.2)';
                        btn.style.fontWeight = 'bold';
                        btn.style.fontSize = '16px';
                        btn.onclick = () => { 
                            if (window.__oai_extracting) return;
                            window.__oai_trigger = true; 
                            window.__oai_extracting = true;
                            btn.innerText = '⌛ 正在提取 (请稍后)...';
                            btn.style.backgroundColor = '#666';
                        };
                        document.body.appendChild(btn);
                    }""")
                except:
                    pass

            # Navigate to ChatGPT
            print("\n[Action] Navigating to ChatGPT. Please perform sign-up/login manually.")
            page.goto("https://chatgpt.com/", wait_until="domcontentloaded")
            inject_button(page)
            
            print("-" * 60)
            print("🛑 操作指引 (STOP! Please read):")
            print("  1. 正常完成邮箱/密码/验证码/个人资料填写。")
            print("  2. 【关键】等到进入聊天界面（左侧出现对话列表）后。")
            print("  3. 点击右下角绿色按钮 '🚀 提取并存档 Token'")
            print("  4. 如果按钮一直转圈，说明浏览器当前环境不稳定，请刷新页面后重试。")
            print("-" * 60)
            
            while True:
                # Poll for browser trigger or wait for terminal input (Non-blocking check)
                is_triggered = False
                try:
                    is_triggered = page.evaluate("window.__oai_trigger")
                except:
                    pass
                
                if not is_triggered:
                    # Provide terminal fallback (using a short timeout logic if possible, or just print)
                    time.sleep(1)
                    # Re-inject button if navigation happened
                    inject_button(page)
                    # Use a non-blocking check for stdin if possible, or just rely on the button
                    continue

                # Reset trigger
                page.evaluate("window.__oai_trigger = false")
                
                print("\n[Trigger] Detected browser button click! Extracting...")
                try:
                    # Capture all cookies beforehand
                    all_cookies = browser.cookies()
                    refresh_token = captured_tokens["refresh_token"] # Prioritize real one from network
                    if not refresh_token:
                        refresh_token = next((c['value'] for c in all_cookies if 'refresh-token' in c['name']), None)
                    
                    session_token = next((c['value'] for c in all_cookies if 'session-token' in c['name']), None)
                    
                    # Execute the JS extraction script
                    token_data = page.evaluate("""async (in_rt, in_st) => {
                        try {
                            const fetchTask = fetch('/api/auth/session').then(r => r.json());
                            const timeoutTask = new Promise((_, reject) => setTimeout(() => reject(new Error('Fetch Timeout (10s)')), 10000));
                            
                            const session = await Promise.race([fetchTask, timeoutTask]);
                            const accessToken = session.accessToken || in_st;
                            if (!accessToken) return { success: false, error: "No accessToken or session-token found." };
                            
                            const email = session?.user?.email || "unknown_email";
                            
                            // Reconstruction of Codex Manager format
                            const now = new Date();
                            const expired = new Date(now.getTime() + 10 * 24 * 60 * 60 * 1000); // +10 days
                            
                            // Parse Account ID from JWT
                            let account_id = "";
                            try {
                                const payloadBase64 = accessToken.split('.')[1];
                                let base = payloadBase64.replace(/-/g, '+').replace(/_/g, '/');
                                while (base.length % 4) base += '=';
                                const payloadText = atob(base);
                                const payload = JSON.parse(decodeURIComponent(escape(payloadText)));
                                const authInfo = payload["https://api.openai.com/auth"];
                                if (authInfo && authInfo["chatgpt_account_id"]) {
                                    account_id = authInfo["chatgpt_account_id"];
                                }
                            } catch(e) { account_id = "default-uuid-fallback"; }
                            
                            return {
                                "id_token": accessToken,
                                "access_token": accessToken,
                                "refresh_token": in_rt || accessToken, // Use real RT if found, fallback to AT
                                "account_id": account_id,
                                "last_refresh": now.toISOString().replace('.000', ''),
                                "email": email,
                                "type": "codex",
                                "expired": expired.toISOString().replace('.000', ''),
                                "success": true
                            };
                        } catch(e) {
                            return { "success": false, "error": e.message };
                        }
                    }""", refresh_token, session_token)
                    
                    if token_data.get("success"):
                        # Save to file
                        os.makedirs("data", exist_ok=True)
                        timestamp = int(time.time())
                        save_filename = f"ChatGPT_Token_{token_data['email'].split('@')[0]}_{timestamp}.json"
                        save_path = os.path.join("data", save_filename)
                        abs_save_path = os.path.abspath(save_path)
                        
                        with open(save_path, "w", encoding="utf-8") as f:
                            json.dump(token_data, f, indent=4, ensure_ascii=False)
                        
                        print(f"✅ [Result] 提取成功！")
                        print(f"📧 邮箱: {token_data['email']}")
                        print(f"💾 文件已在本地生成: {abs_save_path}")
                        print(f"📁 提示：请不要看浏览器的下载，文件在工程目录的 data 文件夹里！")
                        
                        # Auto-open the data folder on Windows
                        if os.name == 'nt':
                            try:
                                os.startfile(os.path.dirname(abs_save_path))
                            except:
                                pass
                    else:
                        print(f"❌ Extraction Failed: {token_data.get('error')}")
                        print("Tip: Make sure you are fully logged in and on the chatgpt.com domain.")
                        
                except Exception as e:
                    print(f"💥 Runtime error during extraction: {e}")

            browser.close()
            print("\n[Status] Browser session closed. Clean-up complete.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="OpenAI Semi-Auto Registration Tool")
    parser.add_argument("--proxy", help="Manual proxy override (host:port or user:pass@host:port)")
    args = parser.parse_args()
    
    try:
        launch_semi_auto_browser(proxy_override=args.proxy)
    except KeyboardInterrupt:
        print("\n👋 User terminated session.")
    except Exception as e:
        print(f"\n💥 Fatal Error: {e}")
