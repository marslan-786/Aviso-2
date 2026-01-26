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
        # full_page=False کیونکہ ہمیں صرف نظر آنے والا حصہ چاہیے
        page.screenshot(path=path)
        bot_status["images"].append(filename)
    except Exception as e:
        print(f"Screenshot failed: {e}")

# --- JAVASCRIPT INTELLIGENCE ---
def get_best_task_via_js(page):
    return page.evaluate("""() => {
        const tasks = Array.from(document.querySelectorAll('table[id^="ads-link-"]'));
        const data = tasks.map(task => {
            const idPart = task.id.replace('ads-link-', '');
            const isVideo = task.querySelector('.ybprosm') !== null;
            if (!isVideo) return null;

            const timerId = 'timer_ads_' + idPart;
            const priceEl = task.querySelector('span[title="Стоимость просмотра"]');
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
    bot_status["step"] = "Opening Tasks Page..."
    page.goto("https://aviso.bz/tasks-youtube")
    page.wait_for_load_state("networkidle")
    
    # Remove AdBlock warning if exists
    page.evaluate("if(document.getElementById('clouse_adblock')) document.getElementById('clouse_adblock').remove();")

    for i in range(1, 25): 
        if not bot_status["is_running"]: break
        
        bot_status["step"] = f"Scanning Task #{i}..."
        task_data = get_best_task_via_js(page)
        
        if not task_data:
            print("No video tasks found via JS. Reloading...")
            page.reload()
            time.sleep(5)
            continue
            
        print(f"TASK FOUND: ID={task_data['id']}")
        bot_status["step"] = f"Task #{i}: ID {task_data['id']} started"

        try:
            # Highlight Target (Red Box)
            page.evaluate(f"document.getElementById('{task_data['tableId']}').style.border = '4px solid red';")
            page.evaluate(f"document.getElementById('{task_data['tableId']}').scrollIntoView({{block: 'center'}});")
            time.sleep(1)
            take_screenshot(page, f"Task_{i}_0_Target_Locked")

            # --- ACTION 1: CLICK START ---
            start_selector = task_data['startSelector']
            
            with context.expect_page() as new_page_info:
                page.click(start_selector)
            
            new_page = new_page_info.value
            new_page.wait_for_load_state("domcontentloaded")
            
            # --- ACTION 2: SMART SYNC WATCHING ---
            new_page.bring_to_front()
            print("Video tab opened. Syncing...")
            
            # --- NEW: SCREENSHOTS FOR PROOF ---
            time.sleep(3) # ویڈیو لوڈ ہونے کا تھوڑا انتظار
            
            # 1. ویڈیو پیج کا ثبوت
            bot_status["step"] = "Capturing Video Page..."
            take_screenshot(new_page, f"Task_{i}_1_Video_Playing_Proof")
            
            # 2. مین پیج (ٹائمر) کا ثبوت
            # ہم فوکس ویڈیو پیج پر ہی رکھیں گے، لیکن تصویر بیک گراؤنڈ پیج کی لیں گے
            bot_status["step"] = "Checking Timer on Main Page..."
            take_screenshot(page, f"Task_{i}_2_Timer_Running_Check")
            
            # ----------------------------------

            max_wait = 90 # Maximum wait time
            timer_finished = False
            
            for tick in range(max_wait):
                if not bot_status["is_running"]: 
                    new_page.close()
                    return
                
                # Mouse Movement on Video Page
                try:
                    new_page.mouse.move(random.randint(100, 500), random.randint(100, 500))
                except: pass

                # Check Status on Main Page (Background)
                status_check = page.evaluate(f"""() => {{
                    const btn = document.querySelector('{task_data['confirmSelector']}');
                    const err = document.querySelector('{task_data['errorSelector']}');
                    
                    if (err && err.offsetParent !== null) return {{ status: 'error', text: err.innerText }};
                    if (btn && btn.offsetParent !== null) return {{ status: 'done' }};
                    return {{ status: 'waiting' }};
                }}""")

                if status_check['status'] == 'error':
                    print(f"Error detected: {status_check['text']}")
                    take_screenshot(page, f"Task_{i}_ErrorMsg")
                    break 
                
                if status_check['status'] == 'done':
                    print("Timer finished! Confirm button visible.")
                    timer_finished = True
                    break
                
                time.sleep(1)
                if tick % 5 == 0: bot_status["step"] = f"Watching... {tick}s elapsed"

            # --- ACTION 3: CLOSE & CONFIRM ---
            new_page.close()
            page.bring_to_front()
            
            if timer_finished:
                bot_status["step"] = "Clicking Confirm..."
                
                # کنفرم بٹن پر کلک کرنے سے پہلے ایک اور ثبوت
                take_screenshot(page, f"Task_{i}_3_Confirm_Button_Ready")
                
                page.click(task_data['confirmSelector'])
                time.sleep(4) # پیسے ایڈ ہونے کا انتظار
                
                # فائنل ثبوت
                take_screenshot(page, f"Task_{i}_4_Money_Added_Success")
                bot_status["step"] = f"Task #{i} Completed! Money Added."
            else:
                print("Task timed out")
                bot_status["step"] = "Task Timeout/Skipped"
                page.reload()

        except Exception as e:
            print(f"Task failed: {e}")
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
            context = p.chromium.launch_persistent_context(
                USER_DATA_DIR,
                headless=True,
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                args=[
                    "--lang=en-US",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--start-maximized",
                    "--disable-blink-features=AutomationControlled"
                ],
                viewport={"width": 1366, "height": 768}
            )
            
            page = context.new_page()
            
            bot_status["step"] = "Opening Site..."
            page.goto("https://aviso.bz/tasks-youtube", timeout=60000)
            page.wait_for_load_state("networkidle")
            
            if "login" in page.url:
                print("Logging in...")
                page.goto("https://aviso.bz/login")
                page.fill("input[name='username']", username)
                page.fill("input[name='password']", password)
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
                    page.locator("input[name='code']").press("Enter")
                    time.sleep(8)
            
            take_screenshot(page, "Dashboard_Ready")
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