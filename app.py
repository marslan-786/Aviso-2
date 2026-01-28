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
current_browser_context = None # Global reference to close browser securely

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
        # Hide Webdriver
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Original Mobile Headers
        page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Linux; Android 14; 23124RN87G) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/133.0.6943.100 Mobile Safari/537.36",
            "sec-ch-ua": '"Not A(Brand";v="99", "Android WebView";v="133", "Chromium";v="133"',
            "sec-ch-ua-mobile": "?1",
            "sec-ch-ua-platform": '"Android"',
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Upgrade-Insecure-Requests": "1"
        })
    except: pass

# --- JS SCANNER (To Find Elements Only) ---
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

# --- VISUAL TOUCH (RED DOT + REAL TAP) ---
def perform_visual_touch(page, selector, screenshot_name):
    """
    یہ فنکشن اب بالکل اصلی ٹچ کرے گا اور پہلے نشان دہی کرے گا۔
    """
    try:
        # عنصر کی جگہ معلوم کریں
        box = page.locator(selector).bounding_box()
        if box:
            # درمیان سے تھوڑا رینڈم
            center_x = box['x'] + box['width'] / 2
            center_y = box['y'] + box['height'] / 2
            
            # Safe Area (30% from center)
            safe_w = box['width'] * 0.3
            safe_h = box['height'] * 0.3
            
            final_x = center_x + random.uniform(-safe_w, safe_w)
            final_y = center_y + random.uniform(-safe_h, safe_h)
            
            print(f"Touching at: {final_x:.1f}, {final_y:.1f}")

            # 1. SHOW RED DOT (Visual Feedback)
            page.evaluate(f"""() => {{
                const d = document.createElement('div');
                d.id = 'aim-dot';
                d.style.position = 'fixed'; 
                d.style.left = '{final_x-6}px'; d.style.top = '{final_y-6}px';
                d.style.width = '12px'; d.style.height = '12px';
                d.style.background = 'red'; d.style.border = '2px solid yellow';
                d.style.borderRadius = '50%'; d.style.zIndex = '2147483647';
                d.style.pointerEvents = 'none';
                document.body.appendChild(d);
            }}""")

            # 2. Wait & Screenshot
            time.sleep(0.5) 
            take_screenshot(page, screenshot_name)
            
            # 3. REAL TAP (No JS Click)
            page.touchscreen.tap(final_x, final_y)
            
            # 4. Cleanup Dot
            page.evaluate("if(document.getElementById('aim-dot')) document.getElementById('aim-dot').remove();")
            return True
    except Exception as e:
        print(f"Touch Error: {e}")
    return False

# --- AUTO PLAY (With Touch) ---
def ensure_video_playing(page):
    try:
        # Try tapping center first (Most natural)
        vp = page.viewport_size
        if vp: 
            page.touchscreen.tap(vp['width']/2, vp['height']/2)
            time.sleep(1)
            
        # Try finding button and touching it
        if page.is_visible(".ytp-large-play-button"):
            perform_visual_touch(page, ".ytp-large-play-button", "Play_Tap")
    except: pass

