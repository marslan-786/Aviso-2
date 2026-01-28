import os
import time
import json
import threading
import random
import shutil
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

# --- ULTIMATE STEALTH (Anti-Detect) ---
def apply_mobile_stealth(page):
    try:
        # 1. Override Webdriver Flag
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # 2. Fake Plugins & Languages
        page.add_init_script("""
            Object.defineProperty(navigator, 'languages', {get: () => ['ru-RU', 'ru', 'en-US', 'en']});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
        """)
        
        # 3. Mobile Emulation Headers
        page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Linux; Android 14; 23124RN87G) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.6943.100 Mobile Safari/537.36",
            "sec-ch-ua": '"Not A(Brand";v="99", "Android WebView";v="133", "Chromium";v="133"',
            "sec-ch-ua-mobile": "?1",
            "sec-ch-ua-platform": '"Android"',
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Upgrade-Insecure-Requests": "1"
        })
    except: pass

# --- JS SCANNER ---
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

# --- VISUAL TOUCH (The Red Dot) ---
def perform_visual_touch(page, selector, screenshot_name):
    try:
        box = page.locator(selector).bounding_box()
        if box:
            # Center + Micro Randomness
            center_x = box['x'] + box['width'] / 2
            center_y = box['y'] + box['height'] / 2
            
            # Safe zone 30% from center
            safe_w = box['width'] * 0.3
            safe_h = box['height'] * 0.3
            
            x = center_x + random.uniform(-safe_w, safe_w)
            y = center_y + random.uniform(-safe_h, safe_h)
            
            print(f"Aiming: {x:.1f}, {y:.1f}")

            # 1. SHOW RED DOT
            page.evaluate(f"""() => {{
                const d = document.createElement('div');
                d.id = 'aim-dot';
                d.style.position = 'fixed'; // Fixed better for scroll
                d.style.left = '{x-6}px';
                d.style.top = '{y-6}px';
                d.style.width = '12px';
                d.style.height = '12px';
                d.style.background = 'red';
                d.style.border = '2px solid yellow';
                d.style.borderRadius = '50%';
                d.style.zIndex = '2147483647';
                d.style.pointerEvents = 'none';
                document.body.appendChild(d);
            }}""")

            # 2. Wait & Snap
            time.sleep(0.5) 
            take_screenshot(page, screenshot_name)
            
            # 3. REAL TOUCH
            page.touchscreen.tap(x, y)
            
            # 4. Remove Dot
            page.evaluate("if(document.getElementById('aim-dot')) document.getElementById('aim-dot').remove();")
            return True
    except Exception as e:
        print(f"Touch Error: {e}")
    return False

# --- AUTO PLAY ---
def ensure_video_playing(page):
    try:
        # JS Click is safer for Play button
        page.evaluate("""() => {
            const btn = document.querySelector('.ytp-large-play-button') || document.querySelector('button[aria-label="Play"]');
            if(btn) btn.click();
        }""")
    except: pass

