"""删除触发器脚本"""
import sys
sys.path.insert(0, r'D:\1B.毕业设计\Flowers-Flask')

from config import DB_CONFIG
import pymysql

conn = pymysql.connect(**DB_CONFIG)
cursor = conn.cursor()

try:
    cursor.execute("DROP TRIGGER IF EXISTS sync_username_to_nickname")
    cursor.execute("DROP TRIGGER IF EXISTS sync_nickname_to_username")
    conn.commit()
    print("触发器已删除")
except Exception as e:
    print(f"删除失败: {e}")
    conn.rollback()

cursor.close()
conn.close()
