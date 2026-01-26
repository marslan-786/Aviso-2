import os
import time
import json
import threading
import random
from flask import Flask, render_template, request, jsonify
from playwright.sync_api import sync_playwright

app = Flask(__name__)

# --- Configuration ---
SCREENSHOT_DIR = "static/screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)
USER_DATA_DIR = "/app/browser_data"

# --- Shared State ---
# یہ وہ جگہ ہے جہاں فرنٹ اینڈ سے آیا ہوا کوڈ رکھا جائے گا
shared_data = {"otp_code": None}

bot_status = {
    "step": "Idle",
    "images": [],
    "is_running": False,
    "needs_code": False # یہ فرنٹ اینڈ کو بتائے گا کہ ان پٹ باکس دکھاؤ
}

# --- Helper Functions ---
def force_google_translate_click(page):
    """
    اگر آٹو ٹرانسلیٹ فیل ہو جائے تو یہ فنکشن گوگل بار پر کلک کرنے کی کوشش کرے گا۔
    """
    try:
        # گوگل ٹرانسلیٹ بار کے عام سلیکٹرز
        translate_bar_btn = "#google_translate_element a.goog-te-menu-value"
        if page.is_visible(translate_bar_btn):
            print("Attempting to click Google Translate bar...")
            page.click(translate_bar_btn)
            # انگلش آپشن کا انتظار کریں اور کلک کریں (یہ تھوڑا ٹرکی ہو سکتا ہے)
            # فی الحال صرف بار پر کلک کر کے دیکھتے ہیں کہ کیا ہوتا ہے
            time.sleep(3) # ٹرانسلیشن لوڈ ہونے کا انتظار
    except Exception as e:
        print(f"Could not click translate bar: {e}")

def take_screenshot(page, name):
    timestamp = int(time.time())
    filename = f"{timestamp}_{name}.png"
    path = os.path.join(SCREENSHOT_DIR, filename)
    page.screenshot(path=path)
    # ہم فرنٹ اینڈ کو صرف فائل کا نام بھیجیں گے، پورا پاتھ نہیں
    bot_status["images"].append(filename)

