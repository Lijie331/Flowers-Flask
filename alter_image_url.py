# -*- coding: utf-8 -*-
import pymysql

conn = pymysql.connect(host='localhost', port=3306, user='root', password='314331', database='tlj', charset='utf8mb4')
cursor = conn.cursor()

# 将 image_url 字段从 varchar(500) 改为 TEXT
try:
    cursor.execute('ALTER TABLE identify_history MODIFY COLUMN image_url TEXT')
    conn.commit()
    print('[SUCCESS] image_url 字段已修改为 TEXT 类型')
except Exception as e:
    print(f'[ERROR] 修改失败: {e}')
finally:
    cursor.close()
    conn.close()