# --- PROCESS ---
def process_youtube_tasks(context, page):
    bot_status["step"] = "Opening Task List..."
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
            print("No visible tasks.")
            save_debug_html(page)
            bot_status["step"] = "No Tasks Visible."
            break
            
        print(f"Task: {task_data['id']} ({task_data['duration']}s)")
        bot_status["step"] = f"Task #{i}: {task_data['duration']}s"

        try:
            # Highlight
            page.evaluate(f"document.getElementById('{task_data['tableId']}').style.border = '3px solid red';")
            page.evaluate(f"document.getElementById('{task_data['tableId']}').scrollIntoView({{block: 'center'}});")
            time.sleep(1)
            take_screenshot(page, f"Task_{i}_1_Target")

            # --- VISUAL CLICK START ---
            initial_pages = len(context.pages)
            
            if not perform_visual_touch(page, task_data['startSelector'], f"Task_{i}_2_Aim_Start"):
                print("Touch failed. Skipping.")
                page.reload()
                continue
            
            time.sleep(5)

            # Check if tab opened
            if len(context.pages) == initial_pages:
                print("Click missed. JS Backup...")
                page.evaluate(f"document.querySelector('{task_data['startSelector']}').click();")
                time.sleep(5)
                if len(context.pages) == initial_pages:
                    print("Dead link. Refreshing.")
                    page.reload()
                    continue

            new_page = context.pages[-1]
            apply_mobile_stealth(new_page) 
            new_page.wait_for_load_state("domcontentloaded")
            new_page.bring_to_front()
            
            time.sleep(2)
            # Remove VPN/Overlay
            try:
                if new_page.is_visible("button:has-text('Я ознакомлен')"):
                    perform_visual_touch(new_page, "button:has-text('Я ознакомлен')", f"Task_{i}_VPN_Click")
                    time.sleep(2)
            except: pass

            ensure_video_playing(new_page)
            take_screenshot(new_page, f"Task_{i}_3_Video_Open")
            
            wait_time = task_data['duration'] + random.randint(6, 12) # Extra random buffer
            for sec in range(wait_time):
                if not bot_status["is_running"]: 
                    new_page.close()
                    return
                if sec % 5 == 0: bot_status["step"] = f"Watching... {sec}/{wait_time}s"
                time.sleep(1)

            new_page.close()
            page.bring_to_front()
            time.sleep(1)
            take_screenshot(page, f"Task_{i}_4_Back_Main")

            confirm_selector = task_data['confirmSelector']
            bot_status["step"] = "Confirming..."
            
            # Button Wait
            btn_visible = False
            for _ in range(8): # 8 sec wait
                if page.is_visible(confirm_selector):
                    btn_visible = True
                    break
                time.sleep(1)
            
            if btn_visible:
                perform_visual_touch(page, confirm_selector, f"Task_{i}_5_Aim_Confirm")
                time.sleep(5)
                take_screenshot(page, f"Task_{i}_6_Success")
                bot_status["step"] = f"Task #{i} Done!"
            else:
                print("Confirm missing.")
                bot_status["step"] = "Confirm Missing. Refreshing..."
                page.reload()
                time.sleep(3)
                break # Refresh list

        except Exception as e:
            print(f"Task error: {e}")
            try: context.pages[-1].close() if len(context.pages) > 1 else None
            except: pass
            page.reload()
            time.sleep(5)
            break

    if bot_status["is_running"]:
        print("Cycle finished. Logging out.")
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
                    user_agent="Mozilla/5.0 (Linux; Android 14; 23124RN87G) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.6943.100 Mobile Safari/537.36",
                    viewport={"width": 412, "height": 915},
                    device_scale_factor=2.625,
                    is_mobile=True,
                    has_touch=True,
                    args=["--lang=en-US", "--no-sandbox", "--disable-blink-features=AutomationControlled"]
                )
                
                page = context.new_page()
                apply_mobile_stealth(page)
                
                bot_status["step"] = "Logging In..."
                page.goto("https://aviso.bz/login", timeout=60000)
                
                if page.is_visible("input[name='username']"):
                    # Type Human-like
                    page.click("input[name='username']")
                    page.type("input[name='username']", username, delay=120)
                    time.sleep(0.5)
                    page.click("input[name='password']")
                    page.type("input[name='password']", password, delay=120)
                    time.sleep(1)

                    # Ensure filled
                    if not page.input_value("input[name='password']"):
                        page.fill("input[name='password']", password)

                    # Submit
                    page.evaluate("document.querySelector('button[type=\"submit\"]').click()")
                    time.sleep(5)

                    if page.is_visible("input[name='code']"):
                        bot_status["step"] = "WAITING_FOR_CODE"
                        bot_status["needs_code"] = True
                        take_screenshot(page, "Code_Required")
                        
                        count = 0
                        while shared_data["otp_code"] is None:
                            time.sleep(1)
                            count += 1
                            if count > 300 or not bot_status["is_running"]: break
                        
                        if shared_data["otp_code"]:
                            page.fill("input[name='code']", shared_data["otp_code"])
                            page.evaluate("document.querySelector('button[type=\"submit\"]').click()")
                            time.sleep(8)
                            bot_status["needs_code"] = False
                            shared_data["otp_code"] = None

                    # Verify Login
                    if page.is_visible("input[name='username']"):
                        print("Login failed. Retrying...")
                        bot_status["step"] = "Login Failed. Retrying..."
                        time.sleep(5)
                        context.close()
                        continue
                
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

# --- NEW: CLEAR DATA ROUTE ---
@app.route('/clear_data', methods=['POST'])
def clear_data_route():
    try:
        # Stop bot first
        bot_status["is_running"] = False
        time.sleep(2) # Give it time to close
        
        if os.path.exists(USER_DATA_DIR):
            shutil.rmtree(USER_DATA_DIR)
            os.makedirs(USER_DATA_DIR, exist_ok=True)
            print("Browser data wiped.")
            return jsonify({"status": "Data Wiped Successfully"})
        else:
            return jsonify({"status": "No Data Found"})
    except Exception as e:
        return jsonify({"status": f"Error: {str(e)}"})

@app.route('/status')
def status(): return jsonify(bot_status)

@app.route('/download_log')
def download_log():
    if os.path.exists(DEBUG_FILE): return send_file(DEBUG_FILE, as_attachment=True)
    else: return "Log not found", 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
