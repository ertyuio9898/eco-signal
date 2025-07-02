# --- server.py (SyntaxError 완벽 수정, 로컬/Vercel 완벽 지원 최종본) ---

import os
import sys
import time
import logging
import threading
import sqlite3
import configparser
from datetime import datetime
import pytz

from flask import Flask, jsonify, render_template, request
from notion_client import Client
from google.cloud import vision
import database

# --- 1. 설정 로드 (하이브리드 방식) ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
config_file_path = 'config.ini'
IS_VERCEL_ENV = os.environ.get('VERCEL') == '1'
try:
    if not IS_VERCEL_ENV and os.path.exists(config_file_path):
        logging.info(f"로컬 환경 감지. '{config_file_path}'에서 설정을 로드합니다.")
        config = configparser.ConfigParser()
        config.read(config_file_path, encoding='utf-8')
        NOTION_API_KEY = config['SECRETS']['NOTION_API_KEY']
        DATABASE_ID = config['SECRETS']['DATABASE_ID']
        ADMIN_PASSWORD = config['SECRETS']['ADMIN_PASSWORD']
        GOOGLE_CREDENTIALS_FILENAME = config['SECRETS']['GOOGLE_CREDENTIALS_FILENAME']
        IS_TEST_MODE = config['MODE'].getboolean('IS_TEST_MODE')
        if getattr(sys, 'frozen', False): application_path = os.path.dirname(sys.executable)
        else: application_path = os.path.dirname(os.path.abspath(__file__))
        credentials_path = os.path.join(application_path, GOOGLE_CREDENTIALS_FILENAME)
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
    else:
        logging.info("Vercel 환경 감지. 환경 변수에서 설정을 로드합니다.")
        NOTION_API_KEY = os.environ.get('NOTION_API_KEY')
        DATABASE_ID = os.environ.get('DATABASE_ID')
        ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')
        IS_TEST_MODE = os.environ.get('IS_TEST_MODE', 'false').lower() == 'true'
    if not all([NOTION_API_KEY, DATABASE_ID, ADMIN_PASSWORD]):
        missing_vars = [var for var in ['NOTION_API_KEY', 'DATABASE_ID', 'ADMIN_PASSWORD'] if not locals().get(var)]
        raise ValueError(f"필수 설정값이 누락되었습니다: {', '.join(missing_vars)}")
except Exception as e:
    logging.critical(f"🚫 설정 로드 중 치명적 오류 발생: {e}"); sys.exit(1)

# --- 2. 기본 설정 및 API 클라이언트 초기화 ---
CONFIG = {"point_policy": { "tumbler": 20, "cup": 20, "stairs": 30, "paper": 15, "thermos": 25 }, "level_thresholds": { "green": 150, "yellow": 120, "orange": 100 }}
CONFIG["bonus_duration_seconds"] = 60 if IS_TEST_MODE else 3600
if IS_TEST_MODE: logging.warning("### 테스트 모드로 실행 중입니다. ###")
else: logging.info("### 운영 모드로 실행 중입니다. ###")
try:
    notion = Client(auth=NOTION_API_KEY); vision_client = vision.ImageAnnotatorClient()
    logging.info("✅ 노션 및 Google Vision API 클라이언트 초기화 성공.")
except Exception as e:
    logging.error(f"🚫 API 클라이언트 초기화 실패: {e}"); notion, vision_client = None, None

# --- 3. 전역 상태 변수 및 Lock ---
SHARED_STATE = { "signal_level": "orange", "current_points": 100, "last_activity": "없음" }
state_lock = threading.Lock() 

# --- 4. 핵심 로직 함수들 ---
def analyze_image_and_apply_bonus(page):
    try:
        user_name = page["properties"]["생성자"]["created_by"]["name"]; user_id = database.get_or_create_user(user_name)
        image_url = page["properties"]["파일과 미디어"]["files"][0]["file"]["url"]
        logging.info(f"👀 '{user_name}'(ID:{user_id})님의 활동 분석 시작: {page['id']}")
        image = vision.Image(); image.source.image_uri = image_url; response = vision_client.label_detection(image=image)
        detected_tags = [label.description.lower() for label in response.label_annotations]
        applied_bonus = 0; applied_activity = "기타 활동"
        for tag, points in CONFIG["point_policy"].items():
            if tag in detected_tags and points > applied_bonus: applied_bonus = points; applied_activity = tag
        if applied_bonus > 0:
            database.add_activity_log(user_id, applied_activity, applied_bonus)
            if not IS_VERCEL_ENV:
                threading.Thread(target=database.check_and_award_achievements, args=(user_id, user_name), daemon=True).start()
            else:
                database.check_and_award_achievements(user_id, user_name)
    except Exception as e: logging.error(f"🚫 AI 분석/DB/뱃지 확인 중 오류: {e}")

