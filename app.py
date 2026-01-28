import os
import time
import json
import threading
import random
import shutil
import datetime
from flask import Flask, render_template, request, jsonify, send_file

app = Flask(__name__)

# --- Configuration ---
SCREENSHOT_DIR = "static/screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)
USER_DATA_DIR = "/app/browser_data2"
DEBUG_FILE = "debug_source.html"

# --- Shared State ---
shared_data = {"otp_code": None}
current_browser_context = None

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

# --- CONTINUOUS LOGGING (New Feature Kept) ---
def save_debug_html(page, step_name):
    try:
        content = page.content()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        separator = f"""
        \n\n<div style="background:#111;color:#0f0;padding:15px;margin:20px;border:3px solid #0f0;font-family:monospace;">
            🖥️ ACTION: {step_name} <br> 🕒 TIME: {timestamp}
        </div>\n\n"""
        with open(DEBUG_FILE, "a", encoding="utf-8") as f:
            f.write(separator + content)
    except: pass

def reset_debug_log():
    try:
        with open(DEBUG_FILE, "w", encoding="utf-8") as f:
            f.write("<h1>🤖 AVISO BOT LOG (OLD CONFIG)</h1>")
    except: pass

# --- JS SCANNER ---
def get_best_task_via_js(page):
    return page.evaluate("""() => {
        const tables = Array.from(document.querySelectorAll('table[id^="ads-link-"]'));
        for (let table of tables) {
            if (table.offsetParent === null) continue;
            const rect = table.getBoundingClientRect();
            if (rect.height === 0 || rect.width === 0) continue; 
            const style = window.getComputedStyle(table);
            if (style.display === 'none' || style.visibility === 'hidden') continue;

            const idPart = table.id.replace('ads-link-', '');
            if (!table.querySelector('.ybprosm')) continue;

            const timerInput = document.getElementById('ads_timer_' + idPart);
            const duration = timerInput ? parseInt(timerInput.value) : 20;
            
            return {
                id: idPart,
                duration: duration,
                tableId: table.id,
                startSelector: '#link_ads_start_' + idPart,
                confirmSelector: '#ads_btn_confirm_' + idPart
            };
        }
        return null; 
    }""")

# --- PROCESS TASKS ---
def process_youtube_tasks(context, page):
    bot_status["step"] = "Checking Tasks..."
    page.goto("https://aviso.bz/tasks-youtube")
    page.wait_for_load_state("networkidle")
    
    if page.is_visible("input[name='username']"): return

    page.evaluate("if(document.getElementById('clouse_adblock')) document.getElementById('clouse_adblock').remove();")
    save_debug_html(page, "Tasks_Loaded")
    take_screenshot(page, "0_Task_List")

    for i in range(1, 31): 
        if not bot_status["is_running"]: break
        
        bot_status["step"] = f"Task #{i} Scan..."
        task_data = get_best_task_via_js(page)
        
        if not task_data:
            print("No tasks.")
            save_debug_html(page, "No_Tasks_Found")
            bot_status["step"] = "No Tasks Visible."
            break
            
        print(f"Task: {task_data['id']} ({task_data['duration']}s)")
        
        try:
            page.evaluate(f"document.getElementById('{task_data['tableId']}').scrollIntoView({{behavior: 'smooth', block: 'center'}});")
            time.sleep(1)
            take_screenshot(page, f"Task_{i}_Target")

            # START
            initial_pages = len(context.pages)
            
            # Simple Click (Like Old Bot)
            page.click(task_data['startSelector'])
            
            time.sleep(5)
            if len(context.pages) == initial_pages:
                # Retry
                page.evaluate(f"document.querySelector('{task_data['startSelector']}').click();")
                time.sleep(5)
                if len(context.pages) == initial_pages:
                    page.reload()
                    continue

            new_page = context.pages[-1]
            new_page.wait_for_load_state("domcontentloaded")
            new_page.bring_to_front()
            
            # Simple Play Check
            time.sleep(2)
            try:
                if new_page.is_visible("button:has-text('Я ознакомлен')"):
                    new_page.click("button:has-text('Я ознакомлен')")
            except: pass

            try:
                new_page.keyboard.press("Space")
            except: pass

            take_screenshot(new_page, f"Task_{i}_Video")
            
            wait_time = task_data['duration'] + random.randint(5, 10)
            for sec in range(wait_time):
                if not bot_status["is_running"]: 
                    new_page.close()
                    return
                if sec % 5 == 0: 
                    bot_status["step"] = f"Watching... {sec}/{wait_time}s"
                time.sleep(1)

            new_page.close()
            page.bring_to_front()
            time.sleep(1)
            take_screenshot(page, f"Task_{i}_Back")

            confirm_selector = task_data['confirmSelector']
            bot_status["step"] = "Confirming..."
            
            if page.is_visible(confirm_selector):
                page.click(confirm_selector)
                time.sleep(5)
                take_screenshot(page, f"Task_{i}_Success")
                bot_status["step"] = f"Task #{i} Done!"
                save_debug_html(page, f"Task_{i}_Success")
            else:
                page.reload()
                time.sleep(3)
                break

        except Exception as e:
            print(f"Error: {e}")
            try: context.pages[-1].close() if len(context.pages) > 1 else None
            except: pass
            page.reload()
            time.sleep(5)
            break

    if bot_status["is_running"]:
        page.goto("https://aviso.bz/logout")

