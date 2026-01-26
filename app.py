import os
import time
import threading
from flask import Flask, render_template, request, jsonify
from playwright.sync_api import sync_playwright

app = Flask(__name__)

# اسکرین شاٹس کے لیے فولڈر
SCREENSHOT_DIR = "static/screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)

# بوٹ کی اسٹیٹس
bot_status = {
    "step": "Idle",
    "images": [],
    "is_running": False
}

def run_aviso_login(username, password):
    global bot_status
    bot_status["is_running"] = True
    bot_status["images"] = [] # پرانی تصاویر صاف کر دیں
    
    user_data_dir = "/app/browser_data" # Docker Volume Path

    with sync_playwright() as p:
        # 1. براؤزر لانچ (Auto Translate Logic)
        context = p.chromium.launch_persistent_context(
            user_data_dir,
            headless=True, # Docker میں Headless ہی چلے گا
            args=["--lang=en-US"],
            viewport={"width": 1280, "height": 720},
            permissions=["clipboard-read", "clipboard-write"],
            prefs={
                "translate": {"enabled": True},
                "translate_whitelists": {"ru": "en"},
                "translate_allowed/ru": True
            }
        )
        
        page = context.new_page()
        
        try:
            # Step 1: Open Website
            bot_status["step"] = "Opening Website..."
            page.goto("https://aviso.bz/")
            page.wait_for_load_state("networkidle")
            
            # Screenshot 1: Homepage
            img_path = f"{SCREENSHOT_DIR}/1_homepage.png"
            page.screenshot(path=img_path)
            bot_status["images"].append("/" + img_path)
            print("Homepage loaded.")

            # Step 2: Check Login Status
            # اگر "Login" کا بٹن نظر آ رہا ہے تو مطلب لاگ ان نہیں ہے
            if page.is_visible("text=Login") or page.is_visible("text=Registration"):
                bot_status["step"] = "Not Logged In. Clicking Login..."
                
                # لاگ ان پیج پر جاؤ
                page.click("text=Login") 
                page.wait_for_load_state("networkidle")
                
                # Screenshot 2: Login Page
                img_path = f"{SCREENSHOT_DIR}/2_login_page.png"
                page.screenshot(path=img_path)
                bot_status["images"].append("/" + img_path)

                # Step 3: Fill Credentials
                bot_status["step"] = "Filling Credentials..."
                # کے مطابق ان پٹ فیلڈز
                page.fill("input[name='username']", username) # یا generic سلیکٹر
                page.fill("input[name='password']", password)
                
                # Screenshot 3: Filled Form
                img_path = f"{SCREENSHOT_DIR}/3_filled_form.png"
                page.screenshot(path=img_path)
                bot_status["images"].append("/" + img_path)

                # Step 4: Click Submit
                bot_status["step"] = "Clicking Login Button..."
                # میں بٹن "Log in to your account" ہے
                page.click("button:has-text('Log in to your account')")
                
                # تھوڑا انتظار (ہوسکتا ہے کیپچا یا کوڈ مانگے)
                time.sleep(5)
                
                # Screenshot 4: After Submit (Result)
                img_path = f"{SCREENSHOT_DIR}/4_after_login.png"
                page.screenshot(path=img_path)
                bot_status["images"].append("/" + img_path)
                
                bot_status["step"] = "Check Screenshot: Did it ask for Code?"

            else:
                bot_status["step"] = "Already Logged In! (Direct Dashboard)"
                img_path = f"{SCREENSHOT_DIR}/dashboard_direct.png"
                page.screenshot(path=img_path)
                bot_status["images"].append("/" + img_path)

        except Exception as e:
            bot_status["step"] = f"Error: {str(e)}"
        
        finally:
            # ہم براؤزر ابھی بند نہیں کر رہے تاکہ سیشن سیو رہے
            context.close()
            bot_status["is_running"] = False

# --- Flask Routes ---

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/start', methods=['POST'])
def start_bot():
    data = request.json
    username = data.get('username')
    password = data.get('password')
    
    # الگ تھریڈ میں چلاؤ تاکہ UI جام نہ ہو
    thread = threading.Thread(target=run_aviso_login, args=(username, password))
    thread.start()
    
    return jsonify({"status": "Bot Started"})

@app.route('/status')
def get_status():
    return jsonify(bot_status)

# یہ اوپر import میں ایڈ کرنا


# ... باقی سارا کوڈ ویسا ہی ...

if __name__ == '__main__':
    # ریلوے کا پورٹ اٹھاؤ، اگر نہ ملے تو 5000 استعمال کرو
    port = int(os.environ.get("PORT", 5000))
    
    # host='0.0.0.0' لازمی ہے تاکہ باہر سے ایکسس ہو سکے
    app.run(host='0.0.0.0', port=port)

