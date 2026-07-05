import os
import re
import time
import json
import threading
import random
import shutil
import datetime
import subprocess
import requests
from flask import Flask, render_template, request, jsonify, send_file, make_response

app = Flask(__name__)

# --- Configuration ---
SCREENSHOT_DIR = "static/screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)
USER_DATA_DIR = "/app/browser_data"
DEBUG_FILE = "debug_source.html"
PROXY_FILE = "proxy_config.txt"
COOKIES_FILE = "youtube_cookies.json"
PROCESSED_TASKS_FILE = "processed_tasks.txt"

# --- Telegram Configuration ---
TELEGRAM_BOT_TOKEN = "7766363398:AAFEfLCKw4jTOqMyTv6baeE5XGCfjHKClFc"  
TELEGRAM_CHAT_ID = "-1004480322983"      

# --- Shared State ---
shared_data = {"otp_code": None}
current_browser_context = None

bot_status = {
    "step": "Idle",
    "images": [],
    "logs": [],  # <-- فرنٹ اینڈ کنسول کے لاگز یہاں سیو ہوں گے
    "is_running": False,
    "needs_code": False,
    "proxy_status": "Direct IP"
}

# --- HELPER FUNCTIONS ---
def log_msg(msg):
    """Prints logs to terminal and sends them directly to the HTML Front-end console."""
    timestamp = datetime.datetime.now().strftime('%H:%M:%S')
    log_line = f"[{timestamp}] {msg}"
    print(log_line)
    bot_status["logs"].append(log_line)
    if len(bot_status["logs"]) > 40:  # زیادہ سے زیادہ 40 لاگز ہسٹری میں رکھے گا
        bot_status["logs"].pop(0)

def load_processed_tasks():
    if os.path.exists(PROCESSED_TASKS_FILE):
        with open(PROCESSED_TASKS_FILE, "r") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_processed_task(task_id):
    with open(PROCESSED_TASKS_FILE, "a") as f:
        f.write(f"{task_id}\n")

def get_proxy_config():
    if os.path.exists(PROXY_FILE):
        try:
            with open(PROXY_FILE, "r") as f:
                proxy_str = f.read().strip()
                if not proxy_str: return None
                parts = proxy_str.split(":")
                proxy_dict = {"server": f"http://{parts[0]}:{parts[1]}"}
                if len(parts) == 4:
                    proxy_dict["username"] = parts[2]
                    proxy_dict["password"] = parts[3]
                return proxy_dict
        except: return None
    return None

