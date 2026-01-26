import os
import time
import json
import threading
import random
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# --- Configuration ---
SCREENSHOT_DIR = "static/screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)
USER_DATA_DIR = "/app/browser_data"

# --- Shared State ---
shared_data = {"otp_code": None}

bot_status = {
    "step": "Idle",
    "images": [],
    "is_running": False,
    "needs_code": False
}

def force_google_translate_click(page):
    try:
        translate_bar_btn = "#google_translate_element a.goog-te-menu-value"
        if page.is_visible(translate_bar_btn):
            page.click(translate_bar_btn)
            time.sleep(2)
    except:
        pass

def take_screenshot(page, name):
    try:
        timestamp = int(time.time())
        filename = f"{timestamp}_{name}.png"
        path = os.path.join(SCREENSHOT_DIR, filename)
        page.screenshot(path=path)
        bot_status["images"].append(filename)
    except Exception as e:
        print(f"Screenshot failed: {e}")

# --- NEW: YouTube Task Logic ---
def process_youtube_tasks(context, page):
    bot_status["step"] = "Navigating to YouTube Tasks..."
    # ڈائریکٹ لنک پر جائیں تاکہ نیویگیشن کا مسئلہ نہ ہو
    page.goto("https://aviso.bz/tasks-youtube")
    page.wait_for_load_state("networkidle")
    force_google_translate_click(page)
    take_screenshot(page, "youtube_task_list")

    # لوپ شروع کریں (مثلاً 10 ویڈیوز کے لیے)
    for i in range(10):
        if not bot_status["is_running"]: break
        
        bot_status["step"] = f"Looking for Video Task #{i+1}..."
        
        # تمام ٹاسک کی قطاریں (Rows) ڈھونڈیں جو 'subscribe' نہ ہوں
        # ہم ان قطاروں کو ڈھونڈیں گے جن میں 'Watch the video' یا 'Просмотр видео' لکھا ہو
        # اور ان کو اگنور کریں گے جن میں 'Subscribe' یا 'Подписаться' ہو
        
        # یہ سیلیکٹر ان تمام ٹاسکس کو اٹھائے گا جو ویڈیو والے ہیں
        task_selector = "tr[id^='task_']:has-text('video')" 
        
        # اگر لسٹ میں ویڈیو نہیں ملتی تو ریفریش کریں
        if not page.is_visible(task_selector):
            print("No video tasks visible, refreshing...")
            page.reload()
            time.sleep(5)
            continue

        # پہلا دستیاب ٹاسک اٹھائیں
        task_row = page.locator(task_selector).first
        
        # چیک کریں کہ کیا یہ واقعی سبسکرپشن والا تو نہیں؟
        task_text = task_row.inner_text().lower()
        if "subscribe" in task_text or "подписаться" in task_text:
            print("Skipping subscription task...")
            # اس ٹاسک کو لسٹ سے ہٹانے کے لیے پیج ریفریش یا اگلا logic لگانا ہوگا
            # فی الحال ہم صرف پہلا کلک ایبل ٹاسک ڈھونڈتے ہیں
            continue

        try:
            # 1. ٹاسک کے ٹائٹل پر کلک کریں تاکہ وہ ایکسپینڈ (Expand) ہو جائے
            print("Clicking task title...")
            task_row.locator("span.go-link").click()
            time.sleep(2)

            # 2. اب "Start" یا "Get Started" بٹن ڈھونڈیں
            # میں بٹن نیلا یا ہرا ہوتا ہے
            start_button = task_row.locator("span.kh-ul-li-start-run") 
            
            if start_button.is_visible():
                bot_status["step"] = "Opening Video Tab..."
                
                # نیا ٹیب کھلنے کا انتظار کریں
                with context.expect_page() as new_page_info:
                    start_button.click()
                
                new_page = new_page_info.value
                
                # --- اہم ترین سٹیپ ---
                # نئے ٹیب کو سامنے لائیں تاکہ ٹائمر چلے
                new_page.bring_to_front()
                bot_status["step"] = "Watching Video (15-20s)..."
                
                # رینڈم انتظار (15 سے 20 سیکنڈ)
                wait_time = random.randint(18, 25) # تھوڑا زیادہ رکھیں تاکہ سیف رہے
                print(f"Waiting {wait_time} seconds on video page...")
                time.sleep(wait_time)
                
                # ٹائم پورا ہونے کے بعد ٹیب بند کر دیں
                new_page.close()
                bot_status["step"] = "Video Closed. Confirming..."
                
                # واپس مین پیج پر فوکس
                page.bring_to_front()
                
                # 3. اب "Confirm" بٹن پر کلک کریں
                # بٹن کا نام "Confirm viewing" یا "Подтвердить" ہوگا
                confirm_btn = task_row.locator("span.serf-yam-but") # یہ کلاس اکثر کنفرم بٹن کی ہوتی ہے
                
                if confirm_btn.is_visible():
                    confirm_btn.click()
                    print("Clicked Confirm!")
                    time.sleep(3) # بیلنس ایڈ ہونے کا انتظار
                    take_screenshot(page, f"task_{i+1}_completed")
                else:
                    print("Confirm button not found, maybe auto-confirmed?")
            
            else:
                print("Start button not found for this task.")

        except Exception as e:
            print(f"Task failed: {e}")
            # اگر ٹاسک فیل ہو تو پیج ریفریش کریں تاکہ پھنسے نہ
            page.reload()
            time.sleep(5)

