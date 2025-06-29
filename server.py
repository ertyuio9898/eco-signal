# --- server.py (SyntaxError 수정된 최종 버전) ---

import time, os, threading, logging, sys, sqlite3, configparser
from flask import Flask, jsonify, render_template, request
from notion_client import Client
from google.cloud import vision
import pytz
import database

# --- Config & 초기화 ---
config = configparser.ConfigParser()
try:
    config.read('config.ini', encoding='utf-8')
    NOTION_API_KEY = config['SECRETS']['NOTION_API_KEY']
    DATABASE_ID = config['SECRETS']['DATABASE_ID']
    ADMIN_PASSWORD = config['SECRETS']['ADMIN_PASSWORD']
    GOOGLE_CREDENTIALS_FILENAME = config['SECRETS']['GOOGLE_CREDENTIALS_FILENAME']
    IS_TEST_MODE = config['MODE'].getboolean('IS_TEST_MODE')
except Exception as e:
    print(f"🚫 'config.ini' 파일을 읽는 중 오류가 발생했습니다: {e}")
    sys.exit(1)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
CONFIG = {"check_interval_seconds": 10, "pending_check_interval_seconds": 15, "pending_timeout_seconds": 300, "point_policy": { "tumbler": 20, "cup": 20, "stairs": 30, "paper": 15, "thermos": 25 }, "level_thresholds": { "green": 150, "yellow": 120, "orange": 100 }}
CONFIG["bonus_duration_seconds"] = 60 if IS_TEST_MODE else 3600

if getattr(sys, 'frozen', False): application_path = os.path.dirname(sys.executable)
else: application_path = os.path.dirname(os.path.abspath(__file__))
credentials_path = os.path.join(application_path, GOOGLE_CREDENTIALS_FILENAME)
os.environ['GOOGLE_APPLICATION_CREDENTIALS'] = credentials_path
try:
    notion = Client(auth=NOTION_API_KEY); vision_client = vision.ImageAnnotatorClient()
    logging.info("✅ 노션 및 Google Vision API 클라이언트 초기화 성공.")
except Exception as e:
    logging.error(f"🚫 API 초기화 실패: {e}"); sys.exit(1)

SHARED_STATE = { "signal_level": "orange", "current_points": 100, "last_activity": "없음", "active_activities": [] }
PENDING_ANALYSIS_QUEUE = {}; PROCESSED_PAGE_IDS = set(); state_lock = threading.Lock()

# --- 백그라운드 작업자들 (수정 없음) ---
def analyze_image_and_apply_bonus(page):
    try:
        user_name = page["properties"]["생성자"]["created_by"]["name"]; user_id = database.get_or_create_user(user_name)
        image_url = page["properties"]["파일과 미디어"]["files"][0]["file"]["url"]
        logging.info(f"👀 '{user_name}'(ID:{user_id})님의 활동 분석 시작: {page['id']}")
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

def state_updater_worker():
    logging.info("⚙️ [상태 업데이트 직원] 근무 시작.");
    while True:
        try:
            with state_lock:
                SHARED_STATE["active_activities"][:] = [act for act in SHARED_STATE["active_activities"] if act["end_time"] >= time.time()]
                total_points = 100 + sum(act["points"] for act in SHARED_STATE["active_activities"])
                SHARED_STATE["current_points"] = total_points; SHARED_STATE["last_activity"] = SHARED_STATE["active_activities"][-1]["activity"] if SHARED_STATE["active_activities"] else "없음"
                level = "orange"
                if total_points >= CONFIG["level_thresholds"]["green"]: level = "green"
                elif total_points >= CONFIG["level_thresholds"]["yellow"]: level = "yellow"
                SHARED_STATE["signal_level"] = level
        except Exception as e: logging.error(f"🚫 상태 업데이트 중 심각한 오류: {e}")
        time.sleep(1)

def notion_checker_worker():
    logging.info("⚙️ [노션 감시 직원] 근무 시작.")
    try:
        initial_pages = notion.databases.query(database_id=DATABASE_ID, sorts=[{"property": "생성 일시", "direction": "descending"}], page_size=100).get("results")
        with state_lock:
            for page in initial_pages: PROCESSED_PAGE_IDS.add(page["id"])
        logging.info(f"✅ 초기 글 {len(initial_pages)}개 학습 완료.")
    except Exception as e: logging.error(f"🚫 초기 글 학습 중 오류 발생: {e}")
    while True:
        try:
            results = notion.databases.query(database_id=DATABASE_ID, sorts=[{"property": "생성 일시", "direction": "descending"}], page_size=20).get("results")
            with state_lock:
                new_pages = [p for p in results if p["id"] not in PROCESSED_PAGE_IDS and p["id"] not in PENDING_ANALYSIS_QUEUE]
            if new_pages:
                logging.info(f"✨ {len(new_pages)}개의 새로운 글 발견! 분석 대기열에 추가합니다.")
                with state_lock:
                    for page in new_pages: PENDING_ANALYSIS_QUEUE[page["id"]] = time.time()
        except Exception as e: logging.error(f"🚫 노션 확인 중 오류: {e}")
        time.sleep(CONFIG["check_interval_seconds"])

def pending_processor_worker():
    logging.info("⚙️ [AI 분석 전문가] 근무 시작.")
    while True:
        page_id_to_process = None
        with state_lock:
            if PENDING_ANALYSIS_QUEUE: page_id_to_process = next(iter(PENDING_ANALYSIS_QUEUE))
        if page_id_to_process:
            try:
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

# --- Flask 앱 설정 및 모든 라우팅 ---
app = Flask(__name__)

# --- API 엔드포인트 ---
@app.route("/status")
def get_status():
    with state_lock:
        return jsonify(SHARED_STATE)

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

# --- 페이지 엔드포인트 ---
@app.route("/admin")
def admin_dashboard():
    if request.args.get('password') != ADMIN_PASSWORD:
        return "<h1>🚫 접근이 거부되었습니다.</h1>", 403
    with state_lock:
        current_status = SHARED_STATE.copy()
    return render_template('admin.html', server_status=current_status, ranking_data=database.get_monthly_ranking(), recent_activities=database.get_recent_activities())

@app.route("/signal")
def signal_page():
    return render_template('signal_web.html')

@app.route("/dashboard")
def dashboard_page():
    return render_template('dashboard_web.html')

@app.route("/")
def index_page(): 
    return render_template('index.html')

# --- 서버 실행 ---
if __name__ == '__main__':
    database.setup_database()
    threading.Thread(target=state_updater_worker, daemon=True, name="StateUpdater").start()
    threading.Thread(target=notion_checker_worker, daemon=True, name="NotionChecker").start()
    threading.Thread(target=pending_processor_worker, daemon=True, name="PendingProcessor").start()
    logging.info("🚀 서버가 모든 준비를 마치고 시작됩니다! http://127.0.0.1:5000 에서 접속하세요.")
    app.run(host='0.0.0.0', port=5000, debug=False)