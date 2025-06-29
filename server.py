
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
import database # database.py 모듈 임포트

# --- 0. 환경 변수 감지 (가장 먼저 정의되어야 함) ---
# 이 변수는 어떤 함수나 블록 안이 아닌, 파일의 최상단에 정의되어야 합니다.
IS_VERCEL_ENV = os.environ.get('VERCEL') == '1' 


# --- 1. 설정 로드 (하이브리드 방식: 로컬의 config.ini 또는 Vercel의 환경 변수) ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
config_file_path = 'config.ini'

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
        
        # 로컬에서는 구글 인증서 파일 경로를 직접 환경 변수에 설정 (Google Cloud Vision API가 필요로 함)
        if getattr(sys, 'frozen', False): application_path = os.path.dirname(sys.executable)
        else: application_path = os.path.dirname(os.path.abspath(__file__))
        credentials_path = os.path.join(application_path, GOOGLE_CREDENTIALS_FILENAME)
        os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path

    else:
        # Vercel 환경: 환경 변수에서 설정 로드 (Vercel에 이미 설정되어 있어야 함)
        logging.info("Vercel 환경 감지. 환경 변수에서 설정을 로드합니다.")
        NOTION_API_KEY = os.environ.get('NOTION_API_KEY')
        DATABASE_ID = os.environ.get('DATABASE_ID')
        ADMIN_PASSWORD = os.environ.get('ADMIN_PASSWORD')
        IS_TEST_MODE = os.environ.get('IS_TEST_MODE', 'false').lower() == 'true'
        
        # Vercel에서는 GOOGLE_APPLICATION_CREDENTIALS 환경 변수 자체를 구글 라이브러리가 직접 사용하므로,
        # 코드에서 파일 경로를 설정할 필요가 없습니다. (vercel.json 설정에 따라)

    # 필수 설정값이 모두 로드되었는지 확인
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


# --- 3. 전역 상태 변수 및 백그라운드 작업자 함수 정의 ---
SHARED_STATE = { "signal_level": "orange", "current_points": 100, "last_activity": "없음", "active_activities": [] }
state_lock = threading.Lock() # 스레드 간 SHARED_STATE 접근을 위한 락

# Notion 페이지 분석 및 점수 적용 함수
def analyze_image_and_apply_bonus(page):
    try:
        user_name = page["properties"]["생성자"]["created_by"]["name"]; user_id = database.get_or_create_user(user_name)
        image_url = page["properties"]["파일과 미디어"]["files"][0]["file"]["url"]
        logging.info(f"👀 '{user_name}'(ID:{user_id})님의 활동 분석 시작: {page['id']}")
        
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
            with state_lock: # SHARED_STATE 접근 시 락 사용
                SHARED_STATE["active_activities"].append({"activity": applied_activity, "points": applied_bonus, "end_time": time.time() + CONFIG["bonus_duration_seconds"]})
            logging.info(f"🎯 활동 '{applied_activity}' 추가! (+{applied_bonus}점)")
            database.add_activity_log(user_id, applied_activity, applied_bonus)
            
            database.check_and_award_achievements(user_id, user_name) 
    except Exception as e: logging.error(f"🚫 AI 분석/DB/뱃지 확인 중 오류: {e}")

# SHARED_STATE를 주기적으로 업데이트하는 스레드 (로컬에서만 실행)
def state_updater_worker():
    logging.info("⚙️ [상태 업데이트 직원] 근무 시작.")
    while True:
        try:
            with state_lock: # SHARED_STATE 접근 시 락 사용
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

# Notion 페이지를 감시하고 처리하는 통합 함수 (로컬 백그라운드 스레드 및 Vercel Cron Job에서 모두 사용)
def process_notion_events():
    logging.info("⚙️ [노션 이벤트 처리] 시작.")
    
    # API 클라이언트 초기화 여부 확인
    if notion is None or vision_client is None:
        logging.error("Notion 또는 Vision 클라이언트가 초기화되지 않아 노션 감시 작업을 수행할 수 없습니다.")
        return 0 # 처리된 페이지 없음
    
    processed_count = 0
    try:
        # 1. DB에서 이미 처리된 Notion 페이지 ID 목록을 가져옴
        processed_ids_from_db = database.get_processed_notion_page_ids()
        
        # 2. Notion에서 최신 페이지들을 쿼리 (생성 시간 내림차순, 최대 20개)
        results = notion.databases.query(database_id=DATABASE_ID, sorts=[{"property": "생성 일시", "direction": "descending"}], page_size=20).get("results")
        
        # 3. 새로운(또는 아직 미처리된) 페이지를 분석하고 DB에 기록
        for page in results:
            page_id = page["id"]
            
            # 아직 DB에 처리 기록이 없는 페이지라면
            if page_id not in processed_ids_from_db:
                files_property = page["properties"].get("파일과 미디어", {}).get("files", [])
                
                # 파일이 있고, '생성자' 정보가 있는 유효한 활동 페이지인 경우에만 분석
                if files_property and files_property[0].get("file") and "생성자" in page["properties"] and "created_by" in page["properties"]["생성자"]:
                    logging.info(f"✨ 새(또는 미처리) Notion 글 발견: {page_id}. 분석 시작.")
                    analyze_image_and_apply_bonus(page) # 이미지 분석 및 점수 적용
                    database.add_processed_notion_page(page_id) # 성공적으로 분석 후 DB에 '처리됨'으로 기록
                    processed_count += 1
                else:
                    # 파일이 없거나 유효한 활동이 아니더라도, 더 이상 체크하지 않도록 DB에 '처리됨'으로 기록
                    database.add_processed_notion_page(page_id)
                    logging.info(f"Notion page '{page_id}' has no file or valid creator; marking as processed to skip future checks.")
        
        logging.info(f"✅ Notion 이벤트 처리 완료. {processed_count}개 페이지 처리됨.")
        return processed_count

    except Exception as e:
        logging.critical(f"🚫 Notion 이벤트 처리 중 심각한 오류: {e}")
        return -1 # 오류 발생 시 -1 반환

