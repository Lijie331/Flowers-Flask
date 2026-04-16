"""
将 flowers_data_102.json 完全覆盖 tlj.flowers 表
"""
import json
import pymysql

# 配置
DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '314331',
    'database': 'tlj',
    'charset': 'utf8mb4'
}

JSON_FILE = r"D:\1B.毕业设计\数据集\flowers_data_102.json"

def main():
    # 读取 JSON 文件
    print(f"读取 JSON 文件: {JSON_FILE}")
    with open(JSON_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    flowers = data.get('flowers', [])
    print(f"共 {len(flowers)} 条记录")
    
    # 连接数据库
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    # 1. 清空 flowers 表
    print("清空 flowers 表...")
    cursor.execute("TRUNCATE TABLE flowers")
    conn.commit()
    print("flowers 表已清空")
    
    # 2. 插入新数据（使用 flowers_2 表的字段结构）
    print("插入新数据...")
    
    insert_sql = """
        INSERT INTO flowers (
            id, chinese_name, latin_name, 
            family, genus, morphology, habitat, growth_habit,
            ornamental_value, care_methods, flower_language,
            category_id, image_url, data_source, collected_date
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
    """
    
    count = 0
    for flower in flowers:
        values = (
            flower.get('id'),
            flower.get('chinese_name', ''),
            flower.get('latin_name', ''),
            flower.get('family', ''),
            flower.get('genus', ''),
            flower.get('morphology', ''),
            flower.get('habitat', ''),
            flower.get('growth_habit', ''),
            flower.get('ornamental_value', ''),
            flower.get('care_methods', ''),
            flower.get('flower_language', ''),
            flower.get('category_id'),
            # flower.get('image_url', ''),
            flower.get('data_source', ''),
            flower.get('collected_date', '')
        )
        cursor.execute(insert_sql, values)
        count += 1
    
    conn.commit()
    cursor.close()
    conn.close()
    
    print(f"✅ 插入完成! 共 {count} 条记录")

if __name__ == '__main__':
    main()