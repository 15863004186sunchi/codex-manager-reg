import imaplib
import email
import re

class ImapEmailService:
    def __init__(self, imap_port=993):
        # 预设多个可能的服务器地址
        self.imap_servers = ["imap.gmail.com", "outlook.office365.com", "imap-mail.outlook.com"]
        self.imap_port = imap_port
        self.credentials_map = {} # email -> password
        self.current_email = None
        
        # [NEW] Master Account Mode (用于 Catch-all)
        self.master_email = None
        self.master_password = None

    def set_master_account(self, email, password):
        """设置统一的中转接收邮箱（用于 Cloudflare 转发等场景）"""
        self.master_email = email
        self.master_password = password
        print(f"[IMAP] 🏁 已开启统一中转模式: 所有邮件将从中转站 {email} 读取。")
        
    def register_credentials(self, email, password):
        self.credentials_map[email.lower()] = password

    def create_email(self):
        """兼容 AnyAutoRegistrationEngine 的取号接口"""
        if self.current_email:
            return {"email": self.current_email, "service_id": "imap_mail"}
        return None

    def get_verification_code(self, email, email_id=None, timeout=60, otp_sent_at=None):
        email_normalized = email.lower()
        
        # 确定登录身份：如果有主账号则用主账号，否则查找该邮箱匹配的密码
        login_user = self.master_email if self.master_email else email_normalized
        login_password = self.master_password if self.master_password else self.credentials_map.get(email_normalized)
        
        if not login_password:
            print(f"[IMAP] ❌ 严重错误: 未在内存中找到邮箱 {login_user} 的登录密码！")
            return None
        
        print(f"[IMAP] ✨ 准备读取邮件 (登录身份: {login_user}, 寻址目标: {email_normalized})")
        
        # 尝试遍历不同的 IMAP 服务器 (根据域名自动插队)
        servers = self.imap_servers.copy()
        if "gmail.com" in login_user:
            servers = ["imap.gmail.com"] + [s for s in servers if s != "imap.gmail.com"]
        
        for server in servers:
            try:
                # 登录 IMAP
                mail = imaplib.IMAP4_SSL(server, self.imap_port, timeout=20)
                mail.login(login_user, login_password)
                mail.select("INBOX")
                
                # 搜索逻辑：如果是主账号模式，搜索发给该特定别名的邮件；否则直接搜 noreply 即可
                if self.master_email:
                    search_criteria = f'(TO "{email_normalized}" FROM "noreply@tm.openai.com")'
                else:
                    search_criteria = '(FROM "noreply@tm.openai.com")'
                
                status, messages = mail.search(None, search_criteria)
                
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
