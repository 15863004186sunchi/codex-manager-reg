import os
import sys
import logging
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)

sys.path.append(os.getcwd())

from src.core.anyauto.register_flow import AnyAutoRegistrationEngine
from src.core.anyauto.luckmail_client import LuckMailEmailService
from src.core.upload.cpa_upload import upload_to_cpa

# ==========================================
# CPA 平台配置 (可选)
# 如果需要自动上传到 CPA 平台，请设置 ENABLED 为 True 并填写 URL/TOKEN
# ==========================================
CPA_ENABLED = False
CPA_API_URL = ""
CPA_API_TOKEN = ""

# ==========================================
# 在这里填入你购买的动态住宅代理，或者 Proxy List 下载链接！
# 格式 1: "http://用户名:密码@代理地址:端口" (单节点自动轮换)
# 格式 2: "https://proxy.webshare.io/api/v2/proxy/list/download/... (提取API链接)
# ==========================================
GLOBAL_PROXY = "https://proxy.webshare.io/api/v2/proxy/list/download/ztaythmrvffodojlsdcahpdpxfudlgngtgktycld/AD-AE-AF-AG-AI-AL-AM-AO-AR-AT-AU-AW-AX-AZ-BA-BB-BD-BE-BF-BG-BH-BI-BJ-BM-BN-BO-BQ-BR-BS-BT-BW-BY-BZ-CA-CD-CG-CH-CI-CL-CM-CN-CO-CR-CU-CV-CW-CY-CZ-DJ-DK-DM-DO-DZ-EC-EE-EG-ER-ET-FI-FJ-FM-FO-GA-GB-GD-GE-GF-GG-GH-GI-GL-GM-GN-GP-GQ-GR-GT-GU-GW-GY-HK-HN-HR-HT-HU-ID-IE-IL-IM-IN-IQ-IR-IS-JE-JM-JO-JP-KE-KG-KH-KM-KN-KR-KW-KY-KZ-LA-LB-LC-LI-LK-LR-LS-LT-LU-LV-LY-MA-MC-MD-ME-MF-MG-MH-MK-ML-MM-MN-MO-MP-MQ-MR-MS-MT-MU-MV-MW-MX-MY-MZ-NA-NC-NE-NG-NI-NL-NO-NP-NZ-OM-PA-PE-PF-PG-PH-PK-PL-PR-PS-PT-PW-PY-QA-RE-RO-RS-RU-RW-SA-SB-SC-SD-SE-SG-SH-SI-SK-SL-SM-SN-SO-SR-SS-ST-SV-SX-SY-SZ-TC-TG-TH-TJ-TL-TN-TO-TR-TT-TW-TZ-UA-UG-US-UY-UZ-VC-VE-VG-VI-VN-VU-WS-YE-YT-ZA-ZM-ZW/any/username/backbone/-/?plan_id=13098254"

import urllib.request
import urllib.error
import random

def load_proxy_pool(proxy_input):
    if not proxy_input:
        return []
    
    if proxy_input.startswith("http") and "download" in proxy_input:
        print("🌍 正在从 Webshare API 下载代理列表池...")
        try:
            req = urllib.request.Request(proxy_input, headers={'User-Agent': 'Mozilla/5.0'})
            with urllib.request.urlopen(req, timeout=15) as resp:
                text_data = resp.read().decode('utf-8')
            
            lines = text_data.strip().split("\r\n")
            pool = []
            for line in lines:
                parts = line.strip().split(":")
                if len(parts) == 4:
                    ip, port, user, pwd = parts
                    pool.append(f"http://{user}:{pwd}@{ip}:{port}")
                elif len(parts) == 2:
                    pool.append(f"http://{line.strip()}")
            print(f"✅ 成功加载 {len(pool)} 个动态代理节点入池！\n")
            return pool
        except Exception as e:
            print(f"❌ 下载代理列表失败: {e}")
            return []
    else:
        return [proxy_input]

