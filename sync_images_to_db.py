"""
自动同步花卉图片到数据库 flowers_2 表
当修改 ChineseFlowers120 文件夹下的图片时，运行此脚本更新数据库的 image_url
"""
import os
import json
import pymysql

# 配置
DATASET_PATH = r"D:\1B.毕业设计\数据集\origin_102"
DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '314331',
    'database': 'tlj',
    'charset': 'utf8mb4'
}

def get_all_folders():
    """获取所有花卉文件夹"""
    folders = []
    if os.path.exists(DATASET_PATH):
        for name in os.listdir(DATASET_PATH):
            folder_path = os.path.join(DATASET_PATH, name)
            if os.path.isdir(folder_path):
                # 获取该文件夹下的所有图片
                images = []
                for f in os.listdir(folder_path):
                    if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.webp')):
                        images.append({
                            'filename': f,
                            'relative_path': f"{name}/{f}"
                        })
                if images:
                    folders.append({
                        'folder_name': name,
                        'count': len(images),
                        'images': images
                    })
    return folders

def update_database():
    """更新数据库中的 image_url"""
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    folders = get_all_folders()
    updated = 0
    not_found = []
    
    for folder in folders:
        folder_name = folder['folder_name']
        image_data = json.dumps({
            'count': folder['count'],
            'images': folder['images']
        }, ensure_ascii=False)
        
        # 根据文件夹名(中文名)更新数据库
        cursor.execute("""
            UPDATE flowers
            SET image_url = %s
            WHERE chinese_name = %s
        """, (image_data, folder_name))
        
        if cursor.rowcount > 0:
            updated += 1
            print(f"✅ 更新成功: {folder_name} ({folder['count']}张图片)")
        else:
            not_found.append(folder_name)
    
    conn.commit()
    cursor.close()
    conn.close()
    
    print(f"\n更新完成: 成功 {updated} 个, 未找到匹配 {len(not_found)} 个")
    if not_found:
        print(f"未找到匹配的文件夹: {not_found}")

if __name__ == '__main__':
    print("=" * 50)
    print("开始同步花卉图片到数据库...")
    print("=" * 50)
    update_database()
    print("=" * 50)
    print("同步完成!")