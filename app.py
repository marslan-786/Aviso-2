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
            navigator.getBattery = async () => { return { level: 0.85, charging: false } };
        """)
    except: pass

# --- JS SCANNER ---
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
            const timerInput = document.getElementById('ads_timer_' + idPart);
            const duration = timerInput ? parseInt(timerInput.value) : 15;

            return {
                id: idPart,
                price: price,
                duration: duration,
                tableId: task.id,
                startSelector: '#link_ads_start_' + idPart,
                confirmSelector: '#ads_btn_confirm_' + idPart,
                errorSelector: '#btn_error_view_' + idPart
            };
        }).filter(item => item !== null);

        data.sort((a, b) => b.price - a.price);
        return data.length > 0 ? data[0] : null;
    }""")

# --- NEW: AUTO PLAY VIDEO FUNCTION ---
def ensure_video_playing(new_page):
    """
    یہ فنکشن ویڈیو پیج پر پلے بٹن ڈھونڈ کر اسے دبائے گا۔
    """
    print("Checking for Play Button...")
    try:
        # YouTube کے مختلف Play Buttons کے سلیکٹرز
        # 1. Big Red Button (.ytp-large-play-button)
        # 2. Generic Mobile Play Button
        # 3. Iframe Center
        
        # پہلے کوشش: بڑا بٹن ڈھونڈو
        play_btn = new_page.locator(".ytp-large-play-button, button[aria-label='Play'], .html5-video-player")
        
        if play_btn.count() > 0 and play_btn.first.is_visible():
            print("Play button found! Tapping...")
            play_btn.first.tap()
            time.sleep(1)
        else:
            # اگر بٹن نہیں ملا تو شاید ویڈیو iframe میں ہو۔
            # ہم اسکرین کے بالکل بیچ میں ایک 'Tap' کریں گے (موبائل پر یہ اکثر ویڈیو چلا دیتا ہے)
            print("Button not found via selector. Trying center tap...")
            viewport = new_page.viewport_size
            if viewport:
                x = viewport['width'] / 2
                y = viewport['height'] / 2
                new_page.mouse.click(x, y)
                
    except Exception as e:
        print(f"Auto-play error: {e}")

# --- PROCESS LOGIC ---
def process_youtube_tasks(context, page):
    bot_status["step"] = "Checking Tasks..."
    page.goto("https://aviso.bz/tasks-youtube")
    page.wait_for_load_state("networkidle")
    
    page.evaluate("if(document.getElementById('clouse_adblock')) document.getElementById('clouse_adblock').remove();")
    
    take_screenshot(page, "0_Main_List_Loaded")

    for i in range(1, 31): 
        if not bot_status["is_running"]: break
        
        bot_status["step"] = f"Finding Task #{i}..."
        task_data = get_best_task_via_js(page)
        
        if not task_data:
            print("No tasks found. Scrolling...")
            page.mouse.wheel(0, 500)
            time.sleep(3)
            task_data = get_best_task_via_js(page)
            if not task_data:
                print("No tasks available.")
                bot_status["step"] = "No Tasks. Finished."
                break
            
        print(f"Doing Task: {task_data['id']} ({task_data['duration']}s)")
        bot_status["step"] = f"Task #{i}: Starting..."

        try:
            # Highlight Target
            page.evaluate(f"document.getElementById('{task_data['tableId']}').style.border = '4px solid red';")
            page.evaluate(f"document.getElementById('{task_data['tableId']}').scrollIntoView({{block: 'center'}});")
            time.sleep(1)
            take_screenshot(page, f"Task_{i}_1_Target_Locked")

            # Start Task
            start_selector = task_data['startSelector']
            
            with context.expect_page() as new_page_info:
                page.tap(start_selector)
            
            new_page = new_page_info.value
            apply_mobile_stealth(new_page) 
            new_page.wait_for_load_state("domcontentloaded")
            new_page.bring_to_front()
            
            # --- AUTO PLAY LOGIC HERE ---
            time.sleep(2) # لوڈ ہونے دیں
            ensure_video_playing(new_page) # <--- ویڈیو پلے کریں
            
            # Screenshot to prove it's playing
            time.sleep(2)
            take_screenshot(new_page, f"Task_{i}_2_Video_Playing")
            
            # Check Timer on Main Page
            take_screenshot(page, f"Task_{i}_3_Timer_Check")
            
            # Wait Loop
            max_wait = 100
            timer_finished = False
            
            for tick in range(max_wait):
                if not bot_status["is_running"]: 
                    new_page.close()
                    return
                
                # Keep video active
                try: new_page.touchscreen.tap(200, 200) # Small taps to keep screen active
                except: pass

                status_check = page.evaluate(f"""() => {{
                    const btn = document.querySelector('{task_data['confirmSelector']}');
                    const err = document.querySelector('{task_data['errorSelector']}');
                    if (err && err.offsetParent !== null) return 'error';
                    if (btn && btn.offsetParent !== null) return 'done';
                    return 'wait';
                }}""")

                if status_check == 'error':
                    take_screenshot(page, f"Task_{i}_Error_Msg")
                    break 
                
                if status_check == 'done':
                    timer_finished = True
                    break
                
                time.sleep(1)
                if tick % 5 == 0: bot_status["step"] = f"Watching... {tick}s"

            new_page.close()
            page.bring_to_front()
            
            if timer_finished:
                bot_status["step"] = "Confirming..."
                page.tap(task_data['confirmSelector'])
                time.sleep(5)
                take_screenshot(page, f"Task_{i}_4_Success")
                bot_status["step"] = f"Task #{i} Success!"
            else:
                bot_status["step"] = "Task Timeout"
                page.reload()

        except Exception as e:
            print(f"Task failed: {e}")
            try: new_page.close() 
            except: pass
            page.reload()
            time.sleep(5)

# --- MAIN RUNNER ---
def run_single_account(username, password):
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
            
            bot_status["step"] = "Opening Aviso..."
            page.goto("https://aviso.bz/tasks-youtube", timeout=60000)
            page.wait_for_load_state("networkidle")
            
            if "login" in page.url or page.is_visible("input[name='username']"):
                print("Logging in...")
                bot_status["step"] = "Logging In..."
                page.goto("https://aviso.bz/login")
                
                page.fill("input[name='username']", username)
                page.fill("input[name='password']", password)
                
                btn = page.locator("button[type='submit'], button:has-text('Войти')")
                if btn.count() > 0: btn.first.tap()
                else: page.locator("input[name='password']").press("Enter")
                
                time.sleep(5)

                if page.is_visible("input[name='code']"):
                    bot_status["step"] = "WAITING_FOR_CODE"
                    bot_status["needs_code"] = True
                    take_screenshot(page, "Code_Required")
                    while shared_data["otp_code"] is None:
                        time.sleep(2)
                        if not bot_status["is_running"]: return
                    
                    page.fill("input[name='code']", shared_data["otp_code"])
                    page.locator("input[name='code']").press("Enter")
                    time.sleep(8)
            
            take_screenshot(page, "Login_Done")
            process_youtube_tasks(context, page)
            bot_status["step"] = "Finished."

        except Exception as e:
            bot_status["step"] = f"Error: {str(e)}"
            print(f"Critical: {e}")
            try: take_screenshot(page, "error")
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
    t = threading.Thread(target=run_single_account, args=(data.get('username'), data.get('password')))
    t.start()
    return jsonify({"status": "Started"})

@app.route('/status')
def status(): return jsonify(bot_status)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
