import os
import time
import json
import threading
import random
import re # ٹائم پڑھنے کے لیے یہ لائبریری ضروری ہے
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

# --- NEW: SMART YOUTUBE LOGIC ---
def process_youtube_tasks(context, page):
    bot_status["step"] = "Navigating to YouTube Tasks..."
    page.goto("https://aviso.bz/tasks-youtube")
    page.wait_for_load_state("networkidle")
    force_google_translate_click(page)
    take_screenshot(page, "1_youtube_list_loaded")

    # Loop for tasks
    for i in range(1, 15): # تھوڑے زیادہ ٹاسک چیک کریں گے
        if not bot_status["is_running"]: break
        
        bot_status["step"] = f"Scanning Task #{i}..."
        print(f"Scanning for task #{i}...")
        
        # --- FILTERING LOGIC ---
        # 1. صرف وہ قطاریں جن میں 'video' ہو (تاکہ Watch والے ملیں)
        # 2. 'Subscribe' اور 'Like' والوں کو نکالو
        # Aviso پر اکثر Watch والے ٹاسک کا نام 'Посмотреть видео' (Watch video) ہوتا ہے
        
        task_rows = page.locator("tr[id^='task_']")
        count = task_rows.count()
        
        target_row = None
        task_duration = 20 # ڈیفالٹ ٹائم اگر کچھ نہ ملا
        
        # لسٹ میں سے صحیح ٹاسک ڈھونڈو
        for idx in range(count):
            row = task_rows.nth(idx)
            text = row.inner_text().lower()
            
            # فلٹرز: ویڈیو ہونی چاہیے، لائک اور سبسکرائب نہیں
            if ("video" in text or "видео" in text) and \
               ("subscribe" not in text and "подписаться" not in text) and \
               ("like" not in text and "лайк" not in text):
                
                target_row = row
                
                # --- SMART TIMER LOGIC ---
                # متن میں سے ٹائم نکالو (مثلاً "180 sec" یا "20 сек")
                # Regex پیٹرن: کوئی بھی نمبر جس کے بعد sec یا сек ہو
                time_match = re.search(r'(\d+)\s*(sec|сек)', text)
                if time_match:
                    task_duration = int(time_match.group(1))
                    print(f"Detected Duration: {task_duration} seconds")
                else:
                    print("Could not detect time, using default 20s")
                
                break # پہلا صحیح ٹاسک مل گیا، لوپ توڑ دو
        
        if not target_row:
            print("No suitable video tasks found. Reloading...")
            page.reload()
            time.sleep(5)
            continue

        try:
            # --- ACTION 1: EXPAND ---
            print(f"Processing Task with duration: {task_duration}s")
            target_row.locator("span.go-link").click()
            time.sleep(3)
            take_screenshot(page, f"task_{i}_expanded_{task_duration}s")

            # --- ACTION 2: START ---
            start_button = target_row.locator("span.kh-ul-li-start-run")
            
            if start_button.is_visible():
                bot_status["step"] = f"Starting Task ({task_duration}s)..."
                
                with context.expect_page() as new_page_info:
                    start_button.click()
                
                new_page = new_page_info.value
                new_page.wait_for_load_state("domcontentloaded")
                
                # --- ACTION 3: SMART WAIT ---
                new_page.bring_to_front()
                
                # محفوظ انتظار: اصل ٹائم + 3 سے 6 سیکنڈ کا اضافی بفر
                safe_wait_time = task_duration + random.randint(3, 6)
                
                bot_status["step"] = f"Watching for {safe_wait_time}s..."
                print(f"Waiting for {safe_wait_time} seconds (Task req: {task_duration}s)...")
                
                # لمبی ویڈیوز کے لیے ہم چھوٹے ٹکڑوں میں انتظار کریں گے تاکہ بوٹ 'Dead' نہ لگے
                remaining = safe_wait_time
                while remaining > 0:
                    if not bot_status["is_running"]: 
                        new_page.close()
                        return
                    sleep_chunk = min(5, remaining) # ہر 5 سیکنڈ بعد سٹیٹس چیک کرو
                    time.sleep(sleep_chunk)
                    remaining -= sleep_chunk
                
                # Screenshot of video page just before closing
                try: take_screenshot(new_page, f"task_{i}_watched_proof")
                except: pass

                new_page.close()
                bot_status["step"] = "Video Closed. Confirming..."
                
                # --- ACTION 4: CONFIRM ---
                page.bring_to_front()
                time.sleep(2)
                
                confirm_btn = target_row.locator("span.serf-yam-but")
                if confirm_btn.is_visible():
                    confirm_btn.click()
                    bot_status["step"] = "Confirm Clicked. Waiting Balance..."
                    time.sleep(4)
                    take_screenshot(page, f"task_{i}_DONE")
                else:
                    take_screenshot(page, f"task_{i}_no_confirm_btn")
            
            else:
                print("Start button hidden.")

        except Exception as e:
            print(f"Task error: {e}")
            page.reload()
            time.sleep(5)

# --- MAIN LOGIN FUNCTION ---
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
            
            # --- LOGIN CHECK ---
            bot_status["step"] = "Checking Session..."
            page.goto("https://aviso.bz/", timeout=60000)
            page.wait_for_load_state("networkidle")
            
            if page.is_visible("text=Login") or page.is_visible("text=Вход"):
                print("Logging in...")
                page.goto("https://aviso.bz/login")
                page.fill("input[name='username']", username)
                page.fill("input[name='password']", password)
                page.locator("input[name='password']").press("Enter")
                time.sleep(5)

                if page.is_visible("input[name='code']"):
                    bot_status["step"] = "WAITING_FOR_CODE"
                    bot_status["needs_code"] = True
                    take_screenshot(page, "code_needed")
                    while shared_data["otp_code"] is None:
                        time.sleep(2)
                        if not bot_status["is_running"]: return
                    
                    page.fill("input[name='code']", shared_data["otp_code"])
                    page.locator("input[name='code']").press("Enter")
                    time.sleep(8)
            
            take_screenshot(page, "dashboard_ok")
            
            # --- START SMART TASKS ---
            process_youtube_tasks(context, page)

        except Exception as e:
            bot_status["step"] = f"Error: {str(e)}"
            print(f"Critical Error: {e}")
            try: take_screenshot(page, "critical_error")
            except: pass
        
        finally:
            try: context.close()
            except: pass
            bot_status["is_running"] = False

# --- FLASK ROUTES ---
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