def save_token_info(email, password, result):
    """
    将注册成功的账号信息保存为 CPA 格式的 JSON 并尝试上传
    """
    token_dir = "tokens"
    if not os.path.exists(token_dir):
        os.makedirs(token_dir)
        
    # 构造 CPA 格式的 JSON (严格对齐 src/core/upload/cpa_upload.py 的 generate_token_json)
    # 同时也保留 session_token，因为 Codex 类型通常需要此项
    metadata = result.get("metadata", {})
    
    token_data = {
        "type": "codex",
        "email": email,
        "password": password, # 原始密码，供参考
        "expired": metadata.get("expires", ""), 
        "id_token": result.get("id_token", ""),
        "account_id": result.get("account_id", ""),
        "access_token": result.get("access_token", ""),
        "session_token": result.get("session_token", ""), # 重要：Session 复用流的核心
        "refresh_token": result.get("refresh_token", ""),
        "last_refresh": time.strftime("%Y-%m-%dT%H:%M:%S+08:00"),
    }
    
    # 也可以把完整的 metadata 挂载进去，不影响主要字段解析
    token_data["metadata"] = metadata
    
    file_path = os.path.join(token_dir, f"{email}.json")
    try:
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(token_data, f, ensure_ascii=False, indent=2)
        print(f"📂 成功存档 Token 文件: {file_path}")
    except Exception as e:
        print(f"⚠️ 存档 Token 文件失败: {e}")

    # 如果启用了 CPA 上传
    if CPA_ENABLED and CPA_API_URL and CPA_API_TOKEN:
        print(f"📡 正在尝试上传到 CPA: {email}...")
        try:
            success, msg = upload_to_cpa(
                token_data=token_data, 
                api_url=CPA_API_URL, 
                api_token=CPA_API_TOKEN
            )
            if success:
                print(f"✅ CPA 上传成功！")
            else:
                print(f"⚠️ CPA 上传失败: {msg}")
        except Exception as e:
            print(f"❌ CPA 上传过程中发生异常: {e}")

def parse_accounts_file(filepath):
    accounts = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if "----tok_" in line:
                parts = line.split("----")
                if len(parts) >= 2:
                    accounts.append((parts[0].strip(), parts[1].strip()))
    return accounts

def main():
    print("=" * 60)
    print("🚀 OpenAI 批量自动注册工具 (Batch + LuckMail + Hybrid)")
    print("=" * 60)

    filename = r"E:\AILearn\20260321codexconsole\codex-console\hotmail三次购买200个.txt"

    if not os.path.exists(filename):
        print(f"文件不存在: {filename}，退出。")
        return

    accounts = parse_accounts_file(filename)
    if not accounts:
        print("未从文件中解析到符合 email----tok_ 格式的账号！退出。")
        return

    print(f"成功加载 {len(accounts)} 个邮箱账号！\n")

    # 构建代理池
    proxy_pool = load_proxy_pool(GLOBAL_PROXY)

    # 配置 LuckMail 服务
    luckmail_base_url = "https://api.luckmail.net"
    
    luckmail_service = LuckMailEmailService(base_url=luckmail_base_url, api_key="")
    
    success_count = 0
    
    for idx, (email, token) in enumerate(accounts):
        print("\n" + "-" * 50)
        print(f"⏳ [{idx+1}/{len(accounts)}] 开始处理: {email}")
        print("-" * 50)
        
        # 将 token 注册进去
        luckmail_service.register_token(email, token)
        
        # 告诉 service 当前正在处理哪个邮箱，以供 `create_email` 接口调用
        luckmail_service.current_email = email
        
        # 注意：此处引擎重建！
        try:
            engine = AnyAutoRegistrationEngine(
                email_service=luckmail_service,
                browser_mode="hybrid",
                callback_logger=lambda m: logging.info(f"[Engine] {m}")
            )
            
            # 从代理池中随机捞取一个给当前流程
            if proxy_pool:
                engine.proxy_url = random.choice(proxy_pool)
                
            result = engine.run()
            
            if result.get("success"):
                print(f"🎉 注册成功！ {email}")
                success_count += 1
                # 存档并上传
                save_token_info(email, token, result)
            else:
                print(f"❌ 注册失败: {result.get('error_message', 'Unknown Error')}")
                
        except Exception as e:
             print(f"💥 这个账号执行过程中发生严重异常: {e}")
             import traceback
             traceback.print_exc()
             
        # 短暂休息后进入下一个
        print(f"目前进度: 成功 {success_count} / 处理的 {idx+1}")
        time.sleep(3)

    print("=" * 60)
    print(f"🎊 批量大跑批结束！总计处理 {len(accounts)} 个，成功注册 {success_count} 个！")
    print("=" * 60)

if __name__ == "__main__":
    main()
