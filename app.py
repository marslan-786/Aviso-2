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
USER_DATA_DIR = "/app/browser_data"  # Docker Volume Path

# --- Bot State ---
bot_status = {
    "step": "Idle",
    "images": [],
    "is_running": False
}

def inject_translation_prefs(user_data_path):
    """
    یہ فنکشن براؤزر چلنے سے پہلے اس کی سیٹنگز فائل میں 
    ٹرانسلیشن زبردستی آن کرنے کا کوڈ لکھ دے گا۔
    """
    try:
        default_dir = os.path.join(user_data_path, "Default")
        os.makedirs(default_dir, exist_ok=True)
        prefs_file = os.path.join(default_dir, "Preferences")

        # اگر فائل پہلے سے ہے تو پڑھو، ورنہ خالی ڈکشنری بناؤ
        if os.path.exists(prefs_file):
            with open(prefs_file, 'r') as f:
                try:
                    prefs = json.load(f)
                except:
                    prefs = {}
        else:
            prefs = {}

        # --- Translation Settings Injection ---
        if "translate" not in prefs:
            prefs["translate"] = {}
        
        # یہ سیٹنگز کروم کو بتاتی ہیں: "رشین کو انگلش کرو"
        prefs["translate"]["enabled"] = True
        prefs["translate"]["whitelists"] = {"ru": "en", "und": "en"} # und = undefined
        prefs["translate_allowed"] = {"ru": True}
        
        # سیٹنگز واپس فائل میں لکھ دو
        with open(prefs_file, 'w') as f:
            json.dump(prefs, f)
        
        print("✅ Translation Preferences Injected Successfully!")
    except Exception as e:
        print(f"⚠️ Could not inject preferences: {e}")

def run_aviso_login(username, password):
    global bot_status
    bot_status["is_running"] = True
    bot_status["images"] = []
    
    # براؤزر چلانے سے پہلے "دماغ" سیٹ کرو
    inject_translation_prefs(USER_DATA_DIR)

    with sync_playwright() as p:
        try:
            # 1. Launch Browser (Error Fixed Here)
            # ہم نے 'prefs' ہٹا دیا ہے اور ڈائریکٹ فائل انجیکشن کر دی ہے
            context = p.chromium.launch_persistent_context(
                USER_DATA_DIR,
                headless=True,
                args=[
                    "--lang=en-US",            # UI Language English
                    "--no-sandbox",            # Docker Safety
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage", # Memory Crash Fix
                    "--start-maximized"        # Full View
                ],
                viewport={"width": 1280, "height": 800}
            )
            
            page = context.new_page()
            
            # --- Step 1: Website Open ---
            bot_status["step"] = "Loading Website..."
            page.goto("https://aviso.bz/", timeout=60000) # 60 sec timeout for slow internet
            page.wait_for_load_state("networkidle")
            
            # Screenshot 1
            path1 = f"{SCREENSHOT_DIR}/1_home.png"
            page.screenshot(path=path1)
            bot_status["images"].append("/" + path1)
            
            # --- Step 2: Login Check ---
            # ہم رشین اور انگلش دونوں ٹیکسٹ چیک کریں گے
            login_selectors = ["text=Login", "text=Вход", "a[href='/login']"]
            found_login = False
            for sel in login_selectors:
                if page.is_visible(sel):
                    found_login = True
                    page.click(sel)
                    break
            
            if found_login:
                bot_status["step"] = "Login Page Detected..."
                page.wait_for_load_state("networkidle")
                
                # Screenshot 2
                path2 = f"{SCREENSHOT_DIR}/2_login_page.png"
                page.screenshot(path=path2)
                bot_status["images"].append("/" + path2)
                
                # --- Step 3: Input Credentials ---
                # Aviso اکثر نام بدلتا رہتا ہے، ہم generic names ٹرائی کریں گے
                page.fill("input[name='username']", username)
                page.fill("input[name='password']", password)
                
                # Screenshot 3
                path3 = f"{SCREENSHOT_DIR}/3_credentials_filled.png"
                page.screenshot(path=path3)
                bot_status["images"].append("/" + path3)
                
                # --- Step 4: Submit ---
                # بٹن پر کلک (ID یا Class ڈھونڈ کر)
                submit_btn = "button[type='submit']"
                if page.is_visible(submit_btn):
                    page.click(submit_btn)
                else:
                    # اگر بٹن نہ ملے تو Enter دبا دو
                    page.keyboard.press("Enter")
                
                bot_status["step"] = "Submitted! Waiting for Response..."
                time.sleep(5) # پیج لوڈ ہونے کا انتظار
                
                # Screenshot 4 (Final Result)
                path4 = f"{SCREENSHOT_DIR}/4_result.png"
                page.screenshot(path=path4)
                bot_status["images"].append("/" + path4)
                
                bot_status["step"] = "Check Images: Code Required or Dashboard?"
            
            else:
                bot_status["step"] = "No Login Button Found (Maybe Already Logged In?)"
                path_dash = f"{SCREENSHOT_DIR}/dashboard_maybe.png"
                page.screenshot(path=path_dash)
                bot_status["images"].append("/" + path_dash)

            # --- Keep Alive Loop (تاکہ تم کوڈ ڈال سکو) ---
            # یہ لوپ براؤزر کو 10 منٹ تک کھلا رکھے گا
            for i in range(60): 
                if not bot_status["is_running"]: break
                time.sleep(10)
                
        except Exception as e:
            bot_status["step"] = f"Error: {str(e)}"
            print(f"Error: {e}")
        
        finally:
            # جب تم چاہو گے تب بند ہوگا
            context.close()
            bot_status["is_running"] = False

# --- API Routes ---
@app.route('/')
def index():
    return render_template('index.html')

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

if __name__ == '__main__':
    # Railway Environment Port Setup
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