# --- PROCESS LOGIC ---
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
            print("No visible tasks.")
            save_debug_html(page)
            bot_status["step"] = "No Tasks Visible."
            break
            
        print(f"Target: {task_data['id']} ({task_data['duration']}s)")
        bot_status["step"] = f"Task #{i}: {task_data['duration']}s"

        try:
            # Highlight Box
            page.evaluate(f"document.getElementById('{task_data['tableId']}').style.border = '3px solid red';")
            page.evaluate(f"document.getElementById('{task_data['tableId']}').scrollIntoView({{block: 'center'}});")
            time.sleep(1)
            
            # --- 1. TOUCH START ---
            initial_pages = len(context.pages)
            if not perform_visual_touch(page, task_data['startSelector'], f"Task_{i}_1_Start_Tap"):
                page.reload()
                continue
            
            time.sleep(5)
            
            if len(context.pages) == initial_pages:
                print("Tap missed. Retrying...")
                perform_visual_touch(page, task_data['startSelector'], f"Task_{i}_1_Retry")
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
            try:
                if new_page.is_visible("button:has-text('Я ознакомлен')"):
                    perform_visual_touch(new_page, "button:has-text('Я ознакомлен')", f"Task_{i}_VPN_Tap")
                    time.sleep(2)
            except: pass

            ensure_video_playing(new_page)
            take_screenshot(new_page, f"Task_{i}_2_Video_Open")
            
            wait_time = task_data['duration'] + random.randint(5, 10)
            for sec in range(wait_time):
                if not bot_status["is_running"]: 
                    new_page.close()
                    return
                if sec % 5 == 0: bot_status["step"] = f"Watching... {sec}/{wait_time}s"
                time.sleep(1)

            new_page.close()
            page.bring_to_front()
            time.sleep(1)
            take_screenshot(page, f"Task_{i}_3_Back_Main")

            confirm_selector = task_data['confirmSelector']
            bot_status["step"] = "Confirming..."
            
            btn_visible = False
            for _ in range(8):
                if page.is_visible(confirm_selector):
                    btn_visible = True
                    break
                time.sleep(1)
            
            if btn_visible:
                # --- 2. TOUCH CONFIRM ---
                perform_visual_touch(page, confirm_selector, f"Task_{i}_4_Confirm_Tap")
                time.sleep(5)
                take_screenshot(page, f"Task_{i}_5_Success")
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
        print("Cycle finished. Logging out.")
        page.goto("https://aviso.bz/logout")

# --- MAIN RUNNER ---
def run_infinite_loop(username, password):
    global bot_status, shared_data, current_browser_context
    from playwright.sync_api import sync_playwright

    bot_status["is_running"] = True
    bot_status["needs_code"] = False
    shared_data["otp_code"] = None

    with sync_playwright() as p:
        while bot_status["is_running"]:
            try:
                # Store context in global var for force closing
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
                current_browser_context = context # Save reference
                
                page = context.new_page()
                apply_mobile_stealth(page)
                
                bot_status["step"] = "Logging In..."
                page.goto("https://aviso.bz/login", timeout=60000)
                
                if page.is_visible("input[name='username']"):
                    # HUMAN TYPING (No Paste)
                    page.tap("input[name='username']")
                    page.type("input[name='username']", username, delay=150)
                    time.sleep(0.5)
                    
                    page.tap("input[name='password']")
                    page.type("input[name='password']", password, delay=150)
                    time.sleep(1)

                    # Touch Login Button
                    perform_visual_touch(page, "button[type='submit']", "Login_Tap")
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
                            perform_visual_touch(page, "button[type='submit']", "Code_Tap")
                            time.sleep(8)
                            bot_status["needs_code"] = False
                            shared_data["otp_code"] = None

                    if page.is_visible("input[name='username']"):
                        bot_status["step"] = "Login Failed. Retrying..."
                        time.sleep(5)
                        context.close()
                        current_browser_context = None
                        continue
                
                take_screenshot(page, "Login_Success")
                process_youtube_tasks(context, page)
                
                context.close()
                current_browser_context = None
                
                print("Waiting 1 hour...")
                for s in range(3600):
                    if not bot_status["is_running"]: return
                    if s % 10 == 0: 
                        rem = 3600 - s
                        bot_status["step"] = f"💤 Next Run: {rem // 60}m {rem % 60}s"
                    time.sleep(1)

            except Exception as e:
                bot_status["step"] = f"Error: {str(e)}"
                try: context.close() 
                except: pass
                current_browser_context = None
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

# --- FIXED CLEAR DATA ROUTE ---
@app.route('/clear_data', methods=['POST'])
def clear_data_route():
    global current_browser_context
    try:
        # 1. Stop Bot
        bot_status["is_running"] = False
        
        # 2. Force Close Browser
        if current_browser_context:
            try:
                current_browser_context.close()
                print("Forced browser close.")
            except: pass
            current_browser_context = None
        
        time.sleep(3) # Wait for file release
        
        # 3. Delete Files
        if os.path.exists(USER_DATA_DIR):
            shutil.rmtree(USER_DATA_DIR)
            os.makedirs(USER_DATA_DIR, exist_ok=True)
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