def kill_all_browsers():
    try:
        subprocess.run(["pkill", "-9", "chrome"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["pkill", "-9", "chromium"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(1)
    except: pass

def take_screenshot(page, name):
    try:
        if page.is_closed(): return
        timestamp = int(time.time())
        filename = f"{timestamp}_{name}.png"
        path = os.path.join(SCREENSHOT_DIR, filename)
        page.screenshot(path=path)
        bot_status["images"].append(filename)
    except: pass

def save_debug_html(page, step_name):
    try:
        if not page.is_closed():
            content = page.content()
            with open(DEBUG_FILE, "a", encoding="utf-8") as f:
                f.write(f"\n\n\n{content}")
    except: pass

def reset_debug_log():
    try:
        with open(DEBUG_FILE, "w", encoding="utf-8") as f:
            f.write("<h1>🖱️ AVISO BOT LOGS</h1>")
    except: pass

def inject_youtube_cookies(context):
    if os.path.exists(COOKIES_FILE):
        try:
            with open(COOKIES_FILE, "r", encoding="utf-8") as f:
                cookies = json.load(f)
                context.add_cookies(cookies)
            log_msg("🍪 YouTube Cookies Injected Successfully!")
        except Exception as e:
            log_msg(f"⚠️ Error loading cookies: {e}")
    else:
        log_msg("⚠️ youtube_cookies.json file not found.")

def perform_human_mouse_click(page, selector, screenshot_name):
    try:
        if page.is_closed() or not page.is_visible(selector): return False
        box = page.locator(selector).bounding_box()
        if box:
            x = box['x'] + box['width'] / 2 + random.uniform(-15, 15)
            y = box['y'] + box['height'] / 2 + random.uniform(-5, 5)
            page.mouse.move(x, y, steps=15) 
            time.sleep(0.3)
            page.mouse.down()
            time.sleep(random.uniform(0.05, 0.15))
            page.mouse.up()
            return True
    except: pass
    return False

# --- JS SCANNERS (2 RUBLES LOCK) ---
def get_high_value_tasks_via_js(page):
    return page.evaluate("""() => {
        const targetTasks = [];
        const rows = document.querySelectorAll('table#work-task tr[id*="block-task"]');
        rows.forEach(row => {
            const linkEl = row.querySelector('a.earn-task__title-link');
            if (!linkEl) return;
            const href = linkEl.getAttribute('href');
            const idMatch = href.match(/adv=(\d+)/);
            const taskId = idMatch ? idMatch[1] : null;
            const priceEl = row.querySelector('td[style*="text-align: right"] span, td[style*="padding-right"] span');
            let price = 0.0;
            if (priceEl) {
                const priceText = priceEl.innerText || priceEl.textContent;
                const cleanPrice = priceText.match(/([\d\.,]+)\s*руб/);
                if (cleanPrice) { price = parseFloat(cleanPrice[1].replace(',', '.')); }
            }
            if (taskId && price >= 2.0) {
                targetTasks.push({ id: taskId, price: price, url: 'https://aviso.bz' + href });
            }
        });
        return targetTasks;
    }""")

def extract_task_page_details(page):
    return page.evaluate("""() => {
        const titleEl = document.querySelector('h1.title');
        if (!titleEl) return null;
        const title = titleEl.innerText.trim();
        
        let category = 'Unknown';
        const tds = Array.from(document.querySelectorAll('td'));
        for (let td of tds) {
            if (td.innerText.includes('Категория:')) {
                category = td.innerText.replace('Категория:', '').trim();
                break;
            }
        }
        let description = '';
        let requirement = '';
        const tikets = Array.from(document.querySelectorAll('.tiket'));
        tikets.forEach(t => {
            if (t.innerText.includes('Описание задания')) {
                if (t.nextElementSibling) description = t.nextElementSibling.innerText.trim();
            }
            if (t.innerText.includes('Что нужно указать для выполнения задания')) {
                if (t.nextElementSibling) requirement = t.nextElementSibling.innerText.trim();
            }
        });
        return { title: title, category: category, description: description, requirement: requirement };
    }""")

# --- SILENT-AI PRO STREAMING CLIENT (UPDATED FOR LOG REASONS) ---
def analyze_with_silent_ai_stream(task_data):
    url = "https://silent-ai-pro-phi.vercel.app/api/ask"
    headers = {"Content-Type": "application/json"}
    
    # پرامپٹ میں رول ایڈ کر دیا ہے کہ ریجیکٹ کرنے کی وجہ لازمی بتائے
    persona = (
        "You are a silent ai made by Nothing Is Impossible.\n"
        "RULES:\n"
        "1. CASUAL CHAT: If the user says hi/hello or talks casually, be friendly and short.\n"
        "2. HAPPY MODE: If the user angry you send always smile emoji and happy response.\n"
        "3. LANGUAGE STYLE: Reply ONLY in standard, clean Roman Urdu prose (Hinglish script like 'Task mukammal karen'). Do NOT use pure Arabic/Urdu alphabet text script.\n"
        "4. CURRENCY RULES: Strictly convert any currency mention like 'py6', 'руб', 'rub', 'rubles', or 'ربل' into upper-case standard letters 'RUB' (e.g., write '3 RUB'). Never write raw letters 'py6'.\n"
        "5. LINK INTEGRATION: When mentioning a link or a bot, output it as a clean markdown link like [Click Here](url). NEVER wrap markdown links inside extra parentheses.\n"
        "6. TASK CRITERIA & SKIP REASON: You are analyzing a micro-task from Aviso.bz. If it requires real money deposits, purchasing accounts, investments, or bank card validation, reply EXACTLY with format 'REJECT: [Short 1-line reason in Roman Urdu explaining why, e.g., Isme investment krni hai ya card chahiye]'. If it is an easy/free task, mark it APPROVED and output a neat step-by-step user guide explaining exactly what to perform."
    )
    
    compiled_prompt = (
        f"{persona}\n\n"
        f"User: Please analyze this micro-task:\n"
        f"Title: {task_data['title']}\n"
        f"Category: {task_data['category']}\n"
        f"Description: {task_data['description']}\n"
        f"Proof Required: {task_data['requirement']}\n\n"
        f"AI:"
    )
    
    request_body = {"key": "silent-ai", "prompt": compiled_prompt}
    raw_response = ""
    try:
        resp = requests.post(url, json=request_body, headers=headers, stream=True, timeout=90)
        if resp.status_code != 200: return False, "AI Server connection failed (Status Code != 200)"
            
        for line in resp.iter_lines():
            if not bot_status["is_running"]: break
            if line:
                decoded_line = line.decode('utf-8').strip()
                if decoded_line.startswith("data: "):
                    json_str = decoded_line[6:]
                    try:
                        data_chunk = json.loads(json_str)
                        if data_chunk.get("type") == "text":
                            raw_response += data_chunk.get("text", "")
                    except: pass
    except Exception as e:
        return False, f"AI Stream Connection Error: {str(e)}"
        
    ai_reply_text = raw_response.strip()
    if not ai_reply_text:
        return False, "AI returned blank or empty content."
        
    # اگر ٹاسک ریجیکٹ ہوا ہے تو وجہ نکالیں
    if "REJECT" in ai_reply_text:
        reason = "Task standard criteria filter (Requires investment, deposit or premium action)"
        if "REJECT:" in ai_reply_text:
            reason = ai_reply_text.split("REJECT:", 1)[1].strip()
        elif ":" in ai_reply_text:
            reason = ai_reply_text.split(":", 1)[1].strip()
        return False, reason
        
    ai_reply_text = ai_reply_text.replace("**", "*")
    ai_reply_text = re.sub(r'(?m)^#{1,6}\s+(.*)$', r'*\1*', ai_reply_text)
    ai_reply_text = re.sub(r'\(\s*\[([^\]]+)\]\(([^)]+)\)\s*\)', r'[\1](\2)', ai_reply_text)
    ai_reply_text = re.sub(r'(?i)py6|руб|руб\.|rubles\b|rub\b|ربل', 'RUB', ai_reply_text)
    
    return True, ai_reply_text

# --- TELEGRAM DELIVERY TRANSMITTER ---
def fire_alert_to_telegram(task_url, price, ai_content):
    if TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or TELEGRAM_CHAT_ID == "YOUR_CHAT_ID_HERE":
        log_msg("⚠️ Telegram configurations missing. Skipping broadcast.")
        return False
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    formatted_msg = (
        f"🎯 *New Easy Task Identified!*\n"
        f"💰 *Payout Value:* {price} RUB\n"
        f"🔗 *Task URL:* [Open Task Dashboard]({task_url})\n\n"
        f"{ai_content}"
    )
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": formatted_msg, "parse_mode": "Markdown", "disable_web_page_preview": True}
    try:
        requests.post(telegram_url, json=payload, timeout=12)
        return True
    except: return False

# --- TASK SCHEDULER CORE RUNNER (DYNAMIC RETRY SCROLL SYSTEM WITH FRONT-END LOGS) ---
def process_high_value_scrapes(context, page):
    log_msg("🔍 Navigating to Aviso Task Pool Dashboard...")
    bot_status["step"] = "🔍 Reading Task List Page..."
    page.goto("https://aviso.bz/tasks")
    page.wait_for_load_state("networkidle")
    time.sleep(2)
    
    if page.is_visible("input[name='username']"):
        log_msg("⚠️ Session expired or not logged in! Exiting scrape cycle.")
        return
    
    processed_history = load_processed_tasks()
    log_msg(f"📋 Loaded {len(processed_history)} already processed tasks from history file.")
    
    while bot_status["is_running"]:
        bot_status["step"] = "⚙️ Scanning current viewport tasks..."
        eligible_tasks = get_high_value_tasks_via_js(page) or []
        unique_tasks = [t for t in eligible_tasks if t['id'] not in processed_history]
        
        # اگر کوئی نیا ٹاسک لسٹ میں نظر نہیں آ رہا، تو جب تک نیا ٹاسک نہ ملے اسکرول لوپ چلائیں
        if not unique_tasks:
            log_msg("📜 No new tasks found in current viewport. Starting smart scroll retry loop...")
            consecutive_scrolls = 0
            max_scroll_limit = 25  
            
            while not unique_tasks and consecutive_scrolls < max_scroll_limit and bot_status["is_running"]:
                consecutive_scrolls += 1
                bot_status["step"] = f"📜 Searching new tasks... Scroll attempt {consecutive_scrolls}"
                log_msg(f"Moving page down/up to trigger dynamic AJAX load (Attempt {consecutive_scrolls})...")
                
                try:
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1.5)
                    page.evaluate("window.scrollBy(0, -350);")  # آٹو لوڈنگ ایکٹیویٹ کرنے کی ٹرک
                    time.sleep(0.6)
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1.5)
                except Exception as e:
                    log_msg(f"❌ Scroll action execution failed: {e}")
                    break
                
                eligible_tasks = get_high_value_tasks_via_js(page) or []
                unique_tasks = [t for t in eligible_tasks if t['id'] not in processed_history]
            
            if not unique_tasks:
                log_msg("🏁 Active scroll limit reached. No more unique tasks generated dynamically by website.")
                bot_status["step"] = "⚠️ Reached end of available pool."
                break
        
        log_msg(f"🎯 Scroll loop stopped. Found {len(unique_tasks)} new unique tasks to process.")
        
        for iteration, task in enumerate(unique_tasks, 1):
            if not bot_status["is_running"]: break
            
            log_msg(f"🚀 Processing Task {iteration}/{len(unique_tasks)} (ID: {task['id']} | Price: {task['price']} RUB)")
            bot_status["step"] = f"🚀 Opening Task ID: {task['id']} in a New Tab..."
            
            try:
                task_page = context.new_page()
                task_page.goto(task['url'], timeout=45000)
                task_page.wait_for_load_state("networkidle")
                time.sleep(1.5)
                
                scraped_payload = extract_task_page_details(task_page)
                task_page.close()  # ڈیٹا نکال کر فوراً کلوز، مین پیج کی پوزیشن سیو رہے گی
                
                if not scraped_payload or not scraped_payload['title']:
                    log_msg(f"❌ Task {task['id']} Skipped! Reason: Task is suspended, removed or invalid page structure.")
                    save_processed_task(task['id'])
                    processed_history.add(task['id'])
                    continue
                
                bot_status["step"] = f"🧠 Analyzing Task {task['id']} with Silent-AI..."
                is_approved, ai_result = analyze_with_silent_ai_stream(scraped_payload)
                
                if is_approved:
                    log_msg(f"✅ Task {task['id']} APPROVED by AI! Dispatching alert to Telegram channel...")
                    bot_status["step"] = f"📢 Firing Task {task['id']} to Telegram..."
                    fire_alert_to_telegram(task['url'], task['price'], ai_result)
                else:
                    # فرنٹ اینڈ کنسول پر واضح اسکیپ کی وجہ پرنٹ ہوگی
                    log_msg(f"⚠️ Task {task['id']} SKIPPED! Reason: {ai_result}")
                    
                save_processed_task(task['id'])
                processed_history.add(task['id'])
                time.sleep(1)
                
            except Exception as err:
                log_msg(f"❌ Error handling task {task['id']} execution inside tab: {err}")
                try: task_page.close()
                except: pass
                save_processed_task(task['id'])
                processed_history.add(task['id'])
                continue
                
    log_msg("🏁 Scrape run cycle completed successfully. Going to standby phase.")

# --- MAIN RUNNER LOOP ---
def run_infinite_loop(username, password):
    global bot_status, shared_data, current_browser_context
    from playwright.sync_api import sync_playwright

    kill_all_browsers()
    reset_debug_log()
    bot_status["is_running"] = True
    bot_status["needs_code"] = False
    bot_status["logs"] = []
    shared_data["otp_code"] = None
    
    log_msg("🚀 System Initialized. Launching browser instances...")
    proxy_config = get_proxy_config()
    if proxy_config:
        log_msg(f"🌍 Running via Proxy Connection: {proxy_config['server']}")
        bot_status["proxy_status"] = f"Proxy: {proxy_config['server']}"
    else:
        log_msg("🌍 Running via Direct IP Network (No proxy).")
        bot_status["proxy_status"] = "Direct IP"

    with sync_playwright() as p:
        while bot_status["is_running"]:
            try:
                context = p.chromium.launch_persistent_context(
                    USER_DATA_DIR,
                    headless=True,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    viewport={"width": 1366, "height": 768},
                    device_scale_factor=1,
                    is_mobile=False, has_touch=False, proxy=proxy_config,
                    args=["--disable-blink-features=AutomationControlled", "--disable-background-timer-throttling", "--start-maximized"]
                )
                
                inject_youtube_cookies(context)
                current_browser_context = context
                page = context.new_page()
                
                bot_status["step"] = "Login Page..."
                log_msg("Checking Aviso authentication status...")
                page.goto("https://aviso.bz/login", timeout=60000)
                save_debug_html(page, "Login_Page")
                
                if page.is_visible("input[name='username']"):
                    log_msg("🔑 Standard login form detected. Typing profile credentials...")
                    page.click("input[name='username']")
                    page.type("input[name='username']", username, delay=80)
                    time.sleep(0.5)
                    page.click("input[name='password']")
                    page.type("input[name='password']", password, delay=80)
                    time.sleep(1)

                    bot_status["step"] = "Clicking Login..."
                    btn_selector = "button:has-text('Войти')"
                    if not page.is_visible(btn_selector): btn_selector = "button[type='submit']"
                    perform_human_mouse_click(page, btn_selector, "Login_Mouse_Click")
                    
                    time.sleep(5)
                    take_screenshot(page, "After_Login_Click")

                    if page.is_visible("input[name='username']"):
                        if "подождите" not in page.content().lower():
                            log_msg("⚠️ Mouse click fallback triggered. Force-submitting form structure...")
                            bot_status["step"] = "Force Submitting..."
                            page.evaluate("""() => {
                                const form = document.querySelector('form[action*="login"]') || document.querySelector('form');
                                if(form) { form.submit(); } 
                            }""")
                            page.keyboard.press("Enter")
                            time.sleep(8)

                    if page.is_visible("input[name='code']"):
                        log_msg("🛡️ 2-Factor Authentication OTP Guard triggered! Waiting for code...")
                        bot_status["step"] = "WAITING_FOR_CODE"
                        bot_status["needs_code"] = True
                        take_screenshot(page, "OTP_Needed")
                        while shared_data["otp_code"] is None:
                            time.sleep(1)
                            if not bot_status["is_running"]: break
                        
                        if shared_data["otp_code"]:
                            log_msg(f"📥 Injecting 2FA Code: {shared_data['otp_code']}")
                            page.fill("input[name='code']", shared_data["otp_code"])
                            page.press("input[name='code']", "Enter")
                            time.sleep(8)
                            bot_status["needs_code"] = False
                            shared_data["otp_code"] = None

                    if page.is_visible("input[name='username']"):
                        log_msg("❌ Authentication sequence failed completely. Retrying...")
                        bot_status["step"] = "Login Failed. Retrying..."
                        save_debug_html(page, "Login_Failed")
                        context.close()
                        continue
                
                log_msg("🟢 Authorization Verified successfully!")
                bot_status["step"] = "🟢 Login Success!"
                take_screenshot(page, "Login_Success")

                # ٹاسک پراسیسنگ کا ایڈوانسڈ لاگنگ ماڈیول رن کریں
                process_high_value_scrapes(context, page)
                
                log_msg("🔒 Cycle finished. Executing safe logout protocol...")
                try:
                    page.goto("https://aviso.bz/logout")
                    time.sleep(5)
                except: pass
                
                context.close()
                log_msg("💤 Session resting. Entering a 20-minute sleep cycle...")
                for s in range(1200):
                    if not bot_status["is_running"]: return
                    if s % 10 == 0: 
                        rem = 1200 - s
                        bot_status["step"] = f"💤 Next Run: {rem // 60}m {rem % 60}s"
                    time.sleep(1)

            except Exception as e:
                log_msg(f"❌ Internal Processing Loop Exception: {str(e)}")
                bot_status["step"] = f"Error: {str(e)}"
                time.sleep(30)

# --- ROUTES ---
@app.route('/')
def index(): return render_template('index.html')

@app.route('/view_image/<filename>')
def view_image(filename):
    file_path = os.path.join(SCREENSHOT_DIR, filename)
    if os.path.exists(file_path):
        response = make_response(send_file(file_path, mimetype='image/jpeg'))
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        return response
    return "Not Found", 404

@app.route('/save_proxy', methods=['POST'])
def save_proxy():
    data = request.json
    with open(PROXY_FILE, "w") as f: f.write(data.get('proxy', '').strip())
    return jsonify({"status": "Proxy Saved!"})

@app.route('/clear_proxy', methods=['POST'])
def clear_proxy():
    if os.path.exists(PROXY_FILE): os.remove(PROXY_FILE)
    return jsonify({"status": "Proxy Cleared!"})

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
    log_msg("🛑 Stop signal received. Suspending operation updates...")
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
        if os.path.exists(USER_DATA_DIR): shutil.rmtree(USER_DATA_DIR); os.makedirs(USER_DATA_DIR, exist_ok=True)
        return jsonify({"status": "Data Wiped"})
    except: return jsonify({"status": "Error"})

@app.route('/status')
def status(): return jsonify(bot_status)

@app.route('/download_log')
def download_log():
    if os.path.exists(DEBUG_FILE): return send_file(DEBUG_FILE, as_attachment=True)
    else: return "Log not found", 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
