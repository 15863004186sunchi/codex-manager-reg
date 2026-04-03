import os
import sys
import json
import time
import tempfile
import shutil
from playwright.sync_api import sync_playwright

# Add project root to sys.path
sys.path.append(os.getcwd())

def launch_semi_auto_browser():
    print("=" * 60)
    print("🚀 OpenAI Semi-Auto Registration Tool (Clean Environment)")
    print("=" * 60)
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
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                    "--start-maximized"
                ],
                no_viewport=True
            )
            
            page = browser.new_page()
            if stealth_sync and callable(stealth_sync):
                stealth_sync(page)
                print("🛡️ [Stealth] Browser fingerprints successfully masked.")
            
            # Inject a floating button for easy extraction
            def inject_button(page):
                try:
                    page.evaluate("""() => {
                        if (document.getElementById('oai-extract-btn')) return;
                        const btn = document.createElement('button');
                        btn.id = 'oai-extract-btn';
                        btn.innerText = '🚀 点击提取 Token (Result in Terminal)';
                        btn.style.position = 'fixed';
                        btn.style.top = '10px';
                        btn.style.right = '10px';
                        btn.style.zIndex = '9999';
                        btn.style.padding = '10px 20px';
                        btn.style.backgroundColor = '#10a37f';
                        btn.style.color = 'white';
                        btn.style.border = 'none';
                        btn.style.borderRadius = '5px';
                        btn.style.cursor = 'pointer';
                        btn.style.fontWeight = 'bold';
                        btn.onclick = () => { window.__oai_trigger = true; btn.innerText = '⌛ 提取中...'; };
                        document.body.appendChild(btn);
                    }""")
                except:
                    pass

            # Navigate to ChatGPT
            print("\n[Action] Navigating to ChatGPT. Please perform sign-up/login manually.")
            page.goto("https://chatgpt.com/", wait_until="domcontentloaded")
            inject_button(page)
            
            print("-" * 60)
            print("🛑 STOP! Please perform the following steps in the browser:")
            print("  1. Click 'Sign up' or 'Log in'.")
            print("  2. Complete the email/password/OTP/Profile steps manually.")
            print("  3. ⚠️ 看浏览器右上角，有一个绿色的按钮 '点击提取 Token'")
            print("  4. 登录完成后，直接点击那个绿色按钮即可。")
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
                    # Execute the JS extraction script
                    token_data = page.evaluate("""async () => {
                        try {
                            const resp = await fetch('/api/auth/session');
                            if (!resp.ok) return { success: false, error: "Session endpoint returned " + resp.status };
                            const session = await resp.json();
                            const accessToken = session.accessToken;
                            if (!accessToken) return { success: false, error: "No accessToken in session" };
                            
                            const email = session?.user?.email || "unknown_email";
                            
                            // Parse Account ID from JWT
                            let account_id = "";
                            try {
                                const payloadBase64 = accessToken.split('.')[1];
                                let base = payloadBase64.replace(/-/g, '+').replace(/_/g, '/');
                                while (base.length % 4) base += '=';
                                const payloadText = atob(base);
                                // Ensure UTF-8 decoding
                                const payload = JSON.parse(decodeURIComponent(escape(payloadText)));
                                const authInfo = payload["https://api.openai.com/auth"];
                                if (authInfo && authInfo["chatgpt_account_id"]) {
                                    account_id = authInfo["chatgpt_account_id"];
                                }
                            } catch(e) { account_id = "default-uuid-fallback"; }
                            
                            return {
                                "access_token": accessToken,
                                "account_id": account_id,
                                "email": email,
                                "success": true
                            };
                        } catch(e) {
                            return { "success": false, "error": e.message };
                        }
                    }""")
                    
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
    launch_semi_auto_browser()