# Notion을 주기적으로 감시하는 스레드 (로컬에서만 실행)
def notion_checker_worker_thread():
    logging.info("⚙️ [노션 감시 스레드] 근무 시작.")
    # 시작 시 Notion의 기존 글들을 DB에 '처리됨'으로 기록 (분석 스킵)
    try:
        if notion is None:
            logging.error("Notion 클라이언트가 초기화되지 않아 초기 노션 감시 작업을 시작할 수 없습니다.")
            return # 함수 종료
        initial_pages = notion.databases.query(database_id=DATABASE_ID, sorts=[{"property": "생성 일시", "direction": "descending"}], page_size=100).get("results")
        initial_processed_count = 0
        current_processed_ids_at_start = database.get_processed_notion_page_ids() # 시작 시 DB에서 처리된 ID 가져오기
        
        for page in initial_pages:
            if page["id"] not in current_processed_ids_at_start:
                database.add_processed_notion_page(page["id"]) # DB에 이미 처리된 것으로 기록 (분석 건너뜀)
                initial_processed_count += 1
        logging.info(f"✅ 시작 시 {initial_processed_count}개의 기존 Notion 글을 DB에 '처리됨'으로 기록했습니다. (분석 건너뜀)")
    except Exception as e: 
        logging.error(f"🚫 초기 Notion 글 학습/기록 중 오류 발생: {e}")

    # 주기적으로 process_notion_events 함수 호출
    while True:
        process_notion_events() # 주기적으로 노션 이벤트 처리 함수 호출
        time.sleep(CONFIG["check_interval_seconds"])


# SHARED_STATE를 API 요청 시에만 업데이트하는 함수 (Vercel에서 실시간 반영을 위해 사용)
def update_shared_state_on_request():
    """API 요청 시 SHARED_STATE를 즉시 업데이트합니다. (Vercel에서 사용)"""
    with state_lock: # SHARED_STATE 접근 시 락 사용
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
    # 이 함수는 로컬과 Vercel 모두에서 SHARED_STATE를 업데이트합니다.
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
    # admin.html 템플릿이 없으므로, 일단 간단한 텍스트로 대체 (선배님이 나중에 admin.html 만드시면 render_template 사용)
    return f"Admin Page. Status: {current_status}. DB Path: {database.DB_NAME}"
@app.route("/signal")
def signal_page(): return render_template('signal_web.html')
@app.route("/dashboard")
def dashboard_page(): return render_template('dashboard_web.html')
@app.route("/")
def index_page(): return render_template('index.html')

# --- Vercel Cron Job용 API (Vercel에서만 사용) ---
@app.route("/api/cron/process_notion_events", methods=['GET'])
def trigger_notion_processing():
    processed_count = process_notion_events() # 노션 이벤트 처리 함수 호출
    if processed_count == -1: # 오류 발생 시
        return jsonify({"status": "error", "message": "Failed to process Notion events"}), 500
    return jsonify({"status": "success", "pages_processed": processed_count})


# --- 5. 서버 실행 ---
if __name__ == '__main__':
    database.setup_database()
    
    # 로컬에서만 백그라운드 스레드를 실행합니다.
    # Vercel 환경에서는 Vercel이 'app' 객체를 찾아서 직접 실행하므로 이 블록은 건너뛰어집니다.
    # Vercel에서는 백그라운드 스레드 대신 Cron Job이 trigger_notion_processing API를 주기적으로 호출합니다.
    if not IS_VERCEL_ENV:
        threading.Thread(target=state_updater_worker, daemon=True, name="StateUpdater").start()
        threading.Thread(target=notion_checker_worker_thread, daemon=True, name="NotionChecker").start()
        
    logging.info("🚀 로컬 테스트 서버가 시작됩니다! http://127.0.0.1:5000 에서 접속하세요.")
    app.run(host='0.0.0.0', port=5000, debug=True)