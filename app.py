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
from flask import Flask, render_template, request, jsonify, send_file

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
    "is_running": False,
    "needs_code": False,
    "proxy_status": "Direct IP"
}

# --- HELPER FUNCTIONS ---
def load_processed_tasks():
    """Loads already processed task IDs from file to prevent duplicates."""
    if os.path.exists(PROCESSED_TASKS_FILE):
        with open(PROCESSED_TASKS_FILE, "r") as f:
            return set(line.strip() for line in f if line.strip())
    return set()

def save_processed_task(task_id):
    """Saves a processed task ID to the history file."""
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
        timestamp = int(time.time())
        filename = f"{timestamp}_{name}.png"
        path = os.path.join(SCREENSHOT_DIR, filename)
        page.screenshot(path=path)
        bot_status["images"].append(filename)
    except: pass

def save_debug_html(page, step_name):
    try:
        content = page.content()
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        separator = f"\n\n\n"
        with open(DEBUG_FILE, "a", encoding="utf-8") as f:
            f.write(separator + content)
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
            print("🍪 YouTube Cookies Injected Successfully!")
        except Exception as e:
            print(f"⚠️ Error loading cookies: {e}")
    else:
        print("⚠️ youtube_cookies.json file not found.")

def perform_human_mouse_click(page, selector, screenshot_name):
    try:
        if not page.is_visible(selector): return False
        box = page.locator(selector).bounding_box()
        if box:
            x = box['x'] + box['width'] / 2 + random.uniform(-15, 15)
            y = box['y'] + box['height'] / 2 + random.uniform(-5, 5)
            
            page.mouse.move(x, y, steps=15) 
            time.sleep(0.3)

            page.evaluate(f"""() => {{
                const d = document.createElement('div');
                d.id = 'click-dot'; d.style.position = 'fixed'; 
                d.style.left = '{x-5}px'; d.style.top = '{y-5}px';
                d.style.width = '10px'; d.style.height = '10px';
                d.style.background = 'red'; d.style.border = '2px solid white';
                d.style.borderRadius = '50%'; d.style.zIndex = '9999999';
                d.style.pointerEvents = 'none';
                document.body.appendChild(d);
            }}""")
            
            take_screenshot(page, screenshot_name)
            page.mouse.down()
            time.sleep(random.uniform(0.05, 0.15))
            page.mouse.up()
            time.sleep(0.5)
            page.evaluate("if(document.getElementById('click-dot')) document.getElementById('click-dot').remove();")
            return True
    except Exception as e:
        print(f"Mouse Error: {e}")
    return False

