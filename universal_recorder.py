import os
import sys
import json
import time
import asyncio
import base64
import shutil
from typing import Dict, Any
from playwright.async_api import async_playwright, Page, Request, Response

# 流量存储路径
TRAFFIC_DATA_PATH = "data/universal_trace.jsonl"

async def log_entry(entry: Dict[str, Any]):
    """将一条流量条目写入 JSONL 文件"""
    os.makedirs("data", exist_ok=True)
    with open(TRAFFIC_DATA_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

async def handle_request(request: Request):
    """处理捕获的请求"""
    try:
        if request.resource_type in ["image", "font", "stylesheet", "media"]:
            return

        # 尝试安全地获取 post_data
        post_data = None
        try:
            post_data = request.post_data
        except Exception:
            # 如果是二进制数据，尝试用 base64 记录
            try:
                buffer = request.post_data_buffer
                if buffer:
                    post_data = f"[Base64] {base64.b64encode(buffer).decode('ascii')}"
            except:
                post_data = "[Binary data - unable to capture]"

        entry = {
            "time": time.time(),
            "type": "request",
            "method": request.method,
            "url": request.url,
            "headers": request.headers,
            "post_data": post_data,
        }
        await log_entry(entry)
    except Exception as e:
        pass

async def handle_response(response: Response):
    """处理捕获的响应"""
    try:
        if response.request.resource_type in ["image", "font", "stylesheet", "media"]:
            return

        # 尝试解析响应体
        body = ""
        try:
            content_type = response.headers.get("content-type", "").lower()
            if "json" in content_type:
                body = await response.json()
            elif "text" in content_type or "javascript" in content_type or "xml" in content_type:
                text = await response.text()
                body = text[:5000] # 限制长度
            else:
                body = "[Non-text content]"
        except Exception:
            body = "[Error decoding body or binary content]"

        entry = {
            "time": time.time(),
            "type": "response",
            "url": response.url,
            "status": response.status,
            "headers": response.headers,
            "body": body,
        }
        await log_entry(entry)
    except Exception as e:
        pass

async def main():
    print("=" * 60)
    print("🚀 Universal Flow Recorder (Robust Version)")
    print("=" * 60)
    
    if os.path.exists(TRAFFIC_DATA_PATH):
        os.remove(TRAFFIC_DATA_PATH)
        print(f"已清理旧数据: {TRAFFIC_DATA_PATH}")

    # 清理浏览器 Profile 保证环境纯净
    user_data_dir = os.path.abspath("data/browser_profile")
    if os.path.exists(user_data_dir):
        try:
            shutil.rmtree(user_data_dir)
            print(f"已清理旧浏览器 Profile: {user_data_dir}")
        except Exception as e:
            print(f"[Warning] 无法清理 Profile 目录: {e}")

    async with async_playwright() as p:
        chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome-sunchi.exe"
        
        try:
            browser_context = await p.chromium.launch_persistent_context(
                user_data_dir=user_data_dir,
                executable_path=chrome_path if os.path.exists(chrome_path) else None,
                headless=False,
                args=[
                    "--no-sandbox",
                    "--disable-blink-features=AutomationControlled",
                ],
                viewport={"width": 1280, "height": 800}
            )
        except Exception as e:
            print(f"\n[Error] 启动浏览器失败: {e}")
            return

        page = await browser_context.new_page()
        page.on("request", handle_request)
        page.on("response", handle_response)

        print("\n[Status] 浏览器已启动。")
        print("[Status] 操作说明：")
        print("  1. 在浏览器中完成注册/登录。")
        print("  2. 完成后直接关闭浏览器窗口或按 Ctrl+C 结束。")
        print("-" * 50)
        
        try:
            # 默认跳转到 chatgpt.com
            await page.goto("https://chatgpt.com/", wait_until="networkidle")
        except Exception:
            pass

        while True:
            try:
                if browser_context.browser and not browser_context.browser.is_connected():
                    break
                if page.is_closed():
                    break
                await asyncio.sleep(1)
            except:
                break

        print("\n" + "=" * 60)
        print(f"✅ 录制结束！流量已保存。")
        print("=" * 60)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[Status] 用户手动中断。")
    except Exception as e:
        print(f"\n[Error] 运行失败: {e}")
