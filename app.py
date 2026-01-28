import os
import time
import json
import threading
import random
import shutil
import datetime
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

def take_screenshot(page, name):
    try:
        timestamp = int(time.time())
        filename = f"{timestamp}_{name}.png"
        path = os.path.join(SCREENSHOT_DIR, filename)
        page.screenshot(path=path)
        bot_status["images"].append(filename)
    except: pass

# --- CONTINUOUS LOGGING ---
def save_debug_html(page, step_name):
    try:
        content = page.content()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        separator = f"""
        \n\n<div style="background:#111;color:#0f0;padding:15px;margin:20px;border:3px solid #0f0;font-family:monospace;">
            🖥️ DESKTOP ACTION: {step_name} <br> 🕒 TIME: {timestamp}
        </div>\n\n"""
        with open(DEBUG_FILE, "a", encoding="utf-8") as f:
            f.write(separator + content)
    except: pass

def reset_debug_log():
    try:
        with open(DEBUG_FILE, "w", encoding="utf-8") as f:
            f.write("<h1>💻 AVISO DESKTOP BOT STARTED</h1>")
    except: pass

# --- DESKTOP STEALTH (Windows 11 Style) ---
def apply_desktop_stealth(page):
    try:
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        # Fake Plugins to look like a real PC
        page.add_init_script("""
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            Object.defineProperty(navigator, 'languages', {get: () => ['ru-RU', 'ru', 'en-US', 'en']});
        """)
        
        # Heavy Desktop Headers
        page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
            "sec-ch-ua": '"Not(A:Brand";v="99", "Google Chrome";v="133", "Chromium";v="133"',
            "sec-ch-ua-mobile": "?0", # Important: Not Mobile
            "sec-ch-ua-platform": '"Windows"',
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Upgrade-Insecure-Requests": "1"
        })
    except: pass

