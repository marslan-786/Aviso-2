import os
import time
import json
import threading
import random
from flask import Flask, render_template, request, jsonify, send_file

app = Flask(__name__)

# --- Configuration ---
SCREENSHOT_DIR = "static/screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)
USER_DATA_DIR = "/app/browser_data2"
DEBUG_FILE = "debug_source.html"

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
    except: pass

def save_debug_html(page):
    try:
        content = page.content()
        with open(DEBUG_FILE, "w", encoding="utf-8") as f:
            f.write(content)
    except: pass

# --- MOBILE STEALTH ---
def apply_mobile_stealth(page):
    try:
        page.add_init_script("""
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
            Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 5 });
            window.ontouchstart = true;
        """)
    except: pass

# --- JS SCANNER (Visual Only) ---
def get_best_task_via_js(page):
    return page.evaluate("""() => {
        const tables = Array.from(document.querySelectorAll('table[id^="ads-link-"]'));
        
        for (let table of tables) {
            // Visibility Check
            if (table.offsetParent === null) continue;
            const rect = table.getBoundingClientRect();
            if (rect.height === 0 || rect.width === 0) continue; 
            
            const style = window.getComputedStyle(table);
            if (style.display === 'none' || style.visibility === 'hidden') continue;

            const idPart = table.id.replace('ads-link-', '');
            const isVideo = table.querySelector('.ybprosm') !== null;
            if (!isVideo) continue;

            const timerInput = document.getElementById('ads_timer_' + idPart);
            const duration = timerInput ? parseInt(timerInput.value) : 20;
            const priceEl = table.querySelector('span[title="Стоимость просмотра"], .price-text');
            const price = priceEl ? parseFloat(priceEl.innerText) : 0;

            return {
                id: idPart,
                price: price,
                duration: duration,
                tableId: table.id,
                startSelector: '#link_ads_start_' + idPart,
                confirmSelector: '#ads_btn_confirm_' + idPart,
                errorSelector: '#btn_error_view_' + idPart
            };
        }
        return null; 
    }""")

# --- PURE JS CLICK ---
def perform_js_click(page, selector):
    try:
        print(f"JS Click: {selector}")
        result = page.evaluate(f"""() => {{
            const el = document.querySelector('{selector}');
            if (el) {{ el.click(); return true; }}
            return false;
        }}""")
        return result
    except: return False

# --- VIDEO AUTO PLAY ---
def ensure_video_playing_js(new_page):
    try:
        new_page.evaluate("""() => {
            const playBtn = document.querySelector('.ytp-large-play-button') || document.querySelector('button[aria-label="Play"]');
            if (playBtn) playBtn.click();
            else {
                const video = document.querySelector('video');
                if (video) video.play();
            }
        }""")
    except: pass

# --- PROCESS LOGIC ---
def process_youtube_tasks(context, page):
    bot_status["step"] = "Checking Tasks..."
    page.goto("https://aviso.bz/tasks-youtube")
    page.wait_for_load_state("networkidle")
    
    # لاگ ان چیک (تاکہ ٹاسک لسٹ کے بجائے لاگ ان پیج نہ کیپچر ہو)
    if page.is_visible("input[name='username']"):
        print("Logged out detected inside task loop.")
        return # واپس مین لوپ میں بھیج دیں

    page.evaluate("if(document.getElementById('clouse_adblock')) document.getElementById('clouse_adblock').remove();")
    take_screenshot(page, "0_Task_List")

    for i in range(1, 31): 
        if not bot_status["is_running"]: break
        
        bot_status["step"] = f"Scanning Active Task #{i}..."
        task_data = get_best_task_via_js(page)
        
        if not task_data:
            print("No visible tasks. Saving debug...")
            save_debug_html(page)
            bot_status["step"] = "No Tasks Left."
            break
            
        print(f"Target: {task_data['id']} ({task_data['duration']}s)")
        bot_status["step"] = f"Task #{i}: {task_data['duration']}s"

        try:
            # Highlight
            page.evaluate(f"document.getElementById('{task_data['tableId']}').style.border = '4px solid red';")
            page.evaluate(f"document.getElementById('{task_data['tableId']}').scrollIntoView({{block: 'center'}});")
            time.sleep(1)
            take_screenshot(page, f"Task_{i}_1_Target")

            # --- CLICK ---
            initial_pages = len(context.pages)
            perform_js_click(page, task_data['startSelector'])
            time.sleep(5)

            if len(context.pages) == initial_pages:
                print("Click failed. Retrying...")
                perform_js_click(page, task_data['startSelector'])
                time.sleep(5)
                if len(context.pages) == initial_pages:
                    print("Task dead. Refreshing.")
                    page.reload()
                    time.sleep(3)
                    continue

            new_page = context.pages[-1]
            apply_mobile_stealth(new_page) 
            new_page.wait_for_load_state("domcontentloaded")
            new_page.bring_to_front()
            
            time.sleep(2)
            try:
                new_page.evaluate("""() => {
                    const btn = document.querySelector("button:contains('Я ознакомлен')") || document.querySelector("a.tr_but_b");
                    if(btn) btn.click();
                }""")
                time.sleep(2)
            except: pass

            ensure_video_playing_js(new_page)
            take_screenshot(new_page, f"Task_{i}_2_Video")
            
            wait_time = task_data['duration'] + random.randint(5, 8)
            for sec in range(wait_time):
                if not bot_status["is_running"]: 
                    new_page.close()
                    return
                if sec % 5 == 0: bot_status["step"] = f"Watching... {sec}/{wait_time}s"
                time.sleep(1)

            new_page.close()
            page.bring_to_front()
            time.sleep(1)
            take_screenshot(page, f"Task_{i}_3_Back")

            confirm_selector = task_data['confirmSelector']
            bot_status["step"] = "Waiting for Confirm..."
            
            btn_visible = False
            for _ in range(5):
                visible = page.evaluate(f"""() => {{
                    const el = document.querySelector('{confirm_selector}');
                    return el && el.offsetParent !== null;
                }}""")
                if visible:
                    btn_visible = True
                    break
                time.sleep(1)
            
            if btn_visible:
                perform_js_click(page, confirm_selector)
                time.sleep(5)
                take_screenshot(page, f"Task_{i}_4_Success")
                bot_status["step"] = f"Task #{i} Done!"
            else:
                print("Confirm missing.")
                bot_status["step"] = "Confirm Missing. Refreshing..."
                page.reload() 
                time.sleep(3)
                break

        except Exception as e:
            print(f"Task error: {e}")
            try: context.pages[-1].close() if len(context.pages) > 1 else None
            except: pass
            page.reload()
            time.sleep(5)
            break

    if bot_status["is_running"]:
        print("Cycle done. Logging out.")
        page.goto("https://aviso.bz/logout")

