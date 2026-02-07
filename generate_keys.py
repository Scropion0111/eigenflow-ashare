#!/usr/bin/env python3
"""
生成 EigenFlow 订阅密钥
格式: EF-26Q1-XXXXXXX

使用方法：直接运行此脚本，或导入 generate_keys() 函数
"""

import random
import string
import sys

def generate_key():
    """生成一个密钥"""
    prefix = "EF-26Q1-"
    # 生成7位随机字符（大写字母+数字）
    random_part = ''.join(random.choices(string.ascii_uppercase + string.digits, k=7))
    return prefix + random_part

def generate_keys(count=50):
    """生成指定数量的密钥"""
    keys = []
    for i in range(count):
        key = generate_key()
        keys.append(key)
    return keys

if __name__ == "__main__":
    print("=" * 60)
    print("EigenFlow 订阅密钥生成器")
    print("=" * 60)
    print()
    
    # 生成50个密钥
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 50
    keys = generate_keys(count)
    
    # 输出 TOML 格式（Streamlit Cloud Secrets）
    print('【复制以下内容到 Streamlit Cloud → Settings → Secrets】')
    print()
    print('[access_keys]')
    print('keys = [')
    for key in keys:
        print(f'    "{key}",')
    print(']')
    print()
    print("=" * 60)
    print(f"已生成 {len(keys)} 个密钥")
    print()
    print("注意：")
    print("1. 复制上面的内容到 Streamlit Cloud → Settings → Secrets")
    print("2. 确保格式正确（TOML格式）")
    print("3. 不要将 keys.json 上传到 GitHub！")
