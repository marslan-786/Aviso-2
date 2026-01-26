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

def take_screenshot(page, name):
    try:
        timestamp = int(time.time())
        filename = f"{timestamp}_{name}.png"
        path = os.path.join(SCREENSHOT_DIR, filename)
        page.screenshot(path=path)
        bot_status["images"].append(filename)
    except Exception as e:
        print(f"Screenshot failed: {e}")

# --- MOBILE STEALTH (Redmi 14C) ---
def apply_mobile_stealth(page):
    try:
        page.add_init_script("""
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 4 });
            Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 5 });
            window.ontouchstart = true;
            
            navigator.getBattery = async () => {
                return {
                    charging: false,
                    chargingTime: Infinity,
                    dischargingTime: 18420,
                    level: 0.85,
                    addEventListener: function() {},
                    removeEventListener: function() {}
                }
            };
        """)
    except: pass

# --- JAVASCRIPT SCANNER ---
def get_best_task_via_js(page):
    return page.evaluate("""() => {
        const tasks = Array.from(document.querySelectorAll('table[id^="ads-link-"], div[id^="ads-link-"]'));
        const data = tasks.map(task => {
            const idPart = task.id.replace('ads-link-', '');
            const isVideo = task.querySelector('.ybprosm') !== null;
            if (!isVideo) return null;

            const timerId = 'timer_ads_' + idPart;
            const priceEl = task.querySelector('span[title="Стоимость просмотра"], .price-text');
            const price = priceEl ? parseFloat(priceEl.innerText) : 0;

            return {
                id: idPart,
                price: price,
                timerId: timerId,
                tableId: task.id,
                startSelector: '#link_ads_start_' + idPart,
                confirmSelector: '#ads_btn_confirm_' + idPart,
                errorSelector: '#btn_error_view_' + idPart
            };
        }).filter(item => item !== null);

        data.sort((a, b) => b.price - a.price);
        return data.length > 0 ? data[0] : null;
    }""")

# --- NEW: LOGIN HANDLER ---
def handle_login_flow(page, username, password):
    print("Performing Login...")
    bot_status["step"] = "Logging In..."
    
    # فل ان پٹ
    page.fill("input[name='username']", username)
    page.fill("input[name='password']", password)
    
    # موبائل پر کبھی کبھی انٹر کام نہیں کرتا، بٹن ٹیپ کریں
    submit_btn = page.locator("button[type='submit'], button:has-text('Войти'), button:has-text('Login')")
    if submit_btn.count() > 0:
        submit_btn.first.tap()
    else:
        page.locator("input[name='password']").press("Enter")
    
    time.sleep(5)

    # 2FA Check
    if page.is_visible("input[name='code']"):
        bot_status["step"] = "WAITING_FOR_CODE"
        bot_status["needs_code"] = True
        take_screenshot(page, "Login_Code_Required")
        
        while shared_data["otp_code"] is None:
            time.sleep(2)
            if not bot_status["is_running"]: return False
        
        page.fill("input[name='code']", shared_data["otp_code"])
        
        # کوڈ کے بعد والا بٹن
        code_btn = page.locator("button:has-text('Войти'), button:has-text('Login'), input[type='submit']")
        if code_btn.count() > 0:
            code_btn.first.tap()
        else:
            page.locator("input[name='code']").press("Enter")
            
        time.sleep(8)
        shared_data["otp_code"] = None # Reset code
        bot_status["needs_code"] = False
        
    return True