# --- MAIN RUNNER (EXACT OLD CONFIG) ---
def run_infinite_loop(username, password):
    global bot_status, shared_data, current_browser_context
    from playwright.sync_api import sync_playwright

    reset_debug_log()
    bot_status["is_running"] = True
    bot_status["needs_code"] = False
    shared_data["otp_code"] = None

    with sync_playwright() as p:
        while bot_status["is_running"]:
            try:
                # --- EXACT OLD CONFIGURATION ---
                # ہم نے وہ تمام فالتو ہیڈرز ہٹا دیے ہیں جو نئی فائل میں تھے
                context = p.chromium.launch_persistent_context(
                    USER_DATA_DIR,
                    headless=True,
                    # یہی سیٹنگز پرانی فائل میں تھیں 👇
                    args=[
                        "--lang=en-US",
                        "--no-sandbox",
                        "--disable-setuid-sandbox",
                        "--disable-dev-shm-usage",
                        "--start-maximized"
                    ],
                    viewport={"width": 1280, "height": 800} 
                )
                current_browser_context = context
                
                page = context.new_page()
                # NO APPLY_STEALTH CALL HERE (Old code didn't have it)
                
                bot_status["step"] = "Opening Site..."
                page.goto("https://aviso.bz/login", timeout=60000)
                page.wait_for_load_state("networkidle")
                save_debug_html(page, "Login_Page")
                
                if page.is_visible("input[name='username']"):
                    # --- EXACT OLD LOGIN LOGIC ---
                    print("Not logged in. Logging in...")
                    bot_status["step"] = "Filling Form..."
                    
                    page.fill("input[name='username']", username)
                    page.fill("input[name='password']", password)
                    take_screenshot(page, "Credentials_Filled")
                    
                    bot_status["step"] = "Pressing Enter..."
                    # پرانی فائل میں صرف انٹر پریس ہو رہا تھا
                    page.locator("input[name='password']").press("Enter")
                    
                    time.sleep(5)
                    take_screenshot(page, "Login_Result")
                    save_debug_html(page, "Login_Result")

                    # OTP Check (From Old File)
                    if page.is_visible("input[name='code']"):
                        bot_status["step"] = "WAITING_FOR_CODE"
                        bot_status["needs_code"] = True
                        take_screenshot(page, "Code_Required")
                        
                        while shared_data["otp_code"] is None:
                            time.sleep(2)
                            if not bot_status["is_running"]: break
                        
                        if shared_data["otp_code"]:
                            page.fill("input[name='code']", shared_data["otp_code"])
                            page.locator("input[name='code']").press("Enter")
                            time.sleep(5)
                            bot_status["needs_code"] = False
                            shared_data["otp_code"] = None

                    # Verification
                    if page.is_visible("input[name='username']"):
                        print("Login failed.")
                        bot_status["step"] = "Login Failed. Retrying..."
                        context.close()
                        continue
                
                bot_status["step"] = "Login Success!"
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
        if os.path.exists(USER_DATA_DIR):
            shutil.rmtree(USER_DATA_DIR)
            os.makedirs(USER_DATA_DIR, exist_ok=True)
            return jsonify({"status": "Data Wiped Successfully"})
        else: return jsonify({"status": "No Data Found"})
    except Exception as e: return jsonify({"status": f"Error: {str(e)}"})

@app.route('/status')
def status(): return jsonify(bot_status)

@app.route('/download_log')
def download_log():
    if os.path.exists(DEBUG_FILE): return send_file(DEBUG_FILE, as_attachment=True)
    else: return "Log not found", 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
