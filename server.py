# --- server.py (최종 완성 버전: 로컬/Vercel 모두 지원, 모든 함수 포함) ---

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

# --- 1. 설정 로드 (하이브리드 방식: 로컬의 config.ini 또는 Vercel의 환경 변수) ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
config_file_path = 'config.ini'
IS_VERCEL_ENV = os.environ.get('VERCEL') == '1' # Vercel에서 자동으로 설정되는 환경 변수

try:
    if not IS_VERCEL_ENV and os.path.exists(config_file_path):
        # 로컬 환경: config.ini 파일에서 설정 로드
        logging.info(f"로컬 환경 감지. '{config_file_path}'에서 설정을 로드합니다.")
        config = configparser.ConfigParser()
        config.read(config_file_path, encoding='utf-8')
        
        NOTION_API_KEY = config['SECRETS']['NOTION_API_KEY']
        DATABASE_ID = config['SECRETS']['DATABASE_ID']
        ADMIN_PASSWORD = config['SECRETS']['ADMIN_PASSWORD']
        GOOGLE_CREDENTIALS_FILENAME = config['SECRETS']['GOOGLE_CREDENTIALS_FILENAME']
        IS_TEST_MODE = config['MODE'].getboolean('IS_TEST_MODE')
        
        # 로컬에서는 구글 인증서 파일 경로를 직접 환경 변수에 설정
        # Vercel에서는 GOOGLE_APPLICATION_CREDENTIALS 환경 변수 자체를 구글 라이브러리가 직접 사용합니다.
        if getattr(sys, 'frozen', False): application_path = os.path.dirname(sys.executable)
        else: application_path = os.path.dirname(os.path.abspath(__file__))
        credentials_path = os.path.join(application_path, GOOGLE_CREDENTIALS_FILENAME)
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path

    else:
        # Vercel 환경: 환경 변수에서 설정 로드
        logging.info("Vercel 환경 감지. 환경 변수에서 설정을 로드합니다.")
        NOTION_API_KEY = os.environ.get('NOTION_API_KEY')
        DATABASE_ID = os.environ.get('DATABASE_ID')
        ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')
        IS_TEST_MODE = os.environ.get('IS_TEST_MODE', 'false').lower() == 'true'
        
    if not all([NOTION_API_KEY, DATABASE_ID, ADMIN_PASSWORD]):
        missing_vars = [var for var in ['NOTION_API_KEY', 'DATABASE_ID', 'ADMIN_PASSWORD'] if not locals().get(var)]
        raise ValueError(f"필수 설정값이 누락되었습니다: {', '.join(missing_vars)}")

except Exception as e:
    logging.critical(f"🚫 설정 로드 중 치명적 오류 발생: {e}")
    sys.exit(1)


# --- 2. 기본 설정 및 API 클라이언트 초기화 ---
CONFIG = {"check_interval_seconds": 10, "pending_check_interval_seconds": 15, "pending_timeout_seconds": 300, "point_policy": { "tumbler": 20, "cup": 20, "stairs": 30, "paper": 15, "thermos": 25 }, "level_thresholds": { "green": 150, "yellow": 120, "orange": 100 }}
CONFIG["bonus_duration_seconds"] = 60 if IS_TEST_MODE else 3600
if IS_TEST_MODE: logging.warning("### 테스트 모드로 실행 중입니다. ###")
else: logging.info("### 운영 모드로 실행 중입니다. ###")

try:
    notion = Client(auth=NOTION_API_KEY)
    vision_client = vision.ImageAnnotatorClient()
    logging.info("✅ 노션 및 Google Vision API 클라이언트 초기화 성공.")
except Exception as e:
    logging.error(f"🚫 API 클라이언트 초기화 실패: {e}")
    notion, vision_client = None, None # 실패 시 클라이언트 None으로 설정하여 계속 진행


# --- 3. 백그라운드 작업자들 & 전역 상태 ---
SHARED_STATE = { "signal_level": "orange", "current_points": 100, "last_activity": "없음", "active_activities": [] }
PENDING_ANALYSIS_QUEUE = {}; PROCESSED_PAGE_IDS = set(); state_lock = threading.Lock()

