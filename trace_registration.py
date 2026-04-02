import os
import sys
import asyncio
import logging

# 将项目根目录添加到 python 路径
sys.path.append(os.getcwd())

# 强制开启流量追踪
os.environ["TRAFFIC_TRACE"] = "1"

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler()]
)

from src.core.anyauto.register_flow import AnyAutoRegistrationEngine

class MockEmailService:
    def __init__(self, email):
        self.email = email
    def create_email(self):
        return {"email": self.email, "service_id": "mock_id"}
    def get_verification_code(self, **kwargs):
        print(f"\n[Manual Action Required] 请检查邮箱 {self.email} 并输入验证码:")
        return sys.stdin.readline().strip()

async def trace_main():
    print("=" * 50)
    print("🚀 OpenAI 注册流量追踪工具 (Trace Mode)")
    print("=" * 50)
    
    # 清理旧的追踪数据
    if os.path.exists("data/traffic_trace.json"):
        os.remove("data/traffic_trace.json")
        print("已清理旧的 data/traffic_trace.json")

    # 1. 设置你想测试的邮箱（建议使用你手动注册时用的同一个邮箱前缀，或者随便填）
    target_email = input("请输入用于测试的邮箱地址 (例如: test_trace_99@outlook.com): ").strip()
    if not target_email:
        target_email = f"trace_{os.urandom(3).hex()}@outlook.com"
        
    mock_email_service = MockEmailService(target_email)
    
    # 2. 初始化引擎 (AnyAuto V2)
    # 启用混合驱动模式绕过 Sentinel
    engine = AnyAutoRegistrationEngine(
        email_service=mock_email_service,
        browser_mode="hybrid"
    )
    
    print(f"\n正在启动注册流程 (Email: {target_email})...")
    print("请等待流程执行，脚本会自动捕获所有 HTTP 请求。")
    print("-" * 50)
    
    try:
        # 运行引擎
        # 即使被 Cloudflare 拦截，记录下来的 403 响应头对我也非常有价值
        result = engine.run()
        
        print("\n" + "=" * 50)
        if result.get("success"):
            print(f"✅ 录制完成（注册成功）")
        else:
            print(f"❌ 录制流程结束（结果: {result.get('error_message')}）")
        print("=" * 50)
        print(f"流量数据已保存至 (JSON 每一行是一个请求/响应):")
        print(os.path.abspath('data/traffic_trace.json'))
        print("\n请将该文件返回给我进行分析。")

    except Exception as e:
        print(f"\n💥 脚本运行崩溃: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # AnyAutoRegistrationEngine.run 是同步的
    async def run_sync_in_async():
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, trace_main_sync)

    def trace_main_sync():
        asyncio.run(trace_main())

    trace_main_sync()
