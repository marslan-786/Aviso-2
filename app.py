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

# --- MOBILE STEALTH ---
def apply_mobile_stealth(page):
    try:
        page.add_init_script("""
            Object.defineProperty(navigator, 'hardwareConcurrency', { get: () => 8 });
            Object.defineProperty(navigator, 'maxTouchPoints', { get: () => 5 });
            window.ontouchstart = true;
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

            const timerInput = document.getElementById('ads_timer_' + idPart);
            const duration = timerInput ? parseInt(timerInput.value) : 15;
            const priceEl = task.querySelector('span[title="Стоимость просмотра"], .price-text');
            const price = priceEl ? parseFloat(priceEl.innerText) : 0;

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

        data.sort((a, b) => a.price - b.price); // Smallest First
        return data.length > 0 ? data[0] : null;
    }""")

# --- AUTO PLAY ---
def ensure_video_playing(new_page):
    try:
        play_btn = new_page.locator(".ytp-large-play-button, button[aria-label='Play']")
        if play_btn.count() > 0 and play_btn.first.is_visible():
            play_btn.first.tap()
        else:
            vp = new_page.viewport_size
            if vp: new_page.mouse.click(vp['width']/2, vp['height']/2)
    except: pass

# --- PROCESS LOGIC ---
def process_youtube_tasks(context, page):
    bot_status["step"] = "Checking Tasks..."
    page.goto("https://aviso.bz/tasks-youtube")
    page.wait_for_load_state("networkidle")
    
    page.evaluate("if(document.getElementById('clouse_adblock')) document.getElementById('clouse_adblock').remove();")
    take_screenshot(page, "Task_List")

    tasks_found = False
    for i in range(1, 31): 
        if not bot_status["is_running"]: break
        
        bot_status["step"] = f"Finding Task #{i}..."
        task_data = get_best_task_via_js(page)
        
        if not task_data:
            if not tasks_found:
                print("No tasks available.")
                bot_status["step"] = "No Tasks Found."
            else:
                bot_status["step"] = "All Tasks Done."
            break
            
        tasks_found = True
        print(f"Task: {task_data['id']} | Time: {task_data['duration']}s")
        bot_status["step"] = f"Task #{i}: Starting..."

        try:
            # Highlight
            page.evaluate(f"document.getElementById('{task_data['tableId']}').style.border = '4px solid red';")
            page.evaluate(f"document.getElementById('{task_data['tableId']}').scrollIntoView({{block: 'center'}});")
            time.sleep(1)
            take_screenshot(page, f"Task_{i}_Target")

            # Start
            with context.expect_page() as new_page_info:
                page.tap(task_data['startSelector'])
            
            new_page = new_page_info.value
            apply_mobile_stealth(new_page) 
            new_page.wait_for_load_state("domcontentloaded")
            new_page.bring_to_front()
            
            # Play & Wait
            time.sleep(2)
            # Handle obstacles like VPN warning
            try:
                blocker = new_page.locator("button:has-text('Я ознакомлен'), a.tr_but_b")
                if blocker.count() > 0 and blocker.first.is_visible():
                    blocker.first.tap()
                    time.sleep(2)
            except: pass

            ensure_video_playing(new_page)
            take_screenshot(new_page, f"Task_{i}_Video")
            
            # Exact Timer Loop
            wait_time = task_data['duration'] + 2 
            timer_finished = False
            
            for tick in range(wait_time + 15): 
                if not bot_status["is_running"]: 
                    new_page.close()
                    return
                
                status = page.evaluate(f"""() => {{
                    const btn = document.querySelector('{task_data['confirmSelector']}');
                    if (btn && btn.offsetParent !== null) return 'done';
                    return 'wait';
                }}""")
                
                if status == 'done':
                    timer_finished = True
                    break
                
                time.sleep(1)
                if tick % 5 == 0: bot_status["step"] = f"Watching... {tick}/{wait_time}s"

            new_page.close()
            page.bring_to_front()
            
            if timer_finished:
                # Random human delay 5-10s
                wait_human = random.randint(5, 10)
                bot_status["step"] = f"Waiting {wait_human}s..."
                for _ in range(wait_human):
                    if not bot_status["is_running"]: return
                    time.sleep(1)

                page.tap(task_data['confirmSelector'])
                time.sleep(4)
                take_screenshot(page, f"Task_{i}_Success")
            else:
                page.reload()

        except Exception as e:
            print(f"Task error: {e}")
            try: new_page.close() 
            except: pass
            page.reload()
            time.sleep(5)

# --- MAIN LOOP RUNNER ---
def run_infinite_loop(username, password):
    global bot_status, shared_data
    from playwright.sync_api import sync_playwright

    bot_status["is_running"] = True
    bot_status["needs_code"] = False
    shared_data["otp_code"] = None

    with sync_playwright() as p:
        # اس لوپ کی وجہ سے بوٹ کبھی بند نہیں ہوگا
        while bot_status["is_running"]:
            try:
                bot_status["step"] = "Launching Browser..."
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
                
                # 1. Login Logic
                bot_status["step"] = "Logging In..."
                page.goto("https://aviso.bz/login", timeout=60000)
                
                # Check if already logged in (cookies)
                if page.url != "https://aviso.bz/login" and not page.is_visible("input[name='username']"):
                     print("Already logged in.")
                else:
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

                take_screenshot(page, "Login_Done")
                
                # 2. Perform Tasks
                process_youtube_tasks(context, page)
                
                # 3. Logout Logic
                if bot_status["is_running"]:
                    bot_status["step"] = "Logging Out..."
                    page.goto("https://aviso.bz/logout")
                    time.sleep(3)
                    take_screenshot(page, "Logged_Out")
                    
                    # 4. Wait for 1 Hour (Interruptible)
                    print("Cycle finished. Waiting 1 hour...")
                    context.close() # Close browser to save RAM
                    
                    wait_seconds = 3600 # 1 Hour
                    for s in range(wait_seconds):
                        if not bot_status["is_running"]: 
                            print("Stop command received.")
                            return
                        remaining = wait_seconds - s
                        # ہر 10 سیکنڈ بعد سٹیٹس اپ ڈیٹ کریں
                        if s % 10 == 0:
                            mins = remaining // 60
                            secs = remaining % 60
                            bot_status["step"] = f"💤 Sleeping... Next Run in {mins}m {secs}s"
                        time.sleep(1)
                else:
                    context.close()
                    return

            except Exception as e:
                bot_status["step"] = f"Error: {str(e)}"
                print(f"Cycle crashed: {e}")
                time.sleep(30) # Error wait

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

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
