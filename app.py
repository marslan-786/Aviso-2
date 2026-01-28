import os
import time
import json
import threading
import random
import shutil
import datetime
import subprocess
from flask import Flask, render_template, request, jsonify, send_file

app = Flask(__name__)

# --- Configuration ---
SCREENSHOT_DIR = "static/screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)
USER_DATA_DIR = "/app/browser_data2"
DEBUG_FILE = "debug_source.html"

# --- Shared State ---
shared_data = {"otp_code": None}
current_browser_context = None

bot_status = {
    "step": "Idle",
    "images": [],
    "is_running": False,
    "needs_code": False
}

gmail_status = {
    "active": False,
    "step": "Waiting",
    "screenshot": "placeholder.png"
}

# --- HELPER FUNCTIONS ---
def kill_all_browsers():
    try:
        subprocess.run(["pkill", "-9", "chrome"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["pkill", "-9", "chromium"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(2)
    except: pass

def take_screenshot(page, name):
    try:
        timestamp = int(time.time())
        filename = f"{timestamp}_{name}.png"
        path = os.path.join(SCREENSHOT_DIR, filename)
        page.screenshot(path=path)
        # Aviso Bot uses listing
        bot_status["images"].append(filename)
        # Gmail Bot uses single update
        gmail_status["screenshot"] = filename 
        return filename
    except: return None

def save_debug_html(page, step_name):
    try:
        content = page.content()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        separator = f"\n\n\n"
        with open(DEBUG_FILE, "a", encoding="utf-8") as f:
            f.write(separator + content)
    except: pass

def reset_debug_log():
    try:
        with open(DEBUG_FILE, "w", encoding="utf-8") as f:
            f.write("<h1>🤖 BOT LOGS STARTED</h1>")
    except: pass

# ======================================================
#  PART 1: AVISO BOT (OLD ENGINE - SAME AS BEFORE)
# ======================================================
# ... (یہ حصہ بالکل وہی پرانا ہے، اسے نہیں چھیڑا تاکہ ٹاسک خراب نہ ہوں) ...

def get_best_task_via_js(page):
    return page.evaluate("""() => {
        const tables = Array.from(document.querySelectorAll('table[id^="ads-link-"]'));
        for (let table of tables) {
            if (table.offsetParent === null) continue;
            const rect = table.getBoundingClientRect();
            if (rect.height === 0 || rect.width === 0) continue; 
            const style = window.getComputedStyle(table);
            if (style.display === 'none' || style.visibility === 'hidden') continue;
            const idPart = table.id.replace('ads-link-', '');
            if (!table.querySelector('.ybprosm')) continue;
            const timerInput = document.getElementById('ads_timer_' + idPart);
            const duration = timerInput ? parseInt(timerInput.value) : 20;
            return {
                id: idPart, duration: duration, tableId: table.id,
                startSelector: '#link_ads_start_' + idPart,
                confirmSelector: '#ads_btn_confirm_' + idPart
            };
        }
        return null; 
    }""")

def perform_human_mouse_click(page, selector, screenshot_name):
    try:
        if not page.is_visible(selector): return False
        box = page.locator(selector).bounding_box()
        if box:
            x = box['x'] + box['width'] / 2 + random.uniform(-10, 10)
            y = box['y'] + box['height'] / 2 + random.uniform(-5, 5)
            page.mouse.move(x, y, steps=15) 
            time.sleep(0.3)
            page.evaluate(f"""() => {{
                const d = document.createElement('div'); d.id = 'click-dot'; d.style.position = 'fixed'; 
                d.style.left = '{x-5}px'; d.style.top = '{y-5}px'; d.style.width = '10px'; d.style.height = '10px';
                d.style.background = 'red'; d.style.border = '2px solid white'; d.style.borderRadius = '50%'; d.style.zIndex = '9999999';
                document.body.appendChild(d);
            }}""")
            take_screenshot(page, screenshot_name)
            page.mouse.down()
            time.sleep(random.uniform(0.05, 0.15))
            page.mouse.up()
            time.sleep(0.5)
            page.evaluate("if(document.getElementById('click-dot')) document.getElementById('click-dot').remove();")
            return True
    except: pass
    return False

def ensure_video_playing(page):
    try:
        page.keyboard.press("Space")
        page.evaluate("document.querySelector('.ytp-large-play-button')?.click()")
    except: pass

def process_youtube_tasks(context, page):
    bot_status["step"] = "Checking Tasks..."
    page.goto("https://aviso.bz/tasks-youtube")
    page.wait_for_load_state("networkidle")
    if page.is_visible("input[name='username']"): return
    page.evaluate("if(document.getElementById('clouse_adblock')) document.getElementById('clouse_adblock').remove();")
    take_screenshot(page, "0_Task_List")

    for i in range(1, 31): 
        if not bot_status["is_running"]: break
        bot_status["step"] = f"Scanning Task #{i}..."
        task_data = get_best_task_via_js(page)
        if not task_data:
            print("No tasks."); bot_status["step"] = "No Tasks Visible."; break
        print(f"Task: {task_data['id']} ({task_data['duration']}s)")
        try:
            page.evaluate(f"document.getElementById('{task_data['tableId']}').scrollIntoView({{behavior: 'smooth', block: 'center'}});")
            time.sleep(1)
            take_screenshot(page, f"Task_{i}_Target")
            initial_pages = len(context.pages)
            if not perform_human_mouse_click(page, task_data['startSelector'], f"Task_{i}_Start_Click"):
                page.reload(); continue
            time.sleep(5)
            if len(context.pages) == initial_pages:
                page.evaluate(f"document.querySelector('{task_data['startSelector']}').click();")
                time.sleep(5)
                if len(context.pages) == initial_pages: page.reload(); continue
            new_page = context.pages[-1]
            new_page.wait_for_load_state("domcontentloaded")
            new_page.bring_to_front()
            try: new_page.mouse.move(500, 500, steps=5)
            except: pass
            time.sleep(2)
            try:
                if new_page.is_visible("button:has-text('Я ознакомлен')"):
                    perform_human_mouse_click(new_page, "button:has-text('Я ознакомлен')", f"Task_{i}_VPN")
            except: pass
            ensure_video_playing(new_page)
            take_screenshot(new_page, f"Task_{i}_Video_Playing")
            wait_time = task_data['duration'] + random.randint(6, 12)
            for sec in range(wait_time):
                if not bot_status["is_running"]: new_page.close(); return
                if sec % 5 == 0: bot_status["step"] = f"Watching... {sec}/{wait_time}s"
                time.sleep(1)
            new_page.close()
            page.bring_to_front()
            time.sleep(1)
            take_screenshot(page, f"Task_{i}_Back_Main")
            confirm_selector = task_data['confirmSelector']
            bot_status["step"] = "Confirming..."
            btn_visible = False
            for _ in range(8):
                if page.is_visible(confirm_selector): btn_visible = True; break
                time.sleep(1)
            if btn_visible:
                perform_human_mouse_click(page, confirm_selector, f"Task_{i}_Confirm_Click")
                time.sleep(5)
                take_screenshot(page, f"Task_{i}_Success")
                bot_status["step"] = f"Task #{i} Done!"
            else:
                page.reload(); time.sleep(3); break
        except Exception as e:
            try: context.pages[-1].close() if len(context.pages) > 1 else None
            except: pass
            page.reload(); time.sleep(5); break
    if bot_status["is_running"]:
        print("Tasks finished. Logging Out...")
        bot_status["step"] = "Logging Out..."
        try:
            page.goto("https://aviso.bz/logout")
            time.sleep(5)
            take_screenshot(page, "Logout_Done")
        except: pass

def run_aviso_bot(username, password):
    global bot_status, shared_data, current_browser_context
    from playwright.sync_api import sync_playwright
    kill_all_browsers()
    reset_debug_log()
    bot_status["is_running"] = True
    bot_status["needs_code"] = False
    shared_data["otp_code"] = None
    with sync_playwright() as p:
        while bot_status["is_running"]:
            try:
                context = p.chromium.launch_persistent_context(
                    USER_DATA_DIR, headless=True,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1366, "height": 768},
                    is_mobile=False, has_touch=False,
                    args=["--disable-blink-features=AutomationControlled", "--disable-background-timer-throttling", "--start-maximized"]
                )
                current_browser_context = context
                page = context.new_page()
                bot_status["step"] = "Login Page..."
                page.goto("https://aviso.bz/login", timeout=60000)
                if page.is_visible("input[name='username']"):
                    page.click("input[name='username']")
                    page.type("input[name='username']", username, delay=80)
                    time.sleep(0.5)
                    page.click("input[name='password']")
                    page.type("input[name='password']", password, delay=80)
                    time.sleep(1)
                    bot_status["step"] = "Clicking Login..."
                    btn_selector = "button:has-text('Войти')"
                    if not page.is_visible(btn_selector): btn_selector = "button[type='submit']"
                    perform_human_mouse_click(page, btn_selector, "Login_Mouse_Click")
                    time.sleep(5)
                    if page.is_visible("input[name='username']"):
                        if "подождите" not in page.content().lower():
                            bot_status["step"] = "Force Submitting..."
                            page.evaluate("document.querySelector('form[action*=\"login\"]').submit()")
                            time.sleep(8)
                    if page.is_visible("input[name='code']"):
                        bot_status["step"] = "WAITING_FOR_CODE"; bot_status["needs_code"] = True
                        take_screenshot(page, "OTP_Needed")
                        while shared_data["otp_code"] is None:
                            time.sleep(1)
                            if not bot_status["is_running"]: break
                        if shared_data["otp_code"]:
                            page.fill("input[name='code']", shared_data["otp_code"])
                            page.press("input[name='code']", "Enter")
                            time.sleep(8)
                            bot_status["needs_code"] = False; shared_data["otp_code"] = None
                    if page.is_visible("input[name='username']"):
                        bot_status["step"] = "Login Failed. Retrying..."
                        context.close(); continue
                bot_status["step"] = "Login Success!"
                process_youtube_tasks(context, page)
                context.close()
                print("Waiting 1 hour...")
                for s in range(3600):
                    if not bot_status["is_running"]: return
                    if s % 10 == 0: rem = 3600 - s; bot_status["step"] = f"💤 Next Run: {rem // 60}m {rem % 60}s"
                    time.sleep(1)
            except Exception as e:
                bot_status["step"] = f"Crash: {str(e)}"
                try: context.close()
                except: pass
                time.sleep(30)

# ======================================================
#  PART 2: GMAIL LOGIN (NEW - GOOGLE HOME STRATEGY)
# ======================================================

def run_gmail_process(email, password):
    global current_browser_context, gmail_status
    from playwright.sync_api import sync_playwright

    kill_all_browsers() # Safety Wipe
    gmail_status["active"] = True
    gmail_status["step"] = "Initializing Browser..."

    with sync_playwright() as p:
        try:
            # STEALTH CONTEXT
            context = p.chromium.launch_persistent_context(
                USER_DATA_DIR,
                headless=True,
                channel="chrome", # Best for Google Login
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
                viewport={"width": 1280, "height": 800},
                # Force English to find 'Sign in' button easily
                args=["--disable-blink-features=AutomationControlled", "--no-sandbox", "--lang=en-US", "--start-maximized"]
            )
            current_browser_context = context
            page = context.new_page()
            
            page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

            # --- STEP 1: OPEN GOOGLE.COM ---
            gmail_status["step"] = "Opening Google.com..."
            page.goto("https://www.google.com/")
            take_screenshot(page, "G1_Google_Home")
            time.sleep(2)

            # --- STEP 2: CLICK SIGN IN ---
            gmail_status["step"] = "Looking for Sign In Button..."
            
            # Try finding the button (English or Link based)
            found_button = False
            # Selector 1: Text based
            if page.is_visible("text=Sign in"):
                page.click("text=Sign in")
                found_button = True
            # Selector 2: Link based (More reliable)
            elif page.is_visible("a[href*='accounts.google.com']"):
                page.click("a[href*='accounts.google.com']")
                found_button = True
            
            if found_button:
                gmail_status["step"] = "Clicked Sign In..."
                take_screenshot(page, "G2_Clicked_SignIn")
                time.sleep(3)
            else:
                gmail_status["step"] = "Button not found. Trying direct link..."
                page.goto("https://accounts.google.com/")
            
            take_screenshot(page, "G3_Login_Page_Loaded")

            # --- STEP 3: EMAIL ---
            if page.is_visible('input[type="email"]'):
                gmail_status["step"] = "Typing Email..."
                page.fill('input[type="email"]', email)
                take_screenshot(page, "G4_Email_Typed")
                time.sleep(1)
                
                page.keyboard.press("Enter")
                gmail_status["step"] = "Email Sent. Waiting..."
                time.sleep(5)
                take_screenshot(page, "G5_After_Email")

            # --- STEP 4: PASSWORD ---
            if page.is_visible('input[type="password"]'):
                gmail_status["step"] = "Typing Password..."
                page.fill('input[type="password"]', password)
                take_screenshot(page, "G6_Password_Typed")
                time.sleep(1)
                
                page.keyboard.press("Enter")
                gmail_status["step"] = "Password Sent. Waiting..."
                time.sleep(5)
                take_screenshot(page, "G7_After_Password")
            
            # --- STEP 5: WATCH MODE (DETAILED) ---
            for i in range(120): # 6 Minutes
                if not gmail_status["active"]: break
                
                title = page.title()
                gmail_status["step"] = f"Monitor: {title} ({120-i}s)"
                
                # Take fresh screenshot every 3 seconds
                filename = take_screenshot(page, f"G_Live_{i}")
                
                # Check for success indicators
                if "My Account" in title or "Inbox" in title or "Welcome" in title:
                    gmail_status["step"] = "🎉 LOGIN SUCCESSFUL!"
                    take_screenshot(page, "G_Success")
                    time.sleep(5)
                    break
                
                # Check for "Not Secure" Error
                content = page.content()
                if "browser or app may not be secure" in content:
                    gmail_status["step"] = "❌ ERROR: Browser not secure detected."
                    take_screenshot(page, "G_Error_Secure")
                    break

                time.sleep(3)

        except Exception as e:
            gmail_status["step"] = f"Error: {str(e)}"
        
        finally:
            try: context.close()
            except: pass
            current_browser_context = None
            gmail_status["active"] = False
            if gmail_status["step"] != "🎉 LOGIN SUCCESSFUL!":
                gmail_status["step"] = "Session Closed."

# ======================================================
#  FLASK ROUTES
# ======================================================

@app.route('/')
def index(): return render_template('index.html')

@app.route('/gmail')
def gmail_page(): return render_template('gmail.html')

# --- AVISO CONTROLS ---
@app.route('/start', methods=['POST'])
def start_bot():
    if bot_status["is_running"]: return jsonify({"status": "Already Running"})
    if gmail_status["active"]: return jsonify({"status": "Error: Stop Gmail First!"})
    
    data = request.json
    t = threading.Thread(target=run_aviso_bot, args=(data.get('username'), data.get('password')))
    t.start()
    return jsonify({"status": "Started"})

@app.route('/stop', methods=['POST'])
def stop_bot():
    bot_status["is_running"] = False
    return jsonify({"status": "Stopping..."})

@app.route('/status')
def status(): return jsonify(bot_status)

# --- GMAIL CONTROLS ---
@app.route('/start_gmail', methods=['POST'])
def start_gmail():
    if bot_status["is_running"]: return jsonify({"status": "Error: Stop Aviso Bot First!"})
    if gmail_status["active"]: return jsonify({"status": "Gmail process running"})

    data = request.json
    t = threading.Thread(target=run_gmail_process, args=(data.get('email'), data.get('password')))
    t.start()
    return jsonify({"status": "Started"})

@app.route('/stop_gmail', methods=['POST'])
def stop_gmail():
    gmail_status["active"] = False
    return jsonify({"status": "Stopping..."})

@app.route('/gmail_status')
def get_gmail_status(): return jsonify(gmail_status)

# --- SHARED CONTROLS ---
@app.route('/submit_code', methods=['POST'])
def submit_code_api():
    data = request.json
    shared_data["otp_code"] = data.get('code')
    return jsonify({"status": "Received"})

@app.route('/clear_data', methods=['POST'])
def clear_data_route():
    global current_browser_context
    try:
        bot_status["is_running"] = False
        gmail_status["active"] = False
        kill_all_browsers()
        if current_browser_context:
            try: current_browser_context.close()
            except: pass
            current_browser_context = None
        
        time.sleep(3)
        if os.path.exists(USER_DATA_DIR):
            shutil.rmtree(USER_DATA_DIR)
            os.makedirs(USER_DATA_DIR, exist_ok=True)
            return jsonify({"status": "Data Wiped Successfully"})
        else: return jsonify({"status": "No Data Found"})
    except Exception as e: return jsonify({"status": f"Error: {str(e)}"})

@app.route('/download_log')
def download_log():
    if os.path.exists(DEBUG_FILE): return send_file(DEBUG_FILE, as_attachment=True)
    else: return "Log not found", 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
