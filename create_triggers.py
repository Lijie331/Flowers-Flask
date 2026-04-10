"""
创建数据库触发器，使 username 和 nickname 保持同步
"""

import pymysql

DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': 'root',
    'password': '314331',
    'database': 'tlj',
    'charset': 'utf8mb4'
}

def create_triggers():
    conn = pymysql.connect(**DB_CONFIG)
    cursor = conn.cursor()

    try:
        # 1. 删除已存在的触发器（防止重复创建）
        cursor.execute("DROP TRIGGER IF EXISTS `sync_username_to_nickname`")
        cursor.execute("DROP TRIGGER IF EXISTS `sync_nickname_to_username`")
        print("[OK] 已删除旧的触发器")

        # 2. 创建触发器：更新 users.username 时同步 user_profiles.nickname
        cursor.execute("""
            CREATE TRIGGER `sync_username_to_nickname`
            AFTER UPDATE ON `users`
            FOR EACH ROW
            BEGIN
                IF OLD.username != NEW.username THEN
                    UPDATE user_profiles SET nickname = NEW.username WHERE user_id = NEW.id;
                END IF;
            END
        """)
        print("[OK] 创建触发器 sync_username_to_nickname 成功")

        # 3. 创建触发器：更新 user_profiles.nickname 时同步 users.username
        cursor.execute("""
            CREATE TRIGGER `sync_nickname_to_username`
            AFTER UPDATE ON `user_profiles`
            FOR EACH ROW
            BEGIN
                IF OLD.nickname != NEW.nickname THEN
                    UPDATE users SET username = NEW.nickname WHERE id = NEW.user_id;
                END IF;
            END
        """)
        print("[OK] 创建触发器 sync_nickname_to_username 成功")

        conn.commit()

        # 4. 初始化现有数据
        cursor.execute("""
            UPDATE user_profiles p SET nickname = (
                SELECT username FROM users u WHERE u.id = p.user_id
            )
        """)
        print("[OK] 同步现有数据成功")

        conn.commit()
        print("\n[SUCCESS] 所有触发器创建成功！")

    except Exception as e:
        print(f"[ERROR] 错误: {e}")
        conn.rollback()
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    create_triggers()
