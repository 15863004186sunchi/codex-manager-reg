import imaplib
import email as email_lib
import re
import time
from datetime import datetime
from email.utils import parsedate_to_datetime

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
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            # 确定服务器列表：根据登录后缀锁定服务器，避免乱试导致的报错
            if "gmail.com" in login_user:
                current_servers = ["imap.gmail.com"]
            elif any(domain in login_user for domain in ["outlook.com", "hotmail.com", "live.com", "msn.com"]):
                current_servers = ["outlook.office365.com", "imap-mail.outlook.com"]
            else:
                # 默认尝试所有 (保持兼容性)
                current_servers = self.imap_servers

            for server in current_servers:
                try:
                    # 登录 IMAP
                    mail = imaplib.IMAP4_SSL(server, self.imap_port, timeout=20)
                    mail.login(login_user, login_password)
                    mail.select("INBOX")
                    
                    # 搜索逻辑：优先使用 TO 过滤 (Gmail 适配较好)，辅以 FROM openai.com
                    # 注意：部分 IMAP 服务器对 TO 搜索支持有限，我们本地仍保留严格过滤
                    search_criteria = f'(FROM "openai.com" TO "{email_normalized}")'
                    
                    status, messages = mail.search(None, search_criteria)
                    
                    if status != "OK" or not messages[0]:
                        # 如果 TO 搜索没结果，退而求其次只搜 FROM (兼容某些转发不规范的场景)
                        search_criteria = '(FROM "openai.com")'
                        status, messages = mail.search(None, search_criteria)
                    
                    if status == "OK" and messages[0]:
                        mail_ids = messages[0].split()
                        if mail_ids:
                            # 按照最新邮件倒序排列检查，提高命中率
                            for latest_email_id in reversed(mail_ids):
                                status, msg_data = mail.fetch(latest_email_id, '(RFC822)')
                                
                                for response_part in msg_data:
                                    if isinstance(response_part, tuple):
                                        msg = email_lib.message_from_bytes(response_part[1])
                                        
                                        # 1. 严格过滤发件人域名
                                        from_addr = str(msg.get("From", "")).lower()
                                        if "openai.com" not in from_addr:
                                            continue
                                        
                                        # 2. 匹配收件人 (支持 Catch-all 场景)
                                        # 使用正则实现更精准的匹配，防止子串包含 (如 a@x.com 匹配到 ba@x.com)
                                        to_addr_raw = str(msg.get("To", "")).lower()
                                        delivered_to = str(msg.get("Delivered-To", "")).lower()
                                        
                                        # 预编译正则，匹配全词邮箱
                                        email_pattern = rf"\b{re.escape(email_normalized)}\b"
                                        
                                        is_match = False
                                        if re.search(email_pattern, to_addr_raw):
                                            is_match = True
                                        elif re.search(email_pattern, delivered_to):
                                            is_match = True
                                        
                                        if not is_match:
                                            continue
                                        
                                        # 3. 时间过滤：确保是本轮发送的新邮件 (允许 1 分钟左右的宽限，防止服务器时钟不准)
                                        if otp_sent_at:
                                            date_str = str(msg.get("Date", ""))
                                            try:
                                                msg_date = parsedate_to_datetime(date_str)
                                                msg_ts = msg_date.timestamp()
                                                
                                                # 如果邮件时间早于 otp_sent_at 之前 10 秒，则认为是旧邮件 (收紧 grace period)
                                                if msg_ts < (otp_sent_at - 10):
                                                    print(f"[IMAP] ⏳ 丢弃旧邮件 (Sent at {msg_date}, Requested at {datetime.fromtimestamp(otp_sent_at)})")
                                                    continue
                                            except Exception as e:
                                                print(f"[IMAP] ⚠️ 无法解析邮件日期: {date_str}, 错误: {e}")
                                                # 如果解析失败，保守起见继续流程
                                                pass
                                    
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
                except imaplib.IMAP4.error as e:
                    # 如果登录失败，通常是账号/密码/IP问题，记录日志但继续轮询
                    print(f"[IMAP] ⚠️  {server} 检查暂无结果: {e}")
                except Exception as e:
                    print(f"[IMAP] 💀 {server} 连接异常: {e}")
            
            # 如果这一轮没搜到，休息 5 秒再来
            time.sleep(5)
            
        print(f"[IMAP] ❌ 在 {timeout} 秒内未从预设服务器获取到 {email_normalized} 的验证码。")
        return None
