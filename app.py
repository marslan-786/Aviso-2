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

# --- MOBILE STEALTH INJECTION (Redmi 14C Identity) ---
def apply_mobile_stealth(page):
    """
    یہ فنکشن براؤزر کو بتائے گا کہ میں ایک اصلی موبائل ہوں (Redmi 14C).
    """
    try:
        # 1. Fake Hardware (Concurrency & Memory)
        page.add_init_script("""
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
            Object.defineProperty(navigator, 'deviceMemory', { get: () => 4 });
        """)

        # 2. Fake Battery (Mobile Feature)
        page.add_init_script("""
            navigator.getBattery = async () => {
                return {
                    charging: false,
                    chargingTime: Infinity,
                    dischargingTime: 18420,
                    level: 0.85, # 85% Battery
                    addEventListener: function() {},
                    removeEventListener: function() {}
                }
            };
        """)

        # 3. Touch Points (کیونکہ موبائل پر ماؤس نہیں، انگلی ہوتی ہے)
        page.add_init_script("""
            Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 5 });
            window.ontouchstart = true;
        """)

        # 4. Fake GPU (Mali-G52 / PowerVR - Typical Mobile GPU)
        page.add_init_script("""
            const getParameter = WebGLRenderingContext.prototype.getParameter;
            WebGLRenderingContext.prototype.getParameter = function(parameter) {
                if (parameter === 37445) return 'Google Inc. (ARM)'; 
                if (parameter === 37446) return 'Android Emulator OpenGL ES Translator (Mali-G57 MC2)'; 
                return getParameter(parameter);
            };
        """)
        print("Redmi 14C Identity Injected Successfully!")
    except Exception as e:
        print(f"Stealth injection failed: {e}")