# --- MAIN LOGIN + TASK FUNCTION ---
def run_aviso_login(username, password):
    global bot_status, shared_data
    from playwright.sync_api import sync_playwright

    bot_status["is_running"] = True
    bot_status["needs_code"] = False
    bot_status["images"] = []
    shared_data["otp_code"] = None

    with sync_playwright() as p:
        try:
            context = p.chromium.launch_persistent_context(
                USER_DATA_DIR,
                headless=True,
                args=[
                    "--lang=en-US",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--start-maximized"
                ],
                viewport={"width": 1280, "height": 800}
            )
            
            page = context.new_page()
            
            # --- LOGIN PART (Same as before) ---
            bot_status["step"] = "Checking Login Status..."
            page.goto("https://aviso.bz/", timeout=60000)
            page.wait_for_load_state("networkidle")
            
            # اگر لاگ ان نہیں ہے تو لاگ ان کرو
            if page.is_visible("text=Login") or page.is_visible("text=Вход"):
                print("Not logged in. Logging in...")
                page.goto("https://aviso.bz/login")
                page.fill("input[name='username']", username)
                page.fill("input[name='password']", password)
                page.locator("input[name='password']").press("Enter")
                time.sleep(5)

                if page.is_visible("input[name='code']"):
                    bot_status["step"] = "WAITING_FOR_CODE"
                    bot_status["needs_code"] = True
                    while shared_data["otp_code"] is None:
                        time.sleep(2)
                        if not bot_status["is_running"]: return
                    
                    page.fill("input[name='code']", shared_data["otp_code"])
                    page.locator("input[name='code']").press("Enter")
                    time.sleep(5)
            
            # --- LOGIN DONE -> START TASKS ---
            take_screenshot(page, "dashboard_reached")
            
            # اب یوٹیوب ٹاسک شروع کرو
            process_youtube_tasks(context, page)

        except Exception as e:
            bot_status["step"] = f"Error: {str(e)}"
            print(f"Critical Error: {e}")
            try: take_screenshot(page, "error_screenshot")
            except: pass
        
        finally:
            try: context.close()
            except: pass
            bot_status["is_running"] = False

# --- FLASK ROUTES (Same as before) ---
@app.route('/')
def index(): return render_template('index.html')

@app.route('/submit_code', methods=['POST'])
def submit_code_api():
    data = request.json
    shared_data["otp_code"] = data.get('code')
    return jsonify({"status": "Received"})

@app.route('/start', methods=['POST'])
def start_bot():
    if bot_status["is_running"]: return jsonify({"status": "Running"})
    data = request.json
    t = threading.Thread(target=run_aviso_login, args=(data.get('username'), data.get('password')))
    t.start()
    return jsonify({"status": "Started"})

@app.route('/status')
def status(): return jsonify(bot_status)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
