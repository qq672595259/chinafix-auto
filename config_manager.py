import json
import os
from cryptography.fernet import Fernet
import base64
import requests

# 配置文件路径(与脚本同目录)
CONFIG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")
KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".key")

# 论坛基础URL
BASE_URL = "https://www.chinafix.com"


def get_or_create_key():
    """获取或创建加密密钥"""
    if os.path.exists(KEY_FILE):
        with open(KEY_FILE, "rb") as f:
            return f.read()
    else:
        key = Fernet.generate_key()
        with open(KEY_FILE, "wb") as f:
            f.write(key)
        # 设置文件隐藏属性（Windows）
        try:
            import subprocess
            subprocess.run(["attrib", "+h", KEY_FILE], check=False, capture_output=True)
        except:
            pass
        return key


def encrypt_password(password):
    """加密密码"""
    key = get_or_create_key()
    f = Fernet(key)
    encrypted = f.encrypt(password.encode())
    return base64.urlsafe_b64encode(encrypted).decode()


def decrypt_password(encrypted_password):
    """解密密码"""
    key = get_or_create_key()
    f = Fernet(key)
    encrypted = base64.urlsafe_b64decode(encrypted_password.encode())
    return f.decrypt(encrypted).decode()


def verify_credentials(username, password):
    """验证账户密码是否正确 - 简化版,不做实际验证,交给主脚本验证"""
    # 由于登录需要验证码,这里不做实际验证
    # 验证工作交给 script.py 的主流程
    print(f"\n[提示] 账户密码将在运行时验证")
    return True


def load_credentials():
    """加载保存的账户密码"""
    if not os.path.exists(CONFIG_FILE):
        return None, None
    
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
            encrypted_username = config.get("username")
            encrypted_password = config.get("password")
            
            if encrypted_username and encrypted_password:
                # 解密用户名和密码
                username = decrypt_password(encrypted_username)
                password = decrypt_password(encrypted_password)
                return username, password
            return None, None
    except Exception as e:
        print(f"[配置] 读取配置文件失败: {e}")
        return None, None


def save_credentials(username, password):
    """保存账户密码到配置文件(全部加密存储)"""
    # 加密用户名和密码
    encrypted_username = encrypt_password(username)
    encrypted_password = encrypt_password(password)
    
    config = {
        "username": encrypted_username,
        "password": encrypted_password
    }
    
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f"[配置] ✅ 账户信息已全部加密保存到: {CONFIG_FILE}")
        return True
    except Exception as e:
        print(f"[配置] ❌ 保存配置文件失败: {e}")
        return False


def get_credentials():
    """获取账户密码,如果没有保存则提示用户输入"""
    username, password = load_credentials()
    
    if username and password:
        print(f"[配置] ✅ 已加载保存的账户信息")
        return username, password
    
    # 首次使用,提示输入
    print("=" * 50)
    print("  首次使用,请输入账户信息")
    print("=" * 50)
    
    while True:
        username = input("\n请输入用户名: ").strip()
        if not username:
            print("❌ 用户名不能为空")
            continue
        
        password = input("请输入密码: ").strip()
        if not password:
            print("❌ 密码不能为空")
            continue
        
        # 验证账户密码是否正确
        if verify_credentials(username, password):
            # 验证成功,询问是否保存
            save_choice = input("\n是否保存账户密码以便下次自动登录?(y/n,默认y): ").strip().lower()
            if save_choice in ["y", "yes", ""]:
                if save_credentials(username, password):
                    print("[配置] ✅ 账户信息已保存,下次将自动登录")
            else:
                print("[配置] 账户信息未保存,每次运行需手动输入")
            
            return username, password
        else:
            # 验证失败,要求重新输入
            print("\n请重新输入正确的账户密码...\n")
            continue


def clear_credentials():
    """清除已保存的账户密码"""
    if os.path.exists(CONFIG_FILE):
        try:
            os.remove(CONFIG_FILE)
            print(f"[配置] ✅ 已清除保存的账户信息")
            return True
        except Exception as e:
            print(f"[配置] ❌ 清除配置文件失败: {e}")
            return False
    else:
        print(f"[配置] 未找到已保存的账户信息")
        return True
