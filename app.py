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
USER_DATA_DIR = "/app/browser_data2"

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

# --- MOBILE STEALTH (Redmi 14C) ---
def apply_mobile_stealth(page):
    try:
        page.add_init_script("""
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
            Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 5 });
            window.ontouchstart = true;
        """)
    except: pass

# --- ADVANCED JS SCANNER ---
def get_all_tasks_via_js(page):
    return page.evaluate("""() => {
        // تمام ٹاسک ٹیبلز کو اٹھائیں
        const tasks = Array.from(document.querySelectorAll('table[id^="ads-link-"], div[id^="ads-link-"]'));
        
        const data = tasks.map(task => {
            const idPart = task.id.replace('ads-link-', '');
            
            // چیک کریں کہ کیا یہ ویڈیو ہے (ybprosm کلاس)
            const isVideo = task.querySelector('.ybprosm') !== null;
            if (!isVideo) return null;

            // ٹائمر کی ویلیو html سے نکالیں (آپ کے دیے گئے کوڈ کے مطابق)
            const timerInput = document.getElementById('ads_timer_' + idPart);
            const duration = timerInput ? parseInt(timerInput.value) : 20;

            // پرائس نکالیں
            const priceEl = task.querySelector('span[title="Стоимость просмотра"], .price-text');
            const price = priceEl ? parseFloat(priceEl.innerText) : 0;

            return {
                id: idPart,
                price: price,
                duration: duration,
                tableId: task.id,
                startSelector: '#link_ads_start_' + idPart,
                confirmSelector: '#ads_btn_confirm_' + idPart,
                errorSelector: '#btn_error_view_' + idPart,
                wrapperSelector: '#ads_checking_btn_' + idPart // یہ وہ div ہے جو display:none ہوتا ہے
            };
        }).filter(item => item !== null);

        // ترتیب: پہلے چھوٹے ٹاسک، پھر بڑے۔
        data.sort((a, b) => a.duration - b.duration);
        return data;
    }""")

# --- AUTO PLAY HELPER ---
def ensure_video_playing(new_page):
    try:
        # YouTube Mobile Play Button
        play_btn = new_page.locator(".ytp-large-play-button, .html5-video-player")
        if play_btn.count() > 0:
            play_btn.first.tap()
        else:
            # Center Tap fallback
            vp = new_page.viewport_size
            if vp: new_page.mouse.click(vp['width']/2, vp['height']/2)
    except: pass

# --- PROCESS TASKS ---
def process_youtube_tasks(context, page):
    bot_status["step"] = "Checking Tasks..."
    page.goto("https://aviso.bz/tasks-youtube")
    page.wait_for_load_state("networkidle")
    
    # Remove AdBlock Warning
    page.evaluate("if(document.getElementById('clouse_adblock')) document.getElementById('clouse_adblock').remove();")
    
    take_screenshot(page, "0_List_Loaded")

    # ایک بار میں سارے ٹاسک کی لسٹ لے لیں
    all_tasks = get_all_tasks_via_js(page)
    
    if not all_tasks:
        print("No tasks found.")
        bot_status["step"] = "No Tasks Found."
        return

    print(f"Found {len(all_tasks)} tasks to process.")
    
    for i, task_data in enumerate(all_tasks, 1):
        if not bot_status["is_running"]: break
        
        bot_status["step"] = f"Task {i}/{len(all_tasks)}: {task_data['duration']}s Video"
        print(f"Processing Task ID: {task_data['id']} ({task_data['duration']}s)")

        try:
            # 1. Scroll to Task
            page.evaluate(f"document.getElementById('{task_data['tableId']}').scrollIntoView({{block: 'center'}});")
            page.evaluate(f"document.getElementById('{task_data['tableId']}').style.border = '3px solid red';")
            time.sleep(1)
            take_screenshot(page, f"Task_{i}_1_Target")

            # 2. Click Start (Open New Tab)
            with context.expect_page() as new_page_info:
                page.tap(task_data['startSelector'])
            
            new_page = new_page_info.value
            apply_mobile_stealth(new_page)
            new_page.wait_for_load_state("domcontentloaded")
            new_page.bring_to_front()
            
            # 3. Play Video & Handle Obstacles
            time.sleep(2)
            try:
                blocker = new_page.locator("button:has-text('Я ознакомлен'), a:has-text('Приступить')")
                if blocker.count() > 0 and blocker.first.is_visible():
                    blocker.first.tap()
                    time.sleep(2)
            except: pass

            ensure_video_playing(new_page)
            take_screenshot(new_page, f"Task_{i}_2_Video")

            # 4. SMART WAIT (The Fix)
            # ہم ٹائمر کا انتظار کریں گے، لیکن ساتھ ساتھ Aviso کے مین پیج کو چیک کرتے رہیں گے
            # کہ بٹن ظاہر ہوا یا نہیں۔
            
            wait_limit = task_data['duration'] + 30 # Buffer time
            confirm_ready = False
            
            for sec in range(wait_limit):
                if not bot_status["is_running"]: 
                    new_page.close()
                    return

                # Keep Video Active
                try: new_page.touchscreen.tap(100, 200)
                except: pass
                
                # Check Main Page for Button Visibility
                # ہم چیک کریں گے کہ کیا کنفرم بٹن اب نظر آ رہا ہے؟
                is_visible = page.evaluate(f"""() => {{
                    const btn = document.querySelector('{task_data['confirmSelector']}');
                    const wrapper = document.querySelector('{task_data['wrapperSelector']}');
                    
                    // اگر ریپر کا display 'none' نہیں ہے، یا بٹن نظر آ رہا ہے
                    if (btn && btn.offsetParent !== null) return true;
                    if (wrapper && wrapper.style.display !== 'none') return true;
                    return false;
                }}""")

                if is_visible:
                    print("Timer Finished! Button is visible.")
                    confirm_ready = True
                    break
                
                if sec % 5 == 0:
                    bot_status["step"] = f"Watching... {sec}/{task_data['duration']}s"
                time.sleep(1)

            # 5. Confirm
            new_page.close()
            page.bring_to_front()
            
            if confirm_ready:
                # Human Delay
                time.sleep(random.randint(2, 4))
                bot_status["step"] = "Clicking Confirm..."
                
                # کلک کریں
                page.tap(task_data['confirmSelector'])
                
                # کامیابی کا انتظار
                time.sleep(5)
                take_screenshot(page, f"Task_{i}_3_Success")
                bot_status["step"] = f"Task {i} Done!"
            else:
                print("Task timed out. Button never appeared.")
                bot_status["step"] = "Task Failed (Timeout)"
                # اگر ایک ٹاسک فیل ہو تو پیج ریفریش کر لو تاکہ اگلا صحیح چلے
                page.reload()
                time.sleep(5)
                # ریفریش کے بعد لسٹ دوبارہ لینی پڑے گی، اس لیے لوپ بریک کریں
                break 

        except Exception as e:
            print(f"Task Failed: {e}")
            try: new_page.close() 
            except: pass
            page.reload()
            break

    # --- AUTO LOGOUT ---
    if bot_status["is_running"]:
        print("Cycle ending. Logging out...")
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
                    btn = page.locator("button[type='submit']")
                    if btn.count() > 0: btn.first.tap()
                    else: page.locator("input[name='password']").press("Enter")
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
                        page.locator("input[name='code']").press("Enter")
                        time.sleep(8)
                        bot_status["needs_code"] = False
                
                take_screenshot(page, "Login_Success")
                process_youtube_tasks(context, page)
                
                context.close()
                
                # Sleep Loop
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
    if bot_status["is_running"]: return jsonify({"status": "Running"})
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

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
