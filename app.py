import os
import time
import json
import threading
import random
from flask import Flask, render_template, request, jsonify

app = Flask(__name__)

# --- Configuration ---
# Flask خود بخود 'static' فولڈر کو پہچانتا ہے۔
# ہم تصاویر اسی کے اندر محفوظ کریں گے۔
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

# --- Helper Functions ---
def force_google_translate_click(page):
    try:
        # Google Translate Bar Click Logic
        translate_bar_btn = "#google_translate_element a.goog-te-menu-value"
        if page.is_visible(translate_bar_btn):
            print("Attempting to click Google Translate bar...")
            page.click(translate_bar_btn)
            time.sleep(2)
    except Exception as e:
        print(f"Translate click failed: {e}")

def take_screenshot(page, name):
    try:
        timestamp = int(time.time())
        filename = f"{timestamp}_{name}.png"
        path = os.path.join(SCREENSHOT_DIR, filename)
        page.screenshot(path=path)
        # ہم صرف فائل کا نام لسٹ میں ڈالیں گے
        # فرنٹ اینڈ خود اس کے ساتھ /static/screenshots/ لگا لے گا
        bot_status["images"].append(filename)
    except Exception as e:
        print(f"Screenshot failed: {e}")

def run_aviso_login(username, password):
    global bot_status, shared_data
    from playwright.sync_api import sync_playwright # Import inside thread

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
            
            # --- Step 1: Open Website ---
            bot_status["step"] = "Loading Website..."
            page.goto("https://aviso.bz/", timeout=60000)
            page.wait_for_load_state("networkidle")
            force_google_translate_click(page)
            take_screenshot(page, "homepage")

            # --- Step 2: Login Check ---
            # چیک کریں کہ کیا لاگ ان بٹن موجود ہے؟
            if page.is_visible("text=Login") or page.is_visible("text=Вход") or page.is_visible("a[href='/login']"):
                bot_status["step"] = "Going to Login Page..."
                page.goto("https://aviso.bz/login")
                page.wait_for_load_state("networkidle")
                take_screenshot(page, "login_page_loaded")

                bot_status["step"] = "Filling Credentials..."
                page.fill("input[name='username']", username)
                page.fill("input[name='password']", password)
                take_screenshot(page, "credentials_filled")

                bot_status["step"] = "Submitting Login..."
                # پاسورڈ فیلڈ میں انٹر پریس کرنا زیادہ محفوظ طریقہ ہے
                page.locator("input[name='password']").press("Enter")
                
                time.sleep(5)
                take_screenshot(page, "after_submission")

                # --- Step 3: Check for 2FA Code ---
                # مختلف الفاظ جو کوڈ پیج پر ہو سکتے ہیں
                if page.is_visible("text=Проверочный код") or page.is_visible("text=Security") or page.is_visible("input[name='code']"):
                    bot_status["step"] = "WAITING_FOR_CODE"
                    bot_status["needs_code"] = True
                    print("2FA Page Detected. Waiting for user input...")
                    take_screenshot(page, "code_required")

                    # --- Wait Loop ---
                    wait_count = 0
                    while shared_data["otp_code"] is None:
                        time.sleep(2)
                        wait_count += 2
                        if wait_count % 10 == 0:
                            print(f"Waiting for code... {wait_count}s")
                        if not bot_status["is_running"]: # اگر یوزر نے روک دیا
                            return

                    # کوڈ مل گیا
                    bot_status["step"] = "Code Received! Submitting..."
                    bot_status["needs_code"] = False
                    code_val = shared_data["otp_code"]

                    # کوڈ انٹر کریں
                    page.fill("input[type='text']", code_val)
                    take_screenshot(page, "code_filled")
                    page.locator("input[type='text']").press("Enter")
                    
                    bot_status["step"] = "Code Submitted. Loading Dashboard..."
                    time.sleep(8)
                    force_google_translate_click(page)
                    take_screenshot(page, "final_dashboard")
                
                else:
                    bot_status["step"] = "No Code Requested. Direct Dashboard?"
                    force_google_translate_click(page)
                    take_screenshot(page, "direct_dashboard_check")
            
            else:
                bot_status["step"] = "Already Logged In!"
                force_google_translate_click(page)
                take_screenshot(page, "already_logged_in")

            # --- Keep Alive ---
            # براؤزر کو تھوڑی دیر کھلا رکھیں تاکہ سیشن اچھی طرح سیو ہو جائے
            time.sleep(10)

        except Exception as e:
            bot_status["step"] = f"Error: {str(e)}"
            print(f"Error: {e}")
            try:
                take_screenshot(page, "error_occurred")
            except:
                pass
        
        finally:
            try:
                context.close()
            except:
                pass
            bot_status["is_running"] = False
            bot_status["needs_code"] = False

# --- Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/submit_code', methods=['POST'])
def submit_code_api():
    data = request.json
    code = data.get('code')
    if code:
        shared_data["otp_code"] = code
        return jsonify({"status": "Code received"})
    return jsonify({"status": "No code"}), 400

@app.route('/start', methods=['POST'])
def start_bot():
    if bot_status["is_running"]:
        return jsonify({"status": "Bot is already running!"})
    data = request.json
    t = threading.Thread(target=run_aviso_login, args=(data.get('username'), data.get('password')))
    t.start()
    return jsonify({"status": "Started"})

@app.route('/status')
def status():
    return jsonify(bot_status)

# نوٹ: یہاں سے وہ 'serve_screenshot' والا خراب کوڈ ہٹا دیا گیا ہے۔
# Flask اب خود بخود static فولڈر سے فائلیں اٹھائے گا۔

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