def analyze_image_and_apply_bonus(page):
    try:
        user_name = page["properties"]["생성자"]["created_by"]["name"]; user_id = database.get_or_create_user(user_name)
        image_url = page["properties"]["파일과 미디어"]["files"][0]["file"]["url"]
        logging.info(f"👀 '{user_name}'(ID:{user_id})님의 활동 분석 시작: {page['id']}")
        
        # Google Vision API 클라이언트가 초기화되었는지 확인
        if vision_client is None:
            logging.error("Google Vision 클라이언트가 초기화되지 않아 이미지 분석을 건너뜀.")
            return

        image = vision.Image(); image.source.image_uri = image_url; response = vision_client.label_detection(image=image)
        detected_tags = [label.description.lower() for label in response.label_annotations]
        applied_bonus = 0; applied_activity = "기타 활동"
        for tag, points in CONFIG["point_policy"].items():
            if tag in detected_tags and points > applied_bonus:
                applied_bonus = points; applied_activity = tag
        if applied_bonus > 0:
            with state_lock:
                SHARED_STATE["active_activities"].append({"activity": applied_activity, "points": applied_bonus, "end_time": time.time() + CONFIG["bonus_duration_seconds"]})
            logging.info(f"🎯 활동 '{applied_activity}' 추가! (+{applied_bonus}점)")
            database.add_activity_log(user_id, applied_activity, applied_bonus)
            threading.Thread(target=database.check_and_award_achievements, args=(user_id, user_name), daemon=True).start()
    except Exception as e: logging.error(f"🚫 AI 분석/DB/뱃지 확인 중 오류: {e}")

# SHARED_STATE를 주기적으로 업데이트하는 스레드 (로컬에서만 실행)
def state_updater_worker():
    logging.info("⚙️ [상태 업데이트 직원] 근무 시작.")
    while True:
        try:
            with state_lock:
                SHARED_STATE["active_activities"][:] = [act for act in SHARED_STATE["active_activities"] if act["end_time"] >= time.time()]
                total_points = 100 + sum(act["points"] for act in SHARED_STATE["active_activities"])
                SHARED_STATE["current_points"] = total_points
                SHARED_STATE["last_activity"] = SHARED_STATE["active_activities"][-1]["activity"] if SHARED_STATE["active_activities"] else "없음"
                level = "orange"
                if total_points >= CONFIG["level_thresholds"]["green"]: level = "green"
                elif total_points >= CONFIG["level_thresholds"]["yellow"]: level = "yellow"
                SHARED_STATE["signal_level"] = level
        except Exception as e: logging.error(f"🚫 상태 업데이트 중 심각한 오류: {e}")
        time.sleep(1)

# Notion을 주기적으로 감시하는 스레드 (로컬에서만 실행)
def notion_checker_worker():
    logging.info("⚙️ [노션 감시 직원] 근무 시작. (Vercel에서는 동작 제한됨)")
    try:
        if notion is None:
            logging.error("Notion 클라이언트가 초기화되지 않아 노션 감시 작업을 시작할 수 없습니다.")
            return # 함수 종료
        initial_pages = notion.databases.query(database_id=DATABASE_ID, sorts=[{"property": "생성 일시", "direction": "descending"}], page_size=100).get("results")
        with state_lock:
            for page in initial_pages: PROCESSED_PAGE_IDS.add(page["id"])
        logging.info(f"✅ 초기 글 {len(initial_pages)}개 학습 완료.")
    except Exception as e: logging.error(f"🚫 초기 글 학습 중 오류 발생: {e}")
    while True:
        try:
            if notion is None: time.sleep(CONFIG["check_interval_seconds"]); continue
            results = notion.databases.query(database_id=DATABASE_ID, sorts=[{"property": "생성 일시", "direction": "descending"}], page_size=20).get("results")
            with state_lock:
                new_pages = [p for p in results if p["id"] not in PROCESSED_PAGE_IDS and p["id"] not in PENDING_ANALYSIS_QUEUE]
            if new_pages:
                logging.info(f"✨ {len(new_pages)}개의 새로운 글 발견! 분석 대기열에 추가합니다.")
                with state_lock:
                    for page in new_pages: PENDING_ANALYSIS_QUEUE[page["id"]] = time.time()
        except Exception as e: logging.error(f"🚫 노션 확인 중 오류: {e}")
        time.sleep(CONFIG["check_interval_seconds"])

# 보류 중인 분석 큐를 처리하는 스레드 (로컬에서만 실행)
def pending_processor_worker():
    logging.info("⚙️ [AI 분석 전문가] 근무 시작. (Vercel에서는 동작 제한됨)")
    while True:
        page_id_to_process = None
        with state_lock:
            if PENDING_ANALYSIS_QUEUE: page_id_to_process = next(iter(PENDING_ANALYSIS_QUEUE))
        if page_id_to_process:
            try:
                if notion is None or vision_client is None:
                    logging.error("Notion 또는 Vision 클라이언트가 초기화되지 않아 AI 분석을 시작할 수 없습니다.")
                    with state_lock: PENDING_ANALYSIS_QUEUE.pop(page_id_to_process, None) # 큐에서 제거하여 무한 루프 방지
                    time.sleep(CONFIG["pending_check_interval_seconds"]); continue
                    
                page_data = notion.pages.retrieve(page_id=page_id_to_process)
                files_property = page_data["properties"].get("파일과 미디어", {}).get("files", [])
                if files_property and files_property[0].get("file"):
                    with state_lock: PENDING_ANALYSIS_QUEUE.pop(page_id_to_process, None); PROCESSED_PAGE_IDS.add(page_id_to_process)
                    threading.Thread(target=analyze_image_and_apply_bonus, args=(page_data,)).start()
                else:
                    with state_lock:
                        if time.time() - PENDING_ANALYSIS_QUEUE.get(page_id_to_process, 0) > CONFIG["pending_timeout_seconds"]:
                            logging.warning(f"⚠️ 페이지 '{page_id_to_process}' 처리 시간 초과. 대기열에서 제거합니다.")
                            PENDING_ANALYSIS_QUEUE.pop(page_id_to_process, None); PROCESSED_PAGE_IDS.add(page_id_to_process)
            except Exception as e:
                logging.error(f"🚫 대기열 처리 중 오류: {e}"); 
                with state_lock: PENDING_ANALYSIS_QUEUE.pop(page_id_to_process, None)
        time.sleep(CONFIG["pending_check_interval_seconds"])