# --- MAIN RUNNER ---
def run_infinite_loop(username, password):
    global bot_status, shared_data
    from playwright.sync_api import sync_playwright

    bot_status["is_running"] = True
    bot_status["needs_code"] = False
    shared_data["otp_code"] = None

    with sync_playwright() as p:
        while bot_status["is_running"]:
            try:
                context = p.chromium.launch_persistent_context(
                    USER_DATA_DIR,
                    headless=True,
                    user_agent="Mozilla/5.0 (Linux; Android 14; 2409BRN2CG) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.200 Mobile Safari/537.36",
                    viewport={"width": 412, "height": 915},
                    device_scale_factor=2.625,
                    is_mobile=True,
                    has_touch=True,
                    args=["--lang=en-US", "--no-sandbox", "--disable-blink-features=AutomationControlled"]
                )
                
                page = context.new_page()
                apply_mobile_stealth(page)
                
                # --- ROBUST LOGIN ---
                logged_in = False
                
                while not logged_in and bot_status["is_running"]:
                    bot_status["step"] = "Opening Login Page..."
                    page.goto("https://aviso.bz/login", timeout=60000)
                    page.wait_for_load_state("networkidle")

                    if page.url != "https://aviso.bz/login" and not page.is_visible("input[name='username']"):
                         print("Already logged in.")
                         logged_in = True
                         break

                    print("Typing Credentials...")
                    
                    # 1. Username
                    page.click("input[name='username']")
                    page.type("input[name='username']", username, delay=100) # 100ms delay per char
                    time.sleep(0.5)

                    # 2. Password
                    page.click("input[name='password']")
                    page.type("input[name='password']", password, delay=100)
                    time.sleep(0.5)

                    # 3. VERIFY FIELDS
                    val_u = page.input_value("input[name='username']")
                    val_p = page.input_value("input[name='password']")
                    
                    if not val_u or not val_p:
                        print("Typing failed. Retrying force fill...")
                        # Fallback: JS Fill
                        page.evaluate(f"document.querySelector('input[name=\"username\"]').value = '{username}';")
                        page.evaluate(f"document.querySelector('input[name=\"password\"]').value = '{password}';")
                        time.sleep(1)

                    take_screenshot(page, "Login_Filled")
                    
                    # Submit
                    submit_btn = page.locator("button[type='submit'], button:has-text('Войти')")
                    if submit_btn.count() > 0: submit_btn.first.click()
                    else: page.locator("input[name='password']").press("Enter")
                    
                    time.sleep(5)

                    if page.is_visible("input[name='code']"):
                        bot_status["step"] = "WAITING_FOR_CODE"
                        bot_status["needs_code"] = True
                        take_screenshot(page, "Code_Required")
                        
                        wait_count = 0
                        while shared_data["otp_code"] is None:
                            time.sleep(1)
                            wait_count += 1
                            if wait_count > 300 or not bot_status["is_running"]: break
                        
                        if shared_data["otp_code"]:
                            page.fill("input[name='code']", shared_data["otp_code"])
                            page.locator("button[type='submit']").click()
                            time.sleep(8)
                            bot_status["needs_code"] = False
                            shared_data["otp_code"] = None

                    if "login" not in page.url or page.is_visible("#new-money-ballans"):
                        print("Login Verified!")
                        logged_in = True
                        take_screenshot(page, "Login_Verified")
                    else:
                        print("Login failed. Retrying loop...")
                        bot_status["step"] = "Login Failed. Retrying..."
                        take_screenshot(page, "Login_Failed")
                        time.sleep(3)
                
                if logged_in and bot_status["is_running"]:
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

@app.route('/status')
def status(): return jsonify(bot_status)

@app.route('/download_log')
def download_log():
    if os.path.exists(DEBUG_FILE): return send_file(DEBUG_FILE, as_attachment=True)
    else: return "Log not found", 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
