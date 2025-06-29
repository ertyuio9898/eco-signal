# --- database.py (Vercel 환경 지원 최종 완성 버전) ---
import sqlite3
from datetime import datetime
import pytz
import os

# --- Vercel 환경인지 확인하여 DB 경로 설정 ---
IS_VERCEL_ENV = os.environ.get('VERCEL') == '1'
DB_NAME = "/tmp/history.db" if IS_VERCEL_ENV else "history.db"

def get_db_connection():
    """데이터베이스 연결을 생성하고 반환하는 헬퍼 함수"""
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    # 딕셔너리 형태로 결과를 받기 위해 row_factory 설정
    conn.row_factory = sqlite3.Row
    return conn

def setup_database():
    """데이터베이스와 초기 테이블, 데이터를 설정합니다."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, user_name TEXT UNIQUE NOT NULL, first_seen TEXT NOT NULL)")
        cursor.execute("CREATE TABLE IF NOT EXISTS activities (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, activity_type TEXT NOT NULL, points INTEGER NOT NULL, timestamp TEXT NOT NULL, FOREIGN KEY (user_id) REFERENCES users (id))")
        cursor.execute("CREATE TABLE IF NOT EXISTS achievements (id INTEGER PRIMARY KEY, badge_name TEXT UNIQUE NOT NULL, description TEXT NOT NULL, condition_type TEXT, condition_value INTEGER)")
        cursor.execute("CREATE TABLE IF NOT EXISTS user_achievements (id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, achievement_id INTEGER NOT NULL, achieved_at TEXT NOT NULL, UNIQUE(user_id, achievement_id), FOREIGN KEY (user_id) REFERENCES users (id), FOREIGN KEY (achievement_id) REFERENCES achievements (id))")
        
        # 초기 뱃지 데이터 추가
        initial_badges = [
            ('첫걸음', '첫 환경보호 활동 인증', 'count_all', 1),
            ('텀블러 홀릭', '텀블러 사용 3회 달성', 'count_tumbler', 3),
            ('계단의 지배자', '계단 이용 3회 달성', 'count_stairs', 3),
        ]
        cursor.executemany("INSERT OR IGNORE INTO achievements (badge_name, description, condition_type, condition_value) VALUES (?, ?, ?, ?)", initial_badges)
        
        conn.commit()
        conn.close()
        print(f"✅ 데이터베이스 '{DB_NAME}' 설정 완료.")
    except Exception as e:
        print(f"🚫 데이터베이스 설정 중 오류: {e}")

def get_or_create_user(user_name):
    """사용자가 존재하면 ID를 반환하고, 없으면 새로 만들고 ID를 반환합니다."""
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM users WHERE user_name = ?", (user_name,));
    user = cursor.fetchone()
    if user:
        user_id = user['id']
    else:
        cursor.execute("INSERT INTO users (user_name, first_seen) VALUES (?, ?)", (user_name, datetime.now(pytz.timezone('Asia/Seoul')).isoformat()))
        conn.commit()
        user_id = cursor.lastrowid
        print(f"🆕 새로운 사용자 '{user_name}'님을 등록했습니다. (ID: {user_id})")
    conn.close()
    return user_id

def add_activity_log(user_id, activity_type, points):
    """사용자의 활동 내역을 DB에 기록합니다."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO activities (user_id, activity_type, points, timestamp) VALUES (?, ?, ?, ?)", (user_id, activity_type, points, datetime.now(pytz.timezone('Asia/Seoul')).isoformat()))
        conn.commit()
        conn.close()
        print(f"💾 DB 저장 완료: 사용자 ID {user_id}, {activity_type}, {points}점")
    except Exception as e:
        print(f"🚫 DB 저장 중 오류: {e}")

