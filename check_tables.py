"""检查数据库表结构"""
import sys
sys.path.insert(0, r'D:\1B.毕业设计\Flowers-Flask')

from config import DB_CONFIG
import pymysql

conn = pymysql.connect(**DB_CONFIG)
cursor = conn.cursor()

print("=== user_profiles 表结构 ===")
cursor.execute("DESCRIBE user_profiles")
for row in cursor.fetchall():
    print(row)

print("\n=== users 表结构 ===")
cursor.execute("DESCRIBE users")
for row in cursor.fetchall():
    print(row)

print("\n=== 触发器列表 ===")
cursor.execute("SHOW TRIGGERS LIKE 'users'")
for row in cursor.fetchall():
    print(row)

cursor.close()
conn.close()
