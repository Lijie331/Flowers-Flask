"""同步现有用户的nickname数据"""
import sys
sys.path.insert(0, r'D:\1B.毕业设计\Flowers-Flask')

from config import DB_CONFIG
import pymysql

conn = pymysql.connect(**DB_CONFIG)
cursor = conn.cursor()

try:
    # 将users表的username同步到user_profiles表的nickname
    cursor.execute("""
        UPDATE user_profiles p
        JOIN users u ON p.user_id = u.id
        SET p.nickname = u.username
        WHERE p.nickname IS NULL OR p.nickname = ''
    """)
    affected = cursor.rowcount
    conn.commit()
    print(f"已同步 {affected} 条 nickname 数据")
except Exception as e:
    print(f"同步失败: {e}")
    conn.rollback()

cursor.close()
conn.close()
