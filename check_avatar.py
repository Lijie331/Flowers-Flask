"""检查用户头像数据"""
import sys
sys.path.insert(0, r'D:\1B.毕业设计\Flowers-Flask')

from config import DB_CONFIG
import pymysql

conn = pymysql.connect(**DB_CONFIG)
cursor = conn.cursor()

print("=== 检查 user_profiles 表的 avatar_url ===")
cursor.execute("SELECT user_id, nickname, avatar_url FROM user_profiles LIMIT 5")
for row in cursor.fetchall():
    print(f"user_id: {row[0]}, nickname: {row[1]}, avatar_url: {row[2]}")

print("\n=== 检查 posts 表的 user_avatar ===")
cursor.execute("SELECT id, user_id, username, user_avatar FROM posts LIMIT 5")
for row in cursor.fetchall():
    print(f"post_id: {row[0]}, user_id: {row[1]}, username: {row[2]}, user_avatar: {row[3]}")

cursor.close()
conn.close()