def run_aviso_login(username, password):
    global bot_status, shared_data
    bot_status["is_running"] = True
    bot_status["needs_code"] = False
    bot_status["images"] = [] # پرانی تصاویر صاف
    shared_data["otp_code"] = None # پرانا کوڈ صاف

    with sync_playwright() as p:
        try:
            # ہم پرانی انجیکشن تکنیک بھی رکھیں گے، شاید کام کر جائے
            # inject_translation_prefs(USER_DATA_DIR) # (پرانے کوڈ والا فنکشن یہاں فرض کریں)

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
            
            # --- Step 1: Open Website & Translate ---
            bot_status["step"] = "Loading Website..."
            page.goto("https://aviso.bz/", timeout=60000)
            page.wait_for_load_state("networkidle")
            
            # زبردستی ٹرانسلیٹ کرنے کی کوشش
            force_google_translate_click(page)
            
            take_screenshot(page, "homepage")

            # --- Step 2: Login Process ---
            # کے مطابق لاگ ان پیج پر جائیں
            page.goto("https://aviso.bz/login")
            page.wait_for_load_state("networkidle")
            take_screenshot(page, "login_page_loaded")

            bot_status["step"] = "Filling Credentials..."
            # سلیکٹرز کی بنیاد پر
            page.fill("input[name='username']", username)
            page.fill("input[name='password']", password)
            take_screenshot(page, "credentials_filled")

            bot_status["step"] = "Submitting Login..."
            # لاگ ان بٹن پر کلک (رشین ٹیکسٹ: Вход в аккаунт)
            # ہم فارم سبمٹ کرنے کی کوشش کرتے ہیں جو زیادہ محفوظ ہے
            input_field = page.locator("input[name='password']")
            input_field.press("Enter")
            
            time.sleep(5) # اگلے پیج کے لوڈ ہونے کا انتظار
            take_screenshot(page, "after_submission")

            # --- Step 3: Check for 2FA Code Page ---
            # ہم میں موجود مخصوص ٹیکسٹ ڈھونڈیں گے
            # "Проверочный код" (Verification code) یا "Безопасность" (Security)
            if page.is_visible("text=Проверочный код") or page.is_visible("text=Security"):
                bot_status["step"] = "WAITING_FOR_CODE"
                bot_status["needs_code"] = True # فرنٹ اینڈ کو سگنل
                print("2FA Page Detected. Waiting for user input...")

                # --- Wait Loop for Code ---
                # یہ لوپ تب تک چلے گا جب تک آپ فرنٹ اینڈ سے کوڈ نہیں بھیجتے
                wait_count = 0
                while shared_data["otp_code"] is None:
                    time.sleep(2)
                    wait_count += 2
                    if wait_count % 10 == 0:
                         print(f"Still waiting for code... ({wait_count}s)")
                    if wait_count > 600: # 10 منٹ کا ٹائم آؤٹ
                         raise Exception("Timed out waiting for code.")

                # کوڈ مل گیا!
                bot_status["step"] = "Code Received! Submitting..."
                bot_status["needs_code"] = False
                code_to_fill = shared_data["otp_code"]

                # کے مطابق ان پٹ فیلڈ ڈھونڈیں اور بھریں
                # چونکہ اس پیج پر ایک ہی مین ان پٹ ہے، ہم ٹائپ ٹیکسٹ استعمال کرتے ہیں
                page.fill("input[type='text']", code_to_fill)
                take_screenshot(page, "code_filled")
                
                # میں بٹن "Войти в аккаунт" ہے
                # ہم پھر انٹر دبانے کا طریقہ استعمال کرتے ہیں جو اس پیج پر کام کرنا چاہیے
                page.locator("input[type='text']").press("Enter")
                
                bot_status["step"] = "Code Submitted. Waiting for Dashboard..."
                time.sleep(8) # ڈیش بورڈ لوڈ ہونے کا لمبا انتظار

                # Final Screenshot: Dashboard
                force_google_translate_click(page) # ڈیش بورڈ کو بھی ٹرانسلیٹ کرنے کی کوشش
                take_screenshot(page, "final_dashboard")
                bot_status["step"] = "Login Complete! Check Dashboard Screenshot."

            else:
                # اگر کوڈ پیج نہیں آیا تو شاید سیدھا ڈیش بورڈ آ گیا
                bot_status["step"] = "No Code Requested. Login Likely Complete."
                force_google_translate_click(page)
                take_screenshot(page, "direct_dashboard")

            # تھوڑی دیر رکیں تاکہ آپ آخری حالت دیکھ سکیں
            time.sleep(20)

        except Exception as e:
            bot_status["step"] = f"Error: {str(e)}"
            print(f"Error details: {e}")
            try:
                take_screenshot(page, "error_state")
            except:
                pass
        
        finally:
            context.close()
            bot_status["is_running"] = False
            bot_status["needs_code"] = False

# --- Flask Routes ---

@app.route('/')
def index():
    return render_template('index.html')

# کوڈ وصول کرنے کے لیے نیا روٹ
@app.route('/submit_code', methods=['POST'])
def submit_code_api():
    data = request.json
    code = data.get('code')
    if code:
        shared_data["otp_code"] = code
        return jsonify({"status": "Code received by backend"})
    return jsonify({"status": "No code provided"}), 400

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

@app.route('/static/screenshots/<path:filename>')
def serve_screenshot(filename):
    # یہ روٹ تصاویر کو کیشے سے بچانے میں مدد کرے گا
    return send_from_directory(SCREENSHOT_DIR, filename, add_etags=False, cache_timeout=0)

# import send_from_directory اوپر ایڈ کرنا نہ بھولیں
from flask import send_from_directory

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