# --- JAVASCRIPT INTELLIGENCE (Same Logic, Works on Mobile Layout) ---
def get_best_task_via_js(page):
    return page.evaluate("""() => {
        // موبائل ویو میں ٹیبل کا سٹرکچر تھوڑا مختلف ہو سکتا ہے، ہم فلیکسیبل سلیکٹر استعمال کریں گے
        const tasks = Array.from(document.querySelectorAll('table[id^="ads-link-"], div[id^="ads-link-"]'));
        
        const data = tasks.map(task => {
            const idPart = task.id.replace('ads-link-', '');
            
            // چیک کریں کہ یہ ویڈیو ہے
            const isVideo = task.querySelector('.ybprosm') !== null;
            if (!isVideo) return null;

            const timerId = 'timer_ads_' + idPart;
            // موبائل میں کبھی کبھی ٹائٹل غائب ہوتا ہے، احتیاط
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

# --- PROCESS LOGIC ---
def process_youtube_tasks(context, page):
    bot_status["step"] = "Opening Mobile Tasks..."
    # موبائل لنک وہی ہے، لیکن موبائل UA کی وجہ سے لے آؤٹ موبائل والا کھلے گا
    page.goto("https://aviso.bz/tasks-youtube")
    
    # موبائل نیٹ ورک سلو ہو سکتا ہے
    page.wait_for_load_state("networkidle", timeout=60000)
    
    # Remove AdBlock Warning
    page.evaluate("if(document.getElementById('clouse_adblock')) document.getElementById('clouse_adblock').remove();")
    
    take_screenshot(page, "0_Mobile_View_Loaded")

    for i in range(1, 25): 
        if not bot_status["is_running"]: break
        
        bot_status["step"] = f"Scanning Task #{i}..."
        task_data = get_best_task_via_js(page)
        
        if not task_data:
            print("No video tasks found. Scrolling down...")
            # موبائل پر لوڈ کرنے کے لیے اسکرول کرنا پڑتا ہے
            page.mouse.wheel(0, 500)
            time.sleep(3)
            # دوبارہ ٹرائی کریں
            task_data = get_best_task_via_js(page)
            if not task_data:
                print("Still nothing. Reloading.")
                page.reload()
                time.sleep(5)
                continue
            
        print(f"TASK FOUND: ID={task_data['id']}")
        bot_status["step"] = f"Task #{i}: ID {task_data['id']} started"

        try:
            # Highlight Target
            page.evaluate(f"document.getElementById('{task_data['tableId']}').style.border = '4px solid red';")
            page.evaluate(f"document.getElementById('{task_data['tableId']}').scrollIntoView({{block: 'center'}});")
            time.sleep(1)
            take_screenshot(page, f"Task_{i}_0_Target_Locked")

            # --- ACTION 1: TAP START (Mobile uses Tap) ---
            start_selector = task_data['startSelector']
            
            with context.expect_page() as new_page_info:
                # Playwright میں tap موبائل کے لیے بہتر ہے
                page.tap(start_selector)
            
            new_page = new_page_info.value
            
            # نئے ٹیب کو بھی موبائل بناؤ
            apply_mobile_stealth(new_page)
            
            new_page.wait_for_load_state("domcontentloaded")
            
            # --- ACTION 2: SYNC WATCHING ---
            new_page.bring_to_front()
            print("Mobile Video tab opened. Syncing...")
            
            time.sleep(3)
            take_screenshot(new_page, f"Task_{i}_1_Video_Playing_Proof")
            take_screenshot(page, f"Task_{i}_2_Main_Page_Check")

            max_wait = 90
            timer_finished = False
            
            for tick in range(max_wait):
                if not bot_status["is_running"]: 
                    new_page.close()
                    return
                
                # Mobile Scroll/Touch Simulation
                try:
                    # موبائل پر ماؤس موو نہیں ہوتا، ٹچ اسکرول ہوتا ہے
                    new_page.touchscreen.tap(200, 300)
                except: pass

                status_check = page.evaluate(f"""() => {{
                    const btn = document.querySelector('{task_data['confirmSelector']}');
                    const err = document.querySelector('{task_data['errorSelector']}');
                    
                    if (err && err.offsetParent !== null) return {{ status: 'error', text: err.innerText }};
                    if (btn && btn.offsetParent !== null) return {{ status: 'done' }};
                    return {{ status: 'waiting' }};
                }}""")

                if status_check['status'] == 'error':
                    take_screenshot(page, f"Task_{i}_ErrorMsg")
                    break 
                
                if status_check['status'] == 'done':
                    timer_finished = True
                    break
                
                time.sleep(1)
                if tick % 5 == 0: bot_status["step"] = f"Watching... {tick}s elapsed"

            # --- ACTION 3: CLOSE & CONFIRM ---
            new_page.close()
            page.bring_to_front()
            
            if timer_finished:
                bot_status["step"] = "Tapping Confirm..."
                take_screenshot(page, f"Task_{i}_3_Confirm_Ready")
                
                page.tap(task_data['confirmSelector'])
                time.sleep(4)
                
                take_screenshot(page, f"Task_{i}_4_Success")
                bot_status["step"] = f"Task #{i} Completed!"
            else:
                bot_status["step"] = "Task Timeout/Skipped"
                page.reload()

        except Exception as e:
            print(f"Task failed: {e}")
            try: new_page.close() 
            except: pass
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
            # --- REDMI 14C EMULATION ---
            # Redmi 14C Viewport: 412x915 (Approx)
            # User Agent: Android 14 Chrome
            
            context = p.chromium.launch_persistent_context(
                USER_DATA_DIR,
                headless=True,
                user_agent="Mozilla/5.0 (Linux; Android 14; 2409BRN2CG) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.200 Mobile Safari/537.36",
                viewport={"width": 412, "height": 915},
                device_scale_factor=2.625, # High DPI Screen
                is_mobile=True, # ویب سائٹ کو موبائل ورژن دکھانے پر مجبور کریں
                has_touch=True, # ٹچ ان ایبل کریں
                
                args=[
                    "--lang=en-US",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled"
                ]
            )
            
            page = context.new_page()
            apply_mobile_stealth(page) # انجیکشن لگائیں
            
            bot_status["step"] = "Opening Mobile Site..."
            page.goto("https://aviso.bz/tasks-youtube", timeout=60000)
            page.wait_for_load_state("networkidle")
            
            # لاگ ان چیک
            if "login" in page.url:
                print("Logging in on Mobile...")
                page.goto("https://aviso.bz/login")
                
                # موبائل پر ان پٹ فیلڈز تھوڑے مختلف ہو سکتے ہیں، لیکن name وہی رہتا ہے
                page.fill("input[name='username']", username)
                page.fill("input[name='password']", password)
                page.tap("button[type='submit']") # Click نہیں، Tap
                time.sleep(5)

                # اگر لاگ ان نہ ہو تو انٹر ٹرائی کریں
                if "login" in page.url:
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
                    page.tap("button:has-text('Войти')") # یا انٹر
                    time.sleep(8)
            
            take_screenshot(page, "Mobile_Dashboard_Ready")
            process_youtube_tasks(context, page)

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