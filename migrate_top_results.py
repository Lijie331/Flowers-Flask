"""迁移 identify_history 表的 top_results 字段为 MEDIUMTEXT"""
import pymysql
from config import DB_CONFIG

conn = pymysql.connect(**DB_CONFIG)
cursor = conn.cursor()

# 检查当前类型
cursor.execute("SHOW COLUMNS FROM identify_history WHERE Field = 'top_results'")
result = cursor.fetchone()
print(f"当前 top_results 字段: {result}")

# 修改为 MEDIUMTEXT (16MB)
cursor.execute("ALTER TABLE identify_history MODIFY COLUMN top_results MEDIUMTEXT")
conn.commit()

# 验证
cursor.execute("SHOW COLUMNS FROM identify_history WHERE Field = 'top_results'")
result = cursor.fetchone()
print(f"修改后 top_results 字段: {result}")

cursor.close()
conn.close()
print("迁移完成")
