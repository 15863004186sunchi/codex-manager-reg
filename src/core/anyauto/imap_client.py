import imaplib
import email
import re

class ImapEmailService:
    def __init__(self, imap_port=993):
        # 预设多个可能的微软 IMAP 服务器地址，增加兼容性
        self.imap_servers = ["outlook.office365.com", "imap-mail.outlook.com", "imap.glbdns2.microsoft.com"]
        self.imap_port = imap_port
        self.credentials_map = {} # email -> password
        self.current_email = None

    def register_credentials(self, email, password):
        self.credentials_map[email.lower()] = password

    def create_email(self):
        """兼容 AnyAutoRegistrationEngine 的取号接口"""
        if self.current_email:
            return {"email": self.current_email, "service_id": "imap_mail"}
        return None

    def get_verification_code(self, email, email_id=None, timeout=60, otp_sent_at=None):
        email_normalized = email.lower()
        password = self.credentials_map.get(email_normalized)
        if not password:
            print(f"[IMAP] ❌ 严重错误: 未在内存中找到邮箱 {email_normalized} 的登录密码！请检查导入流程。")
            return None
        
        print(f"[IMAP] ✨ 准备读取 {email_normalized} 的邮件 (使用密码长度: {len(password)})")
        
        # 尝试遍历不同的 IMAP 服务器
        for server in self.imap_servers:
            print(f"[IMAP] 正在尝试连接服务器: {server}...")
            try:
                # 登录 IMAP
                mail = imaplib.IMAP4_SSL(server, self.imap_port, timeout=20)
                mail.login(email_normalized, password)
                mail.select("INBOX")
                
                # ... 搜索逻辑保持不变 ...
                status, messages = mail.search(None, '(FROM "noreply@tm.openai.com")')
                
                if status == "OK" and messages[0]:
                    mail_ids = messages[0].split()
                    if mail_ids:
                        # 获取最新的一封邮件
                        latest_email_id = mail_ids[-1]
                        status, msg_data = mail.fetch(latest_email_id, '(RFC822)')
                        
                        for response_part in msg_data:
                            if isinstance(response_part, tuple):
                                msg = email.message_from_bytes(response_part[1])
                                
                                # 提取正文
                                body = ""
                                if msg.is_multipart():
                                    for part in msg.walk():
                                        if part.get_content_type() in ["text/plain", "text/html"]:
                                            body_bytes = part.get_payload(decode=True)
                                            if body_bytes:
                                                body = body_bytes.decode(errors="ignore")
                                                break
                                else:
                                    body_bytes = msg.get_payload(decode=True)
                                    if body_bytes:
                                        body = body_bytes.decode(errors="ignore")
                                
                                # 正则匹配 6 位数字验证码
                                match = re.search(r'\b\d{6}\b', body)
                                if match:
                                    code = match.group()
                                    print(f"[IMAP] ✅ 成功从 {server} 获取到验证码: {code}")
                                    mail.logout()
                                    return code
                mail.logout()
                # 如果这个服务器能登录但没邮件，可能还没发过来，不要换服务器，直接等下一轮轮询
                return None
            except imaplib.IMAP4.error as e:
                print(f"[IMAP] ⚠️  {server} 登录失败: {e}")
                # 继续尝试下一个服务器
                continue
            except Exception as e:
                print(f"[IMAP] 💀 {server} 连接异常: {e}")
                continue
            
        print(f"[IMAP] ❌ 所有预设服务器均无法登录 {email_normalized}，请检查账号状态。")
        return None