def check_and_award_achievements(user_id, user_name):
    """사용자의 활동을 기반으로 새로운 뱃지를 수여하는지 확인합니다."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT achievement_id FROM user_achievements WHERE user_id = ?", (user_id,));
        earned_badge_ids = {row['achievement_id'] for row in cursor.fetchall()}
        
        cursor.execute("SELECT * FROM achievements");
        all_achievements = cursor.fetchall()

        for achievement in all_achievements:
            if achievement['id'] not in earned_badge_ids:
                condition_type = achievement['condition_type']
                condition_value = achievement['condition_value']
                is_achieved = False
                
                if condition_type == 'count_all':
                    cursor.execute("SELECT COUNT(id) FROM activities WHERE user_id = ?", (user_id,));
                    count = cursor.fetchone()[0]
                    if count >= condition_value: is_achieved = True
                elif condition_type.startswith('count_'):
                    activity_name = condition_type.split('_')[1]
                    cursor.execute("SELECT COUNT(id) FROM activities WHERE user_id = ? AND activity_type = ?", (user_id, activity_name));
                    count = cursor.fetchone()[0]
                    if count >= condition_value: is_achieved = True
                
                if is_achieved:
                    cursor.execute("INSERT INTO user_achievements (user_id, achievement_id, achieved_at) VALUES (?, ?, ?)",(user_id, achievement['id'], datetime.now(pytz.timezone('Asia/Seoul')).isoformat()))
                    conn.commit()
                    print(f"🎉 뱃지 획득! '{user_name}'님이 '{achievement['badge_name']}' 뱃지를 획득했습니다!")
        conn.close()
    except Exception as e:
        print(f"🚫 도전과제 확인 중 오류: {e}")

def get_monthly_ranking(limit=10):
    """이번 달 상위 랭킹을 조회합니다."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        this_month_start = datetime.now(pytz.timezone('Asia/Seoul')).strftime('%Y-%m-01')
        cursor.execute("SELECT u.user_name, SUM(a.points) as total_points FROM activities a JOIN users u ON a.user_id = u.id WHERE a.timestamp >= ? GROUP BY u.user_name ORDER BY total_points DESC LIMIT ?", (this_month_start, limit))
        ranking_data = [dict(row) for row in cursor.fetchall()]
        for i, user in enumerate(ranking_data):
            user['rank'] = i + 1
        conn.close()
        return ranking_data
    except Exception as e:
        print(f"🚫 랭킹 조회 중 오류: {e}")
        return []

def get_user_history(user_id, limit=20):
    """특정 사용자의 최근 활동 기록을 조회합니다."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT activity_type, points, timestamp FROM activities WHERE user_id = ? ORDER BY id DESC LIMIT ?", (user_id, limit))
        history_data = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return history_data
    except Exception as e:
        print(f"🚫 사용자 활동 기록 조회 중 오류: {e}")
        return []

def get_user_achievements(user_id):
    """특정 사용자가 획득한 모든 뱃지를 조회합니다."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT ac.badge_name, ac.description, ua.achieved_at FROM user_achievements ua JOIN achievements ac ON ua.achievement_id = ac.id WHERE ua.user_id = ? ORDER BY ua.achieved_at DESC", (user_id,))
        badges_data = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return badges_data
    except Exception as e:
        print(f"🚫 사용자 뱃지 목록 조회 중 오류: {e}")
        return []

def get_recent_activities(limit=10):
    """모든 사용자의 최근 활동을 조회합니다."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT a.timestamp, u.user_name, a.activity_type, a.points FROM activities a JOIN users u ON a.user_id = u.id ORDER BY a.id DESC LIMIT ?", (limit,))
        activities = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return activities
    except Exception as e:
        print(f"🚫 최근 활동 조회 중 오류: {e}")
        return []

def get_all_users():
    """DB에 저장된 모든 사용자 목록을 가져옵니다."""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT user_name FROM users ORDER BY user_name")
        users = [row['user_name'] for row in cursor.fetchall()]
        conn.close()
        return users
    except Exception as e:
        print(f"🚫 전체 사용자 목록 조회 중 오류: {e}")
        return []