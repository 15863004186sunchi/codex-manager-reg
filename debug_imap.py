import imaplib
import email as email_lib
import time
import sys

def debug_imap(user, password, target_domain):
    try:
        mail = imaplib.IMAP4_SSL("imap.gmail.com", 993)
        mail.login(user, password)
        mail.select("INBOX")
        
        print(f"Checking for OpenAI emails in {user}...")
        status, messages = mail.search(None, '(FROM "openai.com")')
        
        if status == "OK" and messages[0]:
            mail_ids = messages[0].split()
            print(f"Found {len(mail_ids)} OpenAI emails. Inspecting the last 5...")
            for mid in reversed(mail_ids[-5:]):
                status, data = mail.fetch(mid, '(RFC822)')
                msg = email_lib.message_from_bytes(data[0][1])
                print("-" * 40)
                print(f"ID: {mid.decode()}")
                print(f"Date: {msg.get('Date')}")
                print(f"From: {msg.get('From')}")
                print(f"To: {msg.get('To')}")
                print(f"Delivered-To: {msg.get('Delivered-To')}")
                print(f"X-Forwarded-To: {msg.get('X-Forwarded-To')}")
                print(f"Subject: {msg.get('Subject')}")
        
        mail.logout()
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    # 使用用户提供的凭据
    debug_imap("geeksunchi@gmail.com", "jcfk oprb igpm wbwh", "flapysun.com")
