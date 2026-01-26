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

def force_google_translate_click(page):
    try:
        translate_bar_btn = "#google_translate_element a.goog-te-menu-value"
        if page.is_visible(translate_bar_btn):
            page.click(translate_bar_btn)
            time.sleep(2)
    except:
        pass

def take_screenshot(page, name):
    try:
        timestamp = int(time.time())
        filename = f"{timestamp}_{name}.png"
        path = os.path.join(SCREENSHOT_DIR, filename)
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
            
            // Check if it's a video task (class ybprosm)
            const isVideo = task.querySelector('.ybprosm') !== null;
            if (!isVideo) return null;

            // Get Timer
            const timerInput = document.getElementById('ads_timer_' + idPart);
            const duration = timerInput ? parseInt(timerInput.value) : 20;

            // Get Price
            const priceEl = task.querySelector('span[title="Стоимость просмотра"]');
            const price = priceEl ? parseFloat(priceEl.innerText) : 0;

            return {
                id: idPart,
                duration: duration,
                price: price,
                tableId: task.id,
                startSelector: '#link_ads_start_' + idPart,
                confirmSelector: '#ads_btn_confirm_' + idPart
            };
        }).filter(item => item !== null);

        // Sort by Price High to Low
        data.sort((a, b) => b.price - a.price);
        return data.length > 0 ? data[0] : null;
    }""")

# --- PROCESS LOGIC ---
def process_youtube_tasks(context, page):
    bot_status["step"] = "Opening Tasks Page..."
    page.goto("https://aviso.bz/tasks-youtube")
    page.wait_for_load_state("networkidle")
    take_screenshot(page, "0_Main_List")

    for i in range(1, 21): # Do 20 tasks
        if not bot_status["is_running"]: break
        
        bot_status["step"] = f"Scanning Task #{i}..."
        
        # 1. Get Best Task
        task_data = get_best_task_via_js(page)
        
        if not task_data:
            print("No video tasks found via JS. Reloading...")
            page.reload()
            time.sleep(5)
            continue
            
        print(f"TASK FOUND: ID={task_data['id']}, Time={task_data['duration']}s")
        bot_status["step"] = f"Task #{i}: {task_data['duration']}s video found"

        try:
            # --- PROOF 1: BEFORE START (RED BORDER) ---
            # ہم ٹاسک کے گرد لال بارڈر لگائیں گے تاکہ اسکرین شاٹ میں صاف پتہ چلے
            page.evaluate(f"document.getElementById('{task_data['tableId']}').style.border = '5px solid red';")
            page.evaluate(f"document.getElementById('{task_data['tableId']}').scrollIntoView({{block: 'center'}});")
            time.sleep(1)
            
            # Screenshot 1: "یہ والا ٹاسک کر رہا ہوں"
            take_screenshot(page, f"Task_{i}_1_Target_Locked")

            # --- ACTION 1: CLICK START ---
            start_selector = task_data['startSelector']
            
            with context.expect_page() as new_page_info:
                page.click(start_selector)
            
            new_page = new_page_info.value
            new_page.wait_for_load_state("domcontentloaded")
            
            # --- ACTION 2: WATCH VIDEO ---
            new_page.bring_to_front()
            
            # Timer + Random Buffer
            actual_wait = task_data['duration'] + random.randint(5, 8)
            
            bot_status["step"] = f"Watching Video ({actual_wait}s)..."
            
            # Waiting loop
            remaining = actual_wait
            while remaining > 0:
                if not bot_status["is_running"]: 
                    new_page.close()
                    return
                time.sleep(1)
                remaining -= 1
            
            new_page.close()
            
            # --- ACTION 3: CONFIRM ---
            page.bring_to_front()
            bot_status["step"] = "Confirming Task..."
            
            # Wait for button visibility
            confirm_selector = task_data['confirmSelector']
            
            # Retry finding button loop
            btn_found = False
            for _ in range(5):
                if page.is_visible(confirm_selector):
                    btn_found = True
                    break
                time.sleep(1)
            
            if btn_found:
                page.click(confirm_selector)
                print("Confirm clicked!")
                
                bot_status["step"] = "Waiting for money message..."
                time.sleep(5) # Wait for success message animation
                
                # --- PROOF 2: AFTER SUCCESS ---
                # Screenshot 2: "پیسے مل گئے"
                take_screenshot(page, f"Task_{i}_2_Money_Added")
                
                bot_status["step"] = f"Task #{i} Completed Successfully!"
            else:
                print("Confirm button missing")
                take_screenshot(page, f"Task_{i}_Error_NoButton")
                page.reload() # Refresh to fix glitches

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
                args=[
                    "--lang=en-US",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--start-maximized"
                ],
                viewport={"width": 1280, "height": 800}
            )
            
            page = context.new_page()
            
            bot_status["step"] = "Checking Login..."
            page.goto("https://aviso.bz/tasks-youtube", timeout=60000)
            page.wait_for_load_state("networkidle")
            
            if "login" in page.url:
                print("Need login...")
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
            
            take_screenshot(page, "Ready_To_Start")
            process_youtube_tasks(context, page)

        except Exception as e:
            bot_status["step"] = f"Error: {str(e)}"
            print(f"Critical: {e}")
            try: take_screenshot(page, "error_state")
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