# SHARED_STATE를 API 요청 시에만 업데이트하는 함수 (Vercel에서 실시간 반영을 위해 사용)
def update_shared_state_on_request():
    """API 요청 시 SHARED_STATE를 즉시 업데이트합니다."""
    with state_lock:
        # 만료된 활동 제거
        SHARED_STATE["active_activities"][:] = [act for act in SHARED_STATE["active_activities"] if act["end_time"] >= time.time()]
        
        # 현재 점수 계산
        total_points = 100 + sum(act["points"] for act in SHARED_STATE["active_activities"])
        SHARED_STATE["current_points"] = total_points
        
        # 마지막 활동 업데이트 (가장 최근 활동이 없으면 '없음'으로 표시)
        SHARED_STATE["last_activity"] = SHARED_STATE["active_activities"][-1]["activity"] if SHARED_STATE["active_activities"] else "없음"
        
        # 신호등 레벨 업데이트
        level = "orange"
        if total_points >= CONFIG["level_thresholds"]["green"]: level = "green"
        elif total_points >= CONFIG["level_thresholds"]["yellow"]: level = "yellow"
        SHARED_STATE["signal_level"] = level


# --- 4. Flask 앱 설정 및 라우팅 ---
app = Flask(__name__)

# --- API 엔드포인트 ---
@app.route("/status")
def get_status():
    # Vercel 환경에서는 요청이 올 때마다 SHARED_STATE를 업데이트합니다.
    # 이렇게 해야 신호등과 점수가 실시간으로 반영됩니다.
    update_shared_state_on_request()
    with state_lock:
        return jsonify(SHARED_STATE)

@app.route("/ranking")
def get_ranking(): return jsonify(database.get_monthly_ranking())
@app.route("/user/<user_name>/history")
def get_user_history_api(user_name): user_id = database.get_or_create_user(user_name); return jsonify(database.get_user_history(user_id))
@app.route("/user/<user_name>/achievements")
def get_user_achievements_api(user_name): user_id = database.get_or_create_user(user_name); return jsonify(database.get_user_achievements(user_id))
@app.route("/users")
def get_all_users_api(): return jsonify(database.get_all_users())
@app.route("/admin")
def admin_dashboard():
    if request.args.get('password') != ADMIN_PASSWORD: return "<h1>🚫 접근이 거부되었습니다.</h1>", 403
    with state_lock: current_status = SHARED_STATE.copy()
    # admin.html 템플릿이 없으므로, 간단한 텍스트로 대체 (선배님이 나중에 admin.html 만드시면 render_template 사용)
    return f"Admin Page. Status: {current_status}. DB Path: {database.DB_NAME}"
@app.route("/signal")
def signal_page(): return render_template('signal_web.html')
@app.route("/dashboard")
def dashboard_page(): return render_template('dashboard_web.html')
@app.route("/")
def index_page(): return render_template('index.html')


# --- 5. 서버 실행 ---
# 이 부분은 로컬에서 'python server.py'를 실행했을 때만 동작합니다.
# Vercel 환경에서는 Vercel이 'app' 객체를 찾아서 직접 실행하므로 이 블록은 건너뛰어집니다.
if __name__ == '__main__':
    database.setup_database()
    
    # 로컬 테스트 시에만 백그라운드 스레드를 실행합니다.
    if not IS_VERCEL_ENV:
        threading.Thread(target=state_updater_worker, daemon=True, name="StateUpdater").start()
        threading.Thread(target=notion_checker_worker, daemon=True, name="NotionChecker").start()
        threading.Thread(target=pending_processor_worker, daemon=True, name="PendingProcessor").start()
        
    logging.info("🚀 로컬 테스트 서버가 시작됩니다! http://127.0.0.1:5000 에서 접속하세요.")
    app.run(host='0.0.0.0', port=5000, debug=True)