# --- JS SCANNERS (2 RUBLES LOCK) ---
def get_high_value_tasks_via_js(page):
    """Scans the master task table and filters items paying >= 2.0 Rubles."""
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
                if (cleanPrice) {
                    price = parseFloat(cleanPrice[1].replace(',', '.'));
                }
            }
            
            if (taskId && price >= 2.0) {
                targetTasks.push({
                    id: taskId,
                    price: price,
                    url: 'https://aviso.bz' + href
                });
            }
        });
        
        return targetTasks;
    }""")

def extract_task_page_details(page):
    return page.evaluate("""() => {
        const titleEl = document.querySelector('h1.title');
        const title = titleEl ? titleEl.innerText.trim() : 'Unknown Task Title';
        
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
        
        return {
            title: title,
            category: category,
            description: description,
            requirement: requirement
        };
    }""")

# --- SILENT-AI PRO STREAMING CLIENT ---
def analyze_with_silent_ai_stream(task_data):
    url = "https://silent-ai-pro-phi.vercel.app/api/ask"
    headers = {"Content-Type": "application/json"}
    
    # اے آئی پرامپٹ کو ربل ہٹا کر "RUB" پر لاک کر دیا ہے
    persona = (
        "You are a silent ai made by Nothing Is Impossible.\n"
        "RULES:\n"
        "1. CASUAL CHAT: If the user says hi/hello or talks casually, be friendly and short.\n"
        "2. HAPPY MODE: If the user angry you send always smile emoji and happy response.\n"
        "3. LANGUAGE STYLE: Reply ONLY in standard, clean Roman Urdu prose (Hinglish script like 'Task mukammal karen', 'Screenshot attach karen'). Do NOT use pure Arabic/Urdu alphabet text script.\n"
        "4. CURRENCY RULES: Strictly convert any currency mention like 'py6', 'руб', 'rub', 'rubles', or 'ربل' into upper-case standard letters 'RUB' (e.g., write '3 RUB' or '3.5 RUB'). Never write raw letters 'py6' or Urdu script 'ربل'.\n"
        "5. LINK INTEGRATION: When mentioning a link or a bot, output it as a clean markdown link like [Click Here](url) or [Telegram Bot](url). NEVER wrap markdown links inside extra parentheses like ([text](url)) and never duplicate the raw link text next to it.\n"
        "6. SHORT ANSWER: Always Keep instructions clean and short.\n"
        "7. TASK CRITERIA: You are analyzing a micro-task from Aviso.bz. If it requires real money deposits, purchasing accounts, investments, or bank card validation, reply EXACTLY with the single word 'REJECT'. If it is an easy/free task (like website registration without deposit, joining a Telegram channel/bot, micro app installation, simple social media subscription), mark it APPROVED and output a neat step-by-step user guide explaining exactly what to perform and what information/screenshot to provide as proof."
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
    
    request_body = {
        "key": "silent-ai",
        "prompt": compiled_prompt
    }
    
    raw_response = ""
    try:
        resp = requests.post(url, json=request_body, headers=headers, stream=True, timeout=90)
        if resp.status_code != 200:
            return None
            
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
                    except:
                        pass
    except Exception as e:
        print(f"❌ [AI Stream Core Error]: {e}")
        return None
        
    ai_reply_text = raw_response.strip()
    if not ai_reply_text or "REJECT" in ai_reply_text:
        return None
        
    ai_reply_text = ai_reply_text.replace("**", "*")
    ai_reply_text = re.sub(r'(?m)^#{1,6}\s+(.*)$', r'*\1*', ai_reply_text)
    
    # فکس لنکس اور کرنسی ہارڈ کوڈ ریپلیس فلٹر (ربل اور py6 کو ہمیشہ RUB کرے گا)
    ai_reply_text = re.sub(r'\(\s*\[([^\]]+)\]\(([^)]+)\)\s*\)', r'[\1](\2)', ai_reply_text)
    ai_reply_text = re.sub(r'(?i)py6|руб|руб\.|rubles\b|rub\b|ربل', 'RUB', ai_reply_text)
    
    return ai_reply_text

# --- TELEGRAM DELIVERY TRANSMITTER ---
def fire_alert_to_telegram(task_url, price, ai_content):
    if TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN_HERE" or TELEGRAM_CHAT_ID == "YOUR_CHAT_ID_HERE":
        print("⚠️ Telegram details unconfigured.")
        return False
        
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    
    # یہاں فائنل ٹیلیگرام لے آؤٹ میں "RUB" سیٹ کر دیا ہے
    formatted_msg = (
        f"🎯 *New Easy Task Identified!*\n"
        f"💰 *Payout Value:* {price} RUB\n"
        f"🔗 *Task URL:* [Open Task Dashboard]({task_url})\n\n"
        f"{ai_content}"
    )
    
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": formatted_msg,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True
    }
    try:
        requests.post(telegram_url, json=payload, timeout=12)
        return True
    except:
        return False

# --- TASK SCHEDULER CORE RUNNER (DYNAMIC RETRY SCROLL SYSTEM) ---
def process_high_value_scrapes(context, page):
    """Processes currently visible tasks via independent tabs, scrolling dynamically UNTIL unique tasks are found."""
    bot_status["step"] = "🔍 Reading Task List Page..."
    page.goto("https://aviso.bz/tasks")
    page.wait_for_load_state("networkidle")
    time.sleep(2)
    
    if page.is_visible("input[name='username']"): return
    
    processed_history = load_processed_tasks()
    
    while bot_status["is_running"]:
        bot_status["step"] = "⚙️ Scanning current viewport tasks..."
        eligible_tasks = get_high_value_tasks_via_js(page)
        if not eligible_tasks:
            eligible_tasks = []
            
        unique_tasks = [t for t in eligible_tasks if t['id'] not in processed_history]
        
        # اگر کوئی نیا ٹاسک لسٹ میں نظر نہیں آ رہا، تو جب تک نیا ٹاسک نہ ملے اسکرول لوپ چلائیں
        if not unique_tasks:
            bot_status["step"] = "📜 No new tasks visible. Initializing active scroll loop..."
            consecutive_scrolls = 0
            max_scroll_limit = 25  # سیفٹی کیپ تاکہ اگر پیج بالکل ختم ہو جائے تو ہینگ نہ ہو
            
            while not unique_tasks and consecutive_scrolls < max_scroll_limit and bot_status["is_running"]:
                consecutive_scrolls += 1
                bot_status["step"] = f"📜 Searching new tasks... Scroll attempt {consecutive_scrolls}"
                print(f"Scrolling dynamically down/up to pull new elements. Attempt: {consecutive_scrolls}")
                
                try:
                    # فل نیچے اسکرول کریں
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1.5)
                    # آپ کی بتائی ہوئی ٹرک: تھوڑا سا اوپر اسکرول کریں تا کہ ویب سائٹ کی آٹو لوڈنگ فورا جاگے
                    page.evaluate("window.scrollBy(0, -350);")
                    time.sleep(0.6)
                    # دوبارہ نیچے لے جائیں تا کہ اسٹیبل ہو جائے
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
                    time.sleep(1.5)
                except Exception as scroll_err:
                    print(f"Scroll iteration failed: {scroll_err}")
                    break
                
                # دوبارہ چیک کریں کہ کیا اسکرول کرنے سے لسٹ میں نئے ٹاسک لوڈ ہوئے ہیں؟
                eligible_tasks = get_high_value_tasks_via_js(page) or []
                unique_tasks = [t for t in eligible_tasks if t['id'] not in processed_history]
            
            # اگر اتنی بار اسکرول کرنے پر بھی کوئی نیا ٹاسک نہیں ملا، اس کا مطلب اب مزید ٹاسکس موجود نہیں ہیں
            if not unique_tasks:
                print("End of list reached or no unique tasks generated dynamically.")
                bot_status["step"] = "⚠️ Reached end of available pool."
                break
        
        # جیسے ہی نئے ٹاسک لسٹ میں ڈیٹیکٹ ہوں گے، اسکرولنگ فوراً رک جائے گی اور پروسیسنگ شروع ہوگی
        print(f"Loop stopped scrolling. Found {len(unique_tasks)} new unique tasks to execute.")
        
        for iteration, task in enumerate(unique_tasks, 1):
            if not bot_status["is_running"]: break
            
            bot_status["step"] = f"🚀 Opening Task ID: {task['id']} in a New Tab..."
            try:
                task_page = context.new_page()
                task_page.goto(task['url'], timeout=45000)
                task_page.wait_for_load_state("networkidle")
                time.sleep(1.5)
                
                scraped_payload = extract_task_page_details(task_page)
                task_page.close()  # ڈیٹا نکال کر فوراً کلوز، مین پیج کی پوزیشن برقرار رہے گی
                
                bot_status["step"] = f"🧠 Analyzing Task {task['id']} with Silent-AI..."
                processed_guide = analyze_with_silent_ai_stream(scraped_payload)
                
                if processed_guide:
                    bot_status["step"] = f"📢 Firing Task {task['id']} to Telegram..."
                    fire_alert_to_telegram(task['url'], task['price'], processed_guide)
                    print(f"✅ Dispatched processed task profile for ID: {task['id']}")
                    
                save_processed_task(task['id'])
                processed_history.add(task['id'])
                time.sleep(1)
                
            except Exception as err:
                print(f"Error handling isolated tab processing: {err}")
                try: task_page.close()
                except: pass
                save_processed_task(task['id'])
                processed_history.add(task['id'])
                continue
                
    print("Scrape cycle finalized successfully.")

# --- MAIN RUNNER LOOP ---
def run_infinite_loop(username, password):
    global bot_status, shared_data, current_browser_context
    from playwright.sync_api import sync_playwright

    kill_all_browsers()
    reset_debug_log()
    bot_status["is_running"] = True
    bot_status["needs_code"] = False
    shared_data["otp_code"] = None
    
    proxy_config = get_proxy_config()
    if proxy_config:
        print(f"🌍 Using Proxy: {proxy_config['server']}")
        bot_status["proxy_status"] = f"Proxy: {proxy_config['server']}"
    else:
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
                page.goto("https://aviso.bz/login", timeout=60000)
                save_debug_html(page, "Login_Page")
                
                if page.is_visible("input[name='username']"):
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
                            print("Button failed. Attempting safe submit...")
                            bot_status["step"] = "Force Submitting..."
                            page.evaluate("""() => {
                                const form = document.querySelector('form[action*="login"]') || document.querySelector('form');
                                if(form) { form.submit(); } 
                            }""")
                            page.keyboard.press("Enter")
                            time.sleep(8)

                    if page.is_visible("input[name='code']"):
                        bot_status["step"] = "WAITING_FOR_CODE"
                        bot_status["needs_code"] = True
                        take_screenshot(page, "OTP_Needed")
                        while shared_data["otp_code"] is None:
                            time.sleep(1)
                            if not bot_status["is_running"]: break
                        
                        if shared_data["otp_code"]:
                            page.fill("input[name='code']", shared_data["otp_code"])
                            page.press("input[name='code']", "Enter")
                            time.sleep(8)
                            bot_status["needs_code"] = False
                            shared_data["otp_code"] = None

                    if page.is_visible("input[name='username']"):
                        print("Login failed.")
                        bot_status["step"] = "Login Failed. Retrying..."
                        save_debug_html(page, "Login_Failed")
                        context.close()
                        continue
                
                bot_status["step"] = "🟢 Login Success!"
                take_screenshot(page, "Login_Success")

                # ایڈوانسڈ ڈائنامک لوپ رن کریں
                process_high_value_scrapes(context, page)
                
                print("Cycle Complete. Logging Out...")
                try:
                    page.goto("https://aviso.bz/logout")
                    time.sleep(5)
                    take_screenshot(page, "Logout_Done")
                except: pass
                
                context.close()
                print("Sleeping 20 mins...")
                for s in range(1200):
                    if not bot_status["is_running"]: return
                    if s % 10 == 0: 
                        rem = 1200 - s
                        bot_status["step"] = f"💤 Next Run: {rem // 60}m {rem % 60}s"
                    time.sleep(1)

            except Exception as e:
                bot_status["step"] = f"Error: {str(e)}"
                time.sleep(30)

# --- ROUTES ---
@app.route('/')
def index(): return render_template('index.html')

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