def process_page(page_id, source="신규"):
    logging.info(f"📄 ({source}) 페이지 '{page_id}' 처리 시도...")
    try:
        page_data = notion.pages.retrieve(page_id=page_id)
        files_property = page_data["properties"].get("파일과 미디어", {}).get("files", [])
        if files_property and files_property[0].get("file"):
            analyze_image_and_apply_bonus(page_data); return True
        else:
            logging.warning(f"⚠️ 페이지 '{page_id}'에 아직 사진이 없습니다. 보류합니다."); return False
    except Exception as e:
        logging.error(f"🚫 페이지 '{page_id}' 처리 중 오류: {e}"); return None

def update_shared_state():
    with state_lock:
        all_activities = database.get_recent_activities(limit=100)
        current_time = time.time()
        active_bonuses = [act for act in all_activities if (current_time - datetime.fromisoformat(act['timestamp']).timestamp()) < CONFIG["bonus_duration_seconds"]]
        total_points = 100 + sum(act["points"] for act in active_bonuses)
        SHARED_STATE["current_points"] = total_points
        SHARED_STATE["last_activity"] = active_bonuses[0]["activity_type"] if active_bonuses else "없음"
        level = "orange"
        if total_points >= CONFIG["level_thresholds"]["green"]: level = "green"
        elif total_points >= CONFIG["level_thresholds"]["yellow"]: level = "yellow"
        SHARED_STATE["signal_level"] = level
    logging.info("✅ 실시간 상태 업데이트 완료.")

def check_notion_once():
    pending_pages = database.get_pending_pages()
    if pending_pages:
        logging.info(f"⏳ 보류 중인 페이지 {len(pending_pages)}개를 먼저 확인합니다.")
        for page_id in pending_pages:
            result = process_page(page_id, source="보류")
            if result is True: database.remove_from_pending(page_id); database.add_processed_page_id(page_id)
            elif result is None: database.remove_from_pending(page_id)
    logging.info("🔍 노션에서 새로운 글을 확인합니다.")
    try:
        results = notion.databases.query(database_id=DATABASE_ID, sorts=[{"property": "생성 일시", "direction": "descending"}], page_size=20).get("results")
        all_known_ids = database.get_all_processed_page_ids() | set(pending_pages)
        new_pages = [p for p in results if p["id"] not in all_known_ids]
        if not new_pages: logging.info("-> 새로운 글 없음.")
        else:
            logging.info(f"✨ {len(new_pages)}개의 새로운 글 발견!")
            for page in new_pages:
                result = process_page(page["id"], source="신규")
                if result is True: database.add_processed_page_id(page["id"])
                elif result is False: database.add_to_pending(page["id"])
    except Exception as e: logging.error(f"🚫 노션 확인 중 오류: {e}")

def background_worker():
    logging.info("⚙️ [백그라운드 직원] 근무 시작.");
    while True:
        check_notion_once()
        update_shared_state()
        time.sleep(15)

# --- 5. Flask 앱 설정 및 라우팅 ---
app = Flask(__name__)

@app.route("/status")
def get_status():
    update_shared_state()
    with state_lock:
        return jsonify(SHARED_STATE)

@app.route("/api/check-notion")
def trigger_notion_check():
    if request.args.get('password') != ADMIN_PASSWORD:
        return "<h1>🚫 접근이 거부되었습니다.</h1>", 403
    check_notion_once()
    update_shared_state()
    return f"<h1>작업 완료</h1><p>노션 확인 및 상태 업데이트가 완료되었습니다.</p>"

@app.route("/ranking")
def get_ranking():
    return jsonify(database.get_monthly_ranking())

@app.route("/user/<user_name>/history")
def get_user_history_api(user_name):
    user_id = database.get_or_create_user(user_name)
    return jsonify(database.get_user_history(user_id))

@app.route("/user/<user_name>/achievements")
def get_user_achievements_api(user_name):
    user_id = database.get_or_create_user(user_name)
    return jsonify(database.get_user_achievements(user_id))

@app.route("/users")
def get_all_users_api():
    return jsonify(database.get_all_users())

@app.route("/signal")
def signal_page():
    return render_template('signal_web.html')

@app.route("/dashboard")
def dashboard_page():
    return render_template('dashboard_web.html')

@app.route("/")
def index_page():
    return render_template('index.html')

if __name__ == '__main__':
    database.setup_database()
    if not IS_VERCEL_ENV:
        worker_thread = threading.Thread(target=background_worker, daemon=True)
        worker_thread.start()
    logging.info("🚀 로컬 테스트 서버가 시작됩니다! http://127.0.0.1:5000 에서 접속하세요.")
    app.run(host='0.0.0.0', port=5000, debug=True)