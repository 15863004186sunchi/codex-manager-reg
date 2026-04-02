import imaplib
import email
import re

class ImapEmailService:
    def __init__(self, imap_server="imap-mail.outlook.com", imap_port=993):
        self.imap_server = imap_server
        self.imap_port = imap_port
        self.credentials_map = {} # email -> password
        self.current_email = None

    def register_credentials(self, email_addr, password):
        self.credentials_map[email_addr] = password

    def create_email(self):
        """兼容 AnyAutoRegistrationEngine 的取号接口"""
        if self.current_email:
            return {"email": self.current_email, "service_id": "imap_mail"}
        return None

    def get_verification_code(self, email_addr, email_id=None, timeout=60, otp_sent_at=None):
        password = self.credentials_map.get(email_addr)
        if not password:
            print(f"[IMAP] 未找到邮箱 {email_addr} 关联的密码！")
            return None
        
        print(f"[IMAP] ✨ 正在连接 {self.imap_server} 读取 {email_addr} 的邮件...")
        try:
            # 登录 IMAP
            mail = imaplib.IMAP4_SSL(self.imap_server, self.imap_port)
            mail.login(email_addr, password)
            mail.select("INBOX")

            # 搜索来自 OpenAI 的邮件
            status, messages = mail.search(None, '(FROM "noreply@tm.openai.com")')
            
            if status == "OK" and messages[0]:
                mail_ids = messages[0].split()
                if not mail_ids:
                    return None
                    
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
                                if part.get_content_type() == "text/plain" or part.get_content_type() == "text/html":
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
                            print(f"[IMAP] ✅ 成功获取到验证码: {code}")
                            mail.logout()
                            return code
            mail.logout()
        except imaplib.IMAP4.error as e:
            print(f"[IMAP] ⚠️ IMAP 登录被拒绝，可能账号被冻结或密码错误: {e}")
            # 如果账号已死，返回 "ERROR" 等标识可以让上层停止 polling，但这里为了兼容返回 None
        except Exception as e:
            print(f"[IMAP] 💀 IMAP 读取异常: {e}")
            
        return None