# --- PROCESS TASKS ---
def process_youtube_tasks(context, page, username, password):
    bot_status["step"] = "Opening Task List..."
    page.goto("https://aviso.bz/tasks-youtube")
    page.wait_for_load_state("networkidle")
    
    page.evaluate("if(document.getElementById('clouse_adblock')) document.getElementById('clouse_adblock').remove();")
    
    # --- CHECK FOR TASKS ---
    # اگر ٹاسک نہ ملیں تو 2 بار ریفریش کر کے دیکھو
    tasks_found = False
    for _ in range(3):
        task_check = get_best_task_via_js(page)
        if task_check:
            tasks_found = True
            break
        print("No tasks found, scrolling/refreshing...")
        page.mouse.wheel(0, 1000)
        time.sleep(2)
    
    # --- LOGOUT TRIGGER ---
    if not tasks_found:
        print("⛔ NO TASKS AVAILABLE. Logging out to switch account...")
        bot_status["step"] = "No Tasks! Logging Out..."
        take_screenshot(page, "No_Tasks_Proof")
        
        # Direct Logout Link
        page.goto("https://aviso.bz/logout")
        time.sleep(5)
        
        # Check if logout successful (should see login form)
        if page.is_visible("input[name='username']"):
            print("Logout successful. Re-logging in with provided credentials...")
            handle_login_flow(page, username, password)
            # لاگ ان کے بعد دوبارہ خود کو کال کریں (Recursion)
            process_youtube_tasks(context, page, username, password)
        return

    # --- IF TASKS FOUND, DO THEM ---
    take_screenshot(page, "Tasks_Found")
    
    for i in range(1, 25): 
        if not bot_status["is_running"]: break
        
        task_data = get_best_task_via_js(page)
        if not task_data:
            print("Tasks finished for this session.")
            break
            
        bot_status["step"] = f"Task #{i} Started..."
        print(f"Doing Task ID: {task_data['id']}")

        try:
            # Highlight
            page.evaluate(f"document.getElementById('{task_data['tableId']}').style.border = '4px solid red';")
            page.evaluate(f"document.getElementById('{task_data['tableId']}').scrollIntoView({{block: 'center'}});")
            time.sleep(1)
            take_screenshot(page, f"Task_{i}_Start")

            start_selector = task_data['startSelector']
            
            with context.expect_page() as new_page_info:
                page.tap(start_selector)
            
            new_page = new_page_info.value
            apply_mobile_stealth(new_page)
            new_page.wait_for_load_state("domcontentloaded")
            new_page.bring_to_front()
            
            # --- Sync Watch Logic ---
            time.sleep(3)
            take_screenshot(new_page, f"Task_{i}_Video")
            
            max_wait = 90
            timer_finished = False
            
            for tick in range(max_wait):
                if not bot_status["is_running"]: 
                    new_page.close()
                    return
                
                # Mobile Interaction
                try: new_page.touchscreen.tap(200, 300)
                except: pass

                status_check = page.evaluate(f"""() => {{
                    const btn = document.querySelector('{task_data['confirmSelector']}');
                    const err = document.querySelector('{task_data['errorSelector']}');
                    if (err && err.offsetParent !== null) return {{ status: 'error' }};
                    if (btn && btn.offsetParent !== null) return {{ status: 'done' }};
                    return {{ status: 'waiting' }};
                }}""")

                if status_check['status'] == 'error': break 
                if status_check['status'] == 'done':
                    timer_finished = True
                    break
                time.sleep(1)
                if tick % 5 == 0: bot_status["step"] = f"Watching... {tick}s"

            new_page.close()
            page.bring_to_front()
            
            if timer_finished:
                bot_status["step"] = "Confirming..."
                page.tap(task_data['confirmSelector'])
                time.sleep(4)
                take_screenshot(page, f"Task_{i}_Done")
                bot_status["step"] = f"Task #{i} Complete!"
            else:
                page.reload()

        except Exception as e:
            print(f"Task Error: {e}")
            try: new_page.close() 
            except: pass
            page.reload()
            time.sleep(5)

# --- MAIN RUNNER ---
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
                # REDMI 14C Specs
                user_agent="Mozilla/5.0 (Linux; Android 14; 2409BRN2CG) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.200 Mobile Safari/537.36",
                viewport={"width": 412, "height": 915},
                device_scale_factor=2.625,
                is_mobile=True,
                has_touch=True,
                args=[
                    "--lang=en-US",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled"
                ]
            )
            
            page = context.new_page()
            apply_mobile_stealth(page)
            
            bot_status["step"] = "Checking Session..."
            page.goto("https://aviso.bz/tasks-youtube", timeout=60000)
            page.wait_for_load_state("networkidle")
            
            # اگر لاگ ان نہیں ہے تو لاگ ان کرو
            if "login" in page.url or page.is_visible("input[name='username']"):
                handle_login_flow(page, username, password)
            
            # ٹاسک پروسیسنگ شروع کریں (یہ فنکشن اب خود ہی لاگ آؤٹ/لاگ ان سنبھالے گا)
            process_youtube_tasks(context, page, username, password)

        except Exception as e:
            bot_status["step"] = f"Error: {str(e)}"
            print(f"Critical: {e}")
            try: take_screenshot(page, "critical_error")
            except: pass
        
        finally:
            try: context.close()
            except: pass
            bot_status["is_running"] = False

# --- ROUTES ---
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