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
PROXY_FILE = "proxy_config.txt"

# --- Shared State ---
shared_data = {"otp_code": None}
current_browser_context = None

bot_status = {
    "step": "Idle",
    "images": [],
    "is_running": False,
    "needs_code": False,
    "proxy_status": "Direct IP"
}

# --- HELPER FUNCTIONS ---
def get_proxy_config():
    if os.path.exists(PROXY_FILE):
        try:
            with open(PROXY_FILE, "r") as f:
                proxy_str = f.read().strip()
                if not proxy_str: return None
                parts = proxy_str.split(":")
                proxy_dict = {"server": f"http://{parts[0]}:{parts[1]}"}
                if len(parts) == 4:
                    proxy_dict["username"] = parts[2]
                    proxy_dict["password"] = parts[3]
                return proxy_dict
        except: return None
    return None

def kill_all_browsers():
    try:
        subprocess.run(["pkill", "-9", "chrome"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["pkill", "-9", "chromium"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
    except: pass

def take_screenshot(page, name):
    try:
        timestamp = int(time.time())
        filename = f"{timestamp}_{name}.png"
        path = os.path.join(SCREENSHOT_DIR, filename)
        page.screenshot(path=path)
        bot_status["images"].append(filename)
    except: pass

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
            f.write("<h1>🖱️ AVISO MULTI-TASK BOT</h1>")
    except: pass

# --- HUMAN MOUSE SIMULATION ---
def perform_human_mouse_click(page, selector, screenshot_name):
    try:
        if not page.is_visible(selector): return False
        box = page.locator(selector).bounding_box()
        if box:
            x = box['x'] + box['width'] / 2 + random.uniform(-15, 15)
            y = box['y'] + box['height'] / 2 + random.uniform(-5, 5)
            
            # Move
            page.mouse.move(x, y, steps=15) 
            time.sleep(0.3)

            # Red Dot
            page.evaluate(f"""() => {{
                const d = document.createElement('div'); d.id = 'click-dot'; d.style.position = 'fixed'; 
                d.style.left = '{x-5}px'; d.style.top = '{y-5}px'; d.style.width = '10px'; d.style.height = '10px';
                d.style.background = 'red'; d.style.border = '2px solid white'; d.style.borderRadius = '50%'; d.style.zIndex = '9999999';
                document.body.appendChild(d);
            }}""")
            
            take_screenshot(page, screenshot_name)
            
            # Click
            page.mouse.down()
            time.sleep(random.uniform(0.05, 0.15))
            page.mouse.up()
            
            time.sleep(0.5)
            page.evaluate("if(document.getElementById('click-dot')) document.getElementById('click-dot').remove();")
            return True
    except Exception as e:
        print(f"Mouse Error: {e}")
    return False

# --- FORCE VIDEO PLAY ---
def ensure_video_playing(page):
    try:
        if page.is_visible(".ytp-large-play-button"):
            perform_human_mouse_click(page, ".ytp-large-play-button", "Play_RedButton")
            time.sleep(2)
            return

        viewport = page.viewport_size
        if viewport:
            cx = viewport['width'] / 2
            cy = viewport['height'] / 2
            page.mouse.click(cx, cy)
            time.sleep(1)
        
        page.keyboard.press("Space")
    except: pass

# ==========================================
#  MODULE 1: YOUTUBE TASKS
# ==========================================
def get_youtube_tasks(page):
    return page.evaluate("""() => {
        const tables = Array.from(document.querySelectorAll('table[id^="ads-link-"]'));
        for (let table of tables) {
            if (table.offsetParent === null) continue;
            if (!table.querySelector('.ybprosm')) continue;
            const idPart = table.id.replace('ads-link-', '');
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

def process_youtube_tasks(context, page):
    print("📺 Starting YouTube Module...")
    bot_status["step"] = "Opening YouTube Tasks..."
    page.goto("https://aviso.bz/tasks-youtube")
    page.wait_for_load_state("networkidle")
    
    if page.is_visible("input[name='username']"): return False

    page.evaluate("if(document.getElementById('clouse_adblock')) document.getElementById('clouse_adblock').remove();")
    
    tasks_done = 0
    for i in range(1, 15): # Max 15 per cycle
        if not bot_status["is_running"]: break
        
        task_data = get_youtube_tasks(page)
        if not task_data:
            print("No YouTube tasks found.")
            break
            
        print(f"YT Task: {task_data['id']} ({task_data['duration']}s)")
        bot_status["step"] = f"YouTube #{i}: {task_data['duration']}s"
        
        try:
            page.evaluate(f"document.getElementById('{task_data['tableId']}').scrollIntoView({{behavior: 'smooth', block: 'center'}});")
            time.sleep(1)
            
            # Start
            initial_pages = len(context.pages)
            if not perform_human_mouse_click(page, task_data['startSelector'], f"YT_{i}_Start"):
                page.reload(); continue
            
            time.sleep(5)
            if len(context.pages) == initial_pages:
                page.evaluate(f"document.querySelector('{task_data['startSelector']}').click();")
                time.sleep(5)
                if len(context.pages) == initial_pages: page.reload(); continue

            new_page = context.pages[-1]
            new_page.wait_for_load_state("domcontentloaded")
            new_page.bring_to_front()
            time.sleep(2)

            # Handle VPN/Confirm Button on Video Page
            try:
                if new_page.is_visible("button:has-text('Я ознакомлен')"):
                    new_page.click("button:has-text('Я ознакомлен')")
            except: pass

            ensure_video_playing(new_page)
            
            # 10s Proof
            bot_status["step"] = "Watching (10s proof)..."
            time.sleep(10)
            take_screenshot(new_page, f"YT_{i}_Proof_10s")
            
            # Remaining Wait
            remaining = (task_data['duration'] + random.randint(2, 5)) - 10
            if remaining < 0: remaining = 0
            time.sleep(remaining)

            new_page.close()
            page.bring_to_front()
            time.sleep(1)
            
            # Confirm
            confirm_selector = task_data['confirmSelector']
            bot_status["step"] = "Confirming YT..."
            if page.is_visible(confirm_selector):
                perform_human_mouse_click(page, confirm_selector, f"YT_{i}_Confirm")
                time.sleep(4)
                take_screenshot(page, f"YT_{i}_Done")
                tasks_done += 1
            else:
                page.reload(); time.sleep(3)

        except Exception as e:
            print(f"YT Error: {e}")
            try: context.pages[-1].close() if len(context.pages) > 1 else None
            except: pass
            page.reload(); time.sleep(3)
            
    return tasks_done > 0

# ==========================================
#  MODULE 2: SURFING TASKS (NEW)
# ==========================================
def get_surfing_tasks(page):
    # یہ فنکشن HTML کو دیکھ کر بنایا گیا ہے
    # Button Class: .start-surfing-btn
    return page.evaluate("""() => {
        const buttons = Array.from(document.querySelectorAll('.start-surfing-btn'));
        for (let btn of buttons) {
            // Check visibility
            if (btn.offsetParent === null) continue;
            
            const id = btn.getAttribute('data-surfing-id');
            const timer = parseInt(btn.getAttribute('data-timer')) || 20;
            const url = btn.getAttribute('data-url');
            
            return {
                id: id,
                timer: timer,
                url: url,
                startSelector: `a[data-surfing-id="${id}"]`,
                confirmSelector: `#serf_btn_confirm_${id}` // Hidden initially
            };
        }
        return null;
    }""")

def process_surfing_tasks(context, page):
    print("🏄 Starting Surfing Module...")
    bot_status["step"] = "Switching to Surfing..."
    page.goto("https://aviso.bz/tasks-surf")
    page.wait_for_load_state("networkidle")
    
    if page.is_visible("input[name='username']"): return False

    tasks_done = 0
    for i in range(1, 20): # Max 20 Surfs
        if not bot_status["is_running"]: break
        
        task = get_surfing_tasks(page)
        if not task:
            print("No Surfing tasks.")
            bot_status["step"] = "No Surf Tasks."
            break
            
        print(f"Surf Task: {task['id']} ({task['timer']}s)")
        bot_status["step"] = f"Surfing #{i}: {task['timer']}s"
        
        try:
            page.evaluate(f"document.querySelector('{task['startSelector']}').scrollIntoView({{behavior: 'smooth', block: 'center'}});")
            time.sleep(1)
            take_screenshot(page, f"Surf_{i}_Target")

            # 1. Click Start
            initial_pages = len(context.pages)
            if not perform_human_mouse_click(page, task['startSelector'], f"Surf_{i}_Start"):
                page.reload(); continue
            
            # Wait for tab
            time.sleep(5)
            if len(context.pages) == initial_pages:
                # Retry JS
                page.click(task['startSelector'])
                time.sleep(5)
                if len(context.pages) == initial_pages: page.reload(); continue

            # 2. Watch Site
            new_page = context.pages[-1]
            new_page.bring_to_front()
            
            # Calculate Wait (Timer + Random 3-5s)
            wait_time = task['timer'] + random.randint(3, 6)
            bot_status["step"] = f"Surfing... ({wait_time}s)"
            
            # Anti-Idle
            for s in range(wait_time):
                if not bot_status["is_running"]: new_page.close(); return
                if s % 2 == 0: 
                    try: new_page.mouse.move(random.randint(100,800), random.randint(100,600))
                    except: pass
                time.sleep(1)
            
            new_page.close()
            page.bring_to_front()
            
            # 3. Confirm
            bot_status["step"] = "Confirming Surf..."
            # Wait for button to become visible (it appears after tab close)
            time.sleep(2) 
            
            # HTML shows ID: #serf_btn_confirm_{ID} with class .confirm-surfing-btn
            confirm_sel = f"#serf_btn_confirm_{task['id']}"
            
            if page.is_visible(confirm_sel):
                perform_human_mouse_click(page, confirm_sel, f"Surf_{i}_Confirm")
                time.sleep(4)
                take_screenshot(page, f"Surf_{i}_Done")
                tasks_done += 1
            else:
                # Sometimes it auto-confirms or needs refresh
                print("Surf Confirm missing.")
                page.reload(); time.sleep(3)

        except Exception as e:
            print(f"Surf Error: {e}")
            try: context.pages[-1].close() if len(context.pages) > 1 else None
            except: pass
            page.reload(); time.sleep(3)
            
    return tasks_done > 0

# --- MAIN RUNNER ---
def run_infinite_loop(username, password):
    global bot_status, shared_data, current_browser_context
    from playwright.sync_api import sync_playwright

    kill_all_browsers()
    reset_debug_log()
    bot_status["is_running"] = True
    bot_status["needs_code"] = False
    shared_data["otp_code"] = None
    
    proxy_config = get_proxy_config()
    if proxy_config:
        print(f"🌍 Proxy: {proxy_config['server']}")
        bot_status["proxy_status"] = f"Proxy: {proxy_config['server']}"
    else:
        bot_status["proxy_status"] = "Direct IP"

    with sync_playwright() as p:
        while bot_status["is_running"]:
            try:
                context = p.chromium.launch_persistent_context(
                    USER_DATA_DIR,
                    headless=True,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1366, "height": 768},
                    is_mobile=False, has_touch=False, proxy=proxy_config,
                    args=["--disable-blink-features=AutomationControlled", "--disable-background-timer-throttling", "--start-maximized"]
                )
                current_browser_context = context
                page = context.new_page()
                
                # --- LOGIN ---
                bot_status["step"] = "Login..."
                page.goto("https://aviso.bz/login", timeout=60000)
                
                if page.is_visible("input[name='username']"):
                    page.fill("input[name='username']", username)
                    page.fill("input[name='password']", password)
                    time.sleep(1)
                    
                    btn_selector = "button:has-text('Войти')"
                    if not page.is_visible(btn_selector): btn_selector = "button[type='submit']"
                    perform_human_mouse_click(page, btn_selector, "Login_Click")
                    
                    time.sleep(5)
                    if page.is_visible("input[name='username']") and "подождите" not in page.content().lower():
                        page.evaluate("document.querySelector('form[action*=\"login\"]').submit()")
                        time.sleep(8)

                    # OTP Handler
                    if page.is_visible("input[name='code']"):
                        bot_status["step"] = "WAITING_FOR_CODE"
                        bot_status["needs_code"] = True
                        while shared_data["otp_code"] is None:
                            time.sleep(1)
                            if not bot_status["is_running"]: break
                        if shared_data["otp_code"]:
                            page.fill("input[name='code']", shared_data["otp_code"])
                            page.press("input[name='code']", "Enter")
                            time.sleep(5)
                            bot_status["needs_code"] = False
                            shared_data["otp_code"] = None

                    if page.is_visible("input[name='username']"):
                        bot_status["step"] = "Login Failed."
                        context.close(); continue
                
                bot_status["step"] = "Login Success!"
                take_screenshot(page, "Login_Success")

                # --- MULTI-TASK LOGIC ---
                
                # 1. Do YouTube
                process_youtube_tasks(context, page)
                
                # 2. Do Surfing (Backup)
                process_surfing_tasks(context, page)
                
                # 3. Check YouTube One Last Time
                print("Checking YT again...")
                process_youtube_tasks(context, page)

                # --- SLEEP CYCLE ---
                print("Cycle Complete. Sleeping 20 mins...")
                context.close() # Close browser to save RAM
                
                for s in range(1200): # 20 Minutes = 1200s
                    if not bot_status["is_running"]: return
                    if s % 10 == 0: 
                        rem = 1200 - s
                        bot_status["step"] = f"💤 Next Run: {rem // 60}m {rem % 60}s"
                    time.sleep(1)

            except Exception as e:
                bot_status["step"] = f"Error: {str(e)}"
                time.sleep(30)

# --- ROUTES ---
@app.route('/')
def index(): return render_template('index.html')

@app.route('/save_proxy', methods=['POST'])
def save_proxy():
    data = request.json
    with open(PROXY_FILE, "w") as f: f.write(data.get('proxy', '').strip())
    return jsonify({"status": "Proxy Saved!"})

@app.route('/clear_proxy', methods=['POST'])
def clear_proxy():
    if os.path.exists(PROXY_FILE): os.remove(PROXY_FILE)
    return jsonify({"status": "Proxy Cleared!"})

@app.route('/submit_code', methods=['POST'])
def submit_code_api():
    data = request.json
    shared_data["otp_code"] = data.get('code')
    return jsonify({"status": "Received"})

@app.route('/start', methods=['POST'])
def start_bot():
    if bot_status["is_running"]: return jsonify({"status": "Running"})
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
        if os.path.exists(USER_DATA_DIR): shutil.rmtree(USER_DATA_DIR); os.makedirs(USER_DATA_DIR, exist_ok=True)
        return jsonify({"status": "Data Wiped"})
    except: return jsonify({"status": "Error"})

@app.route('/status')
def status(): return jsonify(bot_status)

@app.route('/download_log')
def download_log():
    if os.path.exists(DEBUG_FILE): return send_file(DEBUG_FILE, as_attachment=True)
    else: return "Log not found", 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
