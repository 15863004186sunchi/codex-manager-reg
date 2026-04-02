import sys
from luckmail import LuckMailClient

class LuckMailEmailService:
    def __init__(self, base_url="https://luckmail.pro", api_key=""):
        # 由于我们使用的是基于 Token 的 API，部分平台允许留空 API Key
        self.client = LuckMailClient(base_url=base_url, api_key=api_key)
        self.email_token_map = {}
        self.current_email = None

    def register_token(self, email, token):
        self.email_token_map[email] = token

    def create_email(self):
        """兼容 AnyAutoRegistrationEngine 的取号接口"""
        if self.current_email:
            return {"email": self.current_email, "service_id": "luckmail"}
        return None

    def wait_for_verification_code(self, email, timeout=120):
        """兼容 AnyAutoRegistrationEngine 的取码接口"""
        token = self.email_token_map.get(email)
        if not token:
            print(f"[LuckMail] 未找到邮箱 {email} 关联的 Token！")
            return None
        
        print(f"[LuckMail] ✨ 正在使用 Token {token[:10]}... 等待 {email} 的验证码...")
        try:
            # 轮询获取
            result = self.client.user.wait_for_token_code(token, timeout=timeout)
            if result and getattr(result, "has_new_mail", False):
                match = result.verification_code
                print(f"[LuckMail] ✅ 成功获取验证码: {match}")
                return match
            else:
                print(f"[LuckMail] ❌ 未收到最新邮件，或者已超时。")
        except Exception as e:
            print(f"[LuckMail] 💀 等待验证码异常: {e}")
        
        return None