# --- JS SCANNER ---
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
                id: idPart,
                duration: duration,
                tableId: table.id,
                startSelector: '#link_ads_start_' + idPart,
                confirmSelector: '#ads_btn_confirm_' + idPart
            };
        }
        return null; 
    }""")

# --- MOUSE CLICK (Human Simulation) ---
def perform_mouse_click(page, selector, screenshot_name):
    try:
        if not page.is_visible(selector): return False
        box = page.locator(selector).bounding_box()
        if box:
            # Calculate Center
            x = box['x'] + box['width'] / 2 + random.uniform(-10, 10)
            y = box['y'] + box['height'] / 2 + random.uniform(-5, 5)
            
            print(f"Mouse moving to: {x:.0f}, {y:.0f}")
            
            # 1. VISUAL RED DOT (Cursor Indicator)
            page.evaluate(f"""() => {{
                const d = document.createElement('div');
                d.id = 'mouse-dot';
                d.style.position = 'fixed'; 
                d.style.left = '{x}px'; d.style.top = '{y}px';
                d.style.width = '12px'; d.style.height = '12px';
                d.style.background = 'transparent';
                d.style.border = '2px solid red';
                d.style.borderRadius = '50%';
                d.style.zIndex = '9999999';
                d.style.pointerEvents = 'none';
                document.body.appendChild(d);
            }}""")
            
            # 2. REAL MOUSE MOVEMENT (Hover effect)
            page.mouse.move(x, y, steps=10) # Smooth move
            time.sleep(0.3)
            
            take_screenshot(page, screenshot_name)
            
            # 3. CLICK
            page.mouse.click(x, y)
            
            # Cleanup
            page.evaluate("if(document.getElementById('mouse-dot')) document.getElementById('mouse-dot').remove();")
            return True
    except Exception as e: print(f"Mouse Error: {e}")
    return False

# --- AUTO PLAY (Desktop) ---
def ensure_video_playing(page):
    try:
        # On Desktop, spacebar often toggles play
        page.keyboard.press("Space")
        # Or click the big button
        page.evaluate("""() => {
            const btn = document.querySelector('.ytp-large-play-button');
            if(btn) btn.click();
        }""")
    except: pass

# --- PROCESS TASKS ---
def process_youtube_tasks(context, page):
    bot_status["step"] = "Checking Tasks..."
    page.goto("https://aviso.bz/tasks-youtube")
    page.wait_for_load_state("networkidle")
    
    if page.is_visible("input[name='username']"): return

    page.evaluate("if(document.getElementById('clouse_adblock')) document.getElementById('clouse_adblock').remove();")
    save_debug_html(page, "Task_List_Page")
    take_screenshot(page, "0_Task_List")

    for i in range(1, 31): 
        if not bot_status["is_running"]: break
        
        bot_status["step"] = f"Task #{i} Scan..."
        task_data = get_best_task_via_js(page)
        
        if not task_data:
            print("No tasks found.")
            save_debug_html(page, "No_Tasks")
            bot_status["step"] = "No Tasks Visible."
            break
            
        print(f"Task: {task_data['id']} ({task_data['duration']}s)")
        
        try:
            # Scroll nicely like a user
            page.evaluate(f"document.getElementById('{task_data['tableId']}').scrollIntoView({{behavior: 'smooth', block: 'center'}});")
            time.sleep(1)
            take_screenshot(page, f"Task_{i}_Target")

            # --- MOUSE CLICK START ---
            initial_pages = len(context.pages)
            if not perform_mouse_click(page, task_data['startSelector'], f"Task_{i}_Click_Start"):
                page.reload()
                continue
            
            time.sleep(5)
            if len(context.pages) == initial_pages:
                # Retry with JS if mouse fails
                page.evaluate(f"document.querySelector('{task_data['startSelector']}').click();")
                time.sleep(5)
                if len(context.pages) == initial_pages:
                    page.reload()
                    continue

            new_page = context.pages[-1]
            apply_desktop_stealth(new_page) 
            new_page.wait_for_load_state("domcontentloaded")
            new_page.bring_to_front()
            
            # Mouse Jiggle (Anti-Idle)
            try: new_page.mouse.move(500, 500); new_page.mouse.move(600, 400)
            except: pass

            time.sleep(2)
            try:
                # Desktop VPN warning might be different, but keeping check
                if new_page.is_visible("button:has-text('Я ознакомлен')"):
                    perform_mouse_click(new_page, "button:has-text('Я ознакомлен')", f"Task_{i}_VPN")
            except: pass

            ensure_video_playing(new_page)
            take_screenshot(new_page, f"Task_{i}_Video")
            
            wait_time = task_data['duration'] + random.randint(5, 10)
            for sec in range(wait_time):
                if not bot_status["is_running"]: 
                    new_page.close()
                    return
                if sec % 5 == 0: 
                    bot_status["step"] = f"Watching... {sec}/{wait_time}s"
                    # Small mouse movements
                    try: new_page.mouse.move(random.randint(200,800), random.randint(200,600))
                    except: pass
                time.sleep(1)

            new_page.close()
            page.bring_to_front()
            time.sleep(1)
            take_screenshot(page, f"Task_{i}_Back")

            confirm_selector = task_data['confirmSelector']
            bot_status["step"] = "Confirming..."
            
            btn_visible = False
            for _ in range(8):
                if page.is_visible(confirm_selector):
                    btn_visible = True
                    break
                time.sleep(1)
            
            if btn_visible:
                perform_mouse_click(page, confirm_selector, f"Task_{i}_Click_Confirm")
                time.sleep(5)
                take_screenshot(page, f"Task_{i}_Success")
                bot_status["step"] = f"Task #{i} Done!"
                save_debug_html(page, f"Task_{i}_Success")
            else:
                page.reload()
                time.sleep(3)
                break

        except Exception as e:
            print(f"Error: {e}")
            try: context.pages[-1].close() if len(context.pages) > 1 else None
            except: pass
            page.reload()
            time.sleep(5)
            break

    if bot_status["is_running"]:
        page.goto("https://aviso.bz/logout")

# --- MAIN RUNNER ---
def run_infinite_loop(username, password):
    global bot_status, shared_data, current_browser_context
    from playwright.sync_api import sync_playwright

    reset_debug_log()
    bot_status["is_running"] = True
    bot_status["needs_code"] = False
    shared_data["otp_code"] = None

    with sync_playwright() as p:
        while bot_status["is_running"]:
            try:
                # --- DESKTOP CONFIGURATION ---
                context = p.chromium.launch_persistent_context(
                    USER_DATA_DIR,
                    headless=True,
                    # Windows 10 User Agent
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.0.0 Safari/537.36",
                    viewport={"width": 1920, "height": 1080}, # FULL HD
                    device_scale_factor=1,
                    is_mobile=False, # IMPORTANT: PC Mode
                    has_touch=False, # IMPORTANT: Mouse Mode
                    args=[
                        "--disable-blink-features=AutomationControlled",
                        "--disable-background-timer-throttling",
                        "--disable-renderer-backgrounding",
                        "--start-maximized", # Full Window
                        "--lang=ru-RU,ru"
                    ]
                )
                current_browser_context = context
                
                page = context.new_page()
                apply_desktop_stealth(page)
                
                bot_status["step"] = "Opening Login (PC)..."
                page.goto("https://aviso.bz/login", timeout=60000)
                save_debug_html(page, "PC_Login_Page")
                
                if page.is_visible("input[name='username']"):
                    # Type credentials
                    page.click("input[name='username']")
                    page.type("input[name='username']", username, delay=100)
                    time.sleep(0.5)
                    page.click("input[name='password']")
                    page.type("input[name='password']", password, delay=100)
                    time.sleep(1)

                    bot_status["step"] = "Pressing Enter..."
                    page.press("input[name='password']", "Enter")
                    
                    time.sleep(5)
                    take_screenshot(page, "Login_Attempt")
                    save_debug_html(page, "After_Login_Enter")

                    # Check for loading
                    try:
                        if "подождите" in page.content().lower():
                            bot_status["step"] = "Loading... (Wait 5s)"
                            time.sleep(5)
                    except: pass

                    # OTP Logic
                    if page.is_visible("input[name='code']"):
                        bot_status["step"] = "WAITING_FOR_CODE"
                        bot_status["needs_code"] = True
                        take_screenshot(page, "Code_Required")
                        
                        while shared_data["otp_code"] is None:
                            time.sleep(1)
                            if not bot_status["is_running"]: break
                        
                        if shared_data["otp_code"]:
                            page.fill("input[name='code']", shared_data["otp_code"])
                            page.press("input[name='code']", "Enter")
                            time.sleep(8)
                            bot_status["needs_code"] = False
                            shared_data["otp_code"] = None

                    # If still on login, click button
                    if page.is_visible("input[name='username']") and not page.is_visible("input[name='code']"):
                         print("Clicking Button...")
                         btn = page.locator("button:has-text('Войти')")
                         if btn.count() > 0:
                             perform_mouse_click(page, "button:has-text('Войти')", "Login_Click")
                         else:
                             page.locator("button[type='submit']").click()
                         
                         time.sleep(5)
                         if page.is_visible("input[name='username']"):
                             print("Login failed.")
                             context.close()
                             continue
                
                bot_status["step"] = "Login Success!"
                take_screenshot(page, "Login_Success")
                process_youtube_tasks(context, page)
                
                context.close()
                print("Waiting 1 hour...")
                for s in range(3600):
                    if not bot_status["is_running"]: return
                    if s % 10 == 0: 
                        rem = 3600 - s
                        bot_status["step"] = f"💤 Next Run: {rem // 60}m {rem % 60}s"
                    time.sleep(1)

            except Exception as e:
                bot_status["step"] = f"Error: {str(e)}"
                time.sleep(30)

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
    if bot_status["is_running"]: return jsonify({"status": "Already Running"})
    data = request.json
    t = threading.Thread(target=run_infinite_loop, args=(data.get('username'), data.get('password')))
    t.start()
    return jsonify({"status": "Started"})

@app.route('/stop', methods=['POST'])
def stop_bot():
    bot_status["is_running"] = False
    return jsonify({"status": "Stopping..."})

@app.route('/clear_data', methods=['POST'])
def clear_data_route():
    global current_browser_context
    try:
        bot_status["is_running"] = False
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

@app.route('/status')
def status(): return jsonify(bot_status)

@app.route('/download_log')
def download_log():
    if os.path.exists(DEBUG_FILE): return send_file(DEBUG_FILE, as_attachment=True)
    else: return "Log not found", 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
