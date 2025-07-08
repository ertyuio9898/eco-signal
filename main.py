# --- main.py (최종 완성 버전) ---

import os
import requests
from flask import Flask, request, render_template, jsonify
import sqlite3
from datetime import datetime
import pytz

# --- 1. 설정 및 DB 연결 ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'eco_tags.db')
print(f"📍 DB 경로: {DB_PATH}")

def get_db_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

try:
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tag_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT, user_name TEXT, tag TEXT,
                co2_saved INTEGER, photo_file_id TEXT, timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.commit()
    print("✅ DB 연결 및 테이블 설정 완료.")
except sqlite3.Error as e:
    print(f"❌ DB 연결 또는 테이블 생성 오류: {e}")

BOT_TOKEN = '7785257974:AAEm8sz9T5exugy_V4s55Ue8cGkgNsTf-EQ' # 선배님 실제 토큰으로 교체
TELEGRAM_API_URL = f"https://api.telegram.org/bot{BOT_TOKEN}/"
app = Flask(__name__)

# --- 2. 텔레그램 웹훅 처리 ---
@app.route('/webhook', methods=['POST'])
def webhook():
    # 이 부분은 선배님 동료분의 웹훅 코드를 그대로 사용해주세요
    # (내용은 생략, 선배님 코드와 동일)
    return 'OK'

# --- 3. 히스토리 페이지 & 필터링 로직 ---
@app.route('/history')
def history():
    selected_user = request.args.get('user')
    selected_year = request.args.get('year')
    selected_month = request.args.get('month')
    selected_day = request.args.get('day')

    conn = get_db_connection()
    query = "SELECT * FROM tag_logs WHERE tag IS NOT NULL"
    params = []
    if selected_user: query += " AND user_name = ?"; params.append(selected_user)
    if selected_year: query += " AND strftime('%Y', timestamp) = ?"; params.append(selected_year)
    if selected_month: query += " AND strftime('%m', timestamp) = ?"; params.append(selected_month.zfill(2))
    if selected_day: query += " AND strftime('%d', timestamp) = ?"; params.append(selected_day.zfill(2))
    query += " ORDER BY timestamp DESC"
    
    rows = conn.execute(query, tuple(params)).fetchall()
    
    logs = []
    for row in rows:
        log_item = dict(row)
        photo_file_id = log_item.get('photo_file_id')
        photo_url = None
        if photo_file_id:
            try:
                r = requests.get(f"{TELEGRAM_API_URL}getFile", params={"file_id": photo_file_id})
                if r.status_code == 200:
                    file_path = r.json().get("result", {}).get("file_path")
                    if file_path:
                        photo_url = f"https://api.telegram.org/file/bot{BOT_TOKEN}/{file_path}"
            except Exception as e:
                print(f"텔레그램 사진 URL 가져오기 실패: {e}")
        log_item['photo_url'] = photo_url
        logs.append(log_item)

    years = [r['year'] for r in conn.execute("SELECT DISTINCT strftime('%Y', timestamp) as year FROM tag_logs ORDER BY year DESC")]
    months = [r['month'] for r in conn.execute("SELECT DISTINCT strftime('%m', timestamp) as month FROM tag_logs ORDER BY month ASC")]
    days = [r['day'] for r in conn.execute("SELECT DISTINCT strftime('%d', timestamp) as day FROM tag_logs ORDER BY day ASC")]
    user_ids = [r['user_name'] for r in conn.execute("SELECT DISTINCT user_name FROM tag_logs WHERE user_name IS NOT NULL ORDER BY user_name")]
    
    conn.close()

    # 템플릿 파일 이름을 최종본인 history_final.html로 사용합니다.
    return render_template("history_final.html", 
                           logs=logs, user_ids=user_ids, 
                           available_years=years, available_months=months, available_days=days,
                           selected_user=selected_user, selected_year=selected_year, 
                           selected_month=selected_month, selected_day=selected_day)

@app.route('/')
def index():
    return history()

if __name__ == '__main__':
    print("🚀 로컬 테스트 서버가 시작됩니다! http://127.0.0.1:5001 에서 접속하세요.")
    app.run(host='0.0.0.0', port=5001, debug=True)