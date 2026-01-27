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

# --- JS SCANNER (Visual & Active) ---
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

# --- PURE JS CLICK FUNCTION ---
def perform_js_click(page, selector):
    """
    یہ فنکشن Python کی بجائے براؤزر کے اندر جا کر JS کے ذریعے کلک کرے گا۔
    """
    try:
        print(f"Executing JS Click on: {selector}")
        page.evaluate(f"""() => {{
            const el = document.querySelector('{selector}');
            if (el) {{
                el.click();
            }} else {{
                throw new Error('Element not found: {selector}');
            }}
        }}""")
        return True
    except Exception as e:
        print(f"JS Click Error: {e}")
        return False

# --- JS AUTO PLAY (For Video Page) ---
def ensure_video_playing_js(new_page):
    try:
        # ویڈیو پلیئر کے بڑے بٹن کو JS سے کلک کریں
        new_page.evaluate("""() => {
            const playBtn = document.querySelector('.ytp-large-play-button') || document.querySelector('button[aria-label="Play"]');
            if (playBtn) {
                playBtn.click();
            } else {
                // اگر بٹن نہ ملے تو ویڈیو ایلیمنٹ کو ڈائریکٹ پلے کرو
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
    
    page.evaluate("if(document.getElementById('clouse_adblock')) document.getElementById('clouse_adblock').remove();")
    take_screenshot(page, "0_Task_List")

    for i in range(1, 31): 
        if not bot_status["is_running"]: break
        
        bot_status["step"] = f"Scanning Active Task #{i}..."
        task_data = get_best_task_via_js(page)
        
        if not task_data:
            print("No visible tasks. Refreshing...")
            page.reload()
            time.sleep(5)
            task_data = get_best_task_via_js(page)
            if not task_data:
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

            # --- ACTION 1: JS CLICK START ---
            initial_pages = len(context.pages)
            
            # Pure JS Click
            perform_js_click(page, task_data['startSelector'])
            
            time.sleep(5) # Wait for tab

            # --- VALIDATION ---
            if len(context.pages) == initial_pages:
                print("JS Click didn't open tab. Retrying once...")
                time.sleep(2)
                # ایک بار پھر ٹرائی کریں (Double Tap Strategy)
                perform_js_click(page, task_data['startSelector'])
                time.sleep(5)
                
                if len(context.pages) == initial_pages:
                    print("Task dead. Refreshing.")
                    bot_status["step"] = "Click Failed. Refreshing..."
                    page.reload()
                    time.sleep(3)
                    continue

            # Task Started
            new_page = context.pages[-1]
            apply_mobile_stealth(new_page) 
            new_page.wait_for_load_state("domcontentloaded")
            new_page.bring_to_front()
            
            time.sleep(2)
            # Handle obstacles (VPN Warning etc) with JS
            try:
                new_page.evaluate("""() => {
                    const btn = document.querySelector("button:contains('Я ознакомлен')") || document.querySelector("a.tr_but_b");
                    if(btn) btn.click();
                }""")
                time.sleep(2)
            except: pass

            # --- ACTION 2: JS VIDEO PLAY ---
            ensure_video_playing_js(new_page)
            take_screenshot(new_page, f"Task_{i}_2_Video_Open")
            
            # Wait + Buffer
            wait_time = task_data['duration'] + random.randint(5, 8)
            for sec in range(wait_time):
                if not bot_status["is_running"]: 
                    new_page.close()
                    return
                if sec % 5 == 0: bot_status["step"] = f"Watching... {sec}/{wait_time}s"
                time.sleep(1)

            # Close
            new_page.close()
            page.bring_to_front()
            time.sleep(1)
            take_screenshot(page, f"Task_{i}_3_Back_Main")

            # --- ACTION 3: JS CONFIRM ---
            confirm_selector = task_data['confirmSelector']
            bot_status["step"] = "Waiting for Confirm..."
            
            # بٹن کے لیے 5 سیکنڈ ویٹ (Visibility Check via JS)
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
                # Pure JS Click on Confirm
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
                    user_agent="Mozilla/5.0 (Linux; Android 14; 2409BRN2CG) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.6778.200 Mobile Safari/537.36",
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
                    page.fill("input[name='username']", username)
                    page.fill("input[name='password']", password)
                    
                    # Login Button via JS
                    page.evaluate("document.querySelector('button[type=\"submit\"]').click()")
                    time.sleep(5)

                    if page.is_visible("input[name='code']"):
                        bot_status["step"] = "WAITING_FOR_CODE"
                        bot_status["needs_code"] = True
                        take_screenshot(page, "Code_Required")
                        while shared_data["otp_code"] is None:
                            time.sleep(2)
                            if not bot_status["is_running"]: 
                                context.close()
                                return
                        
                        page.fill("input[name='code']", shared_data["otp_code"])
                        page.evaluate("document.querySelector('button[type=\"submit\"]').click()") # JS Click
                        time.sleep(8)
                        bot_status["needs_code"] = False
                
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

@app.route('/status')
def status(): return jsonify(bot_status)

@app.route('/download_log')
def download_log():
    if os.path.exists(DEBUG_FILE): return send_file(DEBUG_FILE, as_attachment=True)
    else: return "Log not found", 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
