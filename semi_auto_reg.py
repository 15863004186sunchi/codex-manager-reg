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
            
            # Navigate to ChatGPT
            print("\n[Action] Navigating to ChatGPT. Please perform sign-up/login manually.")
            page.goto("https://chatgpt.com/", wait_until="domcontentloaded")
            
            print("-" * 60)
            print("🛑 STOP! Please perform the following steps in the browser:")
            print("  1. Click 'Sign up' or 'Log in'.")
            print("  2. Complete the email/password/OTP/Profile steps manually.")
            print("  3. Once you see the ChatGPT chat interface, come back to this terminal.")
            print("-" * 60)
            
            while True:
                user_cmd = input("\n[Trigger] Press Enter to extract token, or type 'exit' to quit: ").strip().lower()
                
                if user_cmd == 'exit':
                    break
                
                print("⏳ Extracting session token from ChatGPT...")
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
                    
                    if token_data.get("success"):
                        print(f"✅ Token Extracted Successfully!")
                        print(f"📧 Email: {token_data['email']}")
                        print(f"🆔 Account ID: {token_data['account_id']}")
                        print(f"🔑 Session Token: {token_data['access_token'][:30]}...")
                        
                        # Save to file
                        os.makedirs("data", exist_ok=True)
                        save_path = f"data/manual_token_{int(time.time())}.json"
                        with open(save_path, "w", encoding="utf-8") as f:
                            json.dump(token_data, f, indent=4, ensure_ascii=False)
                        print(f"💾 Data saved to: {save_path}")
                    else:
                        print(f"❌ Extraction Failed: {token_data.get('error')}")
                        print("Tip: Make sure you are fully logged in and on the chatgpt.com domain.")
                        
                except Exception as e:
                    print(f"💥 Runtime error during extraction: {e}")

            browser.close()
            print("\n[Status] Browser session closed. Clean-up complete.")

if __name__ == "__main__":
    launch_semi_auto_browser()
