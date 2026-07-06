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
import asyncio
from flask import Flask, render_template, request, jsonify, send_file, make_response
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes

app = Flask(__name__)

# --- Configuration ---
SCREENSHOT_DIR = "static/screenshots"
os.makedirs(SCREENSHOT_DIR, exist_ok=True)
USER_DATA_DIR = "/app/browser_data"
DEBUG_FILE = "debug_source.html"
PROXY_FILE = "proxy_config.txt"
COOKIES_FILE = "youtube_cookies.json"
PROCESSED_TASKS_FILE = "processed_tasks.txt"
TRACKED_TASKS_FILE = "tracked_tasks.json"

# --- Telegram Configuration ---
TELEGRAM_BOT_TOKEN = "7766363398:AAFEfLCKw4jTOqMyTv6baeE5XGCfjHKClFc"  
TELEGRAM_CHAT_ID = "-1004480322983"  # یہ مین چینل الرٹس کے لیے رہے گا

# --- Shared State & Global Credentials ---
shared_data = {"otp_code": None}
current_browser_context = None
GLOBAL_CREDS = {"username": "", "password": ""}
user_states = {}  # ٹیلی گرام یوزرز کی اسٹیٹ ٹریک کرنے کے لیے

bot_status = {
    "step": "Idle",
    "images": [],
    "logs": [],
    "is_running": False,
    "needs_code": False,
    "proxy_status": "Direct IP"
}

# --- TRACKED TASKS JSON HELPERS ---
def load_tracked_tasks():
    if os.path.exists(TRACKED_TASKS_FILE):
        try:
            with open(TRACKED_TASKS_FILE, "r") as f:
                return json.load(f)
        except:
            return []
    return []

def save_tracked_tasks(data):
    with open(TRACKED_TASKS_FILE, "w") as f:
        json.dump(data, f, indent=4)

# --- HELPER FUNCTIONS ---
def log_msg(msg):
    timestamp = datetime.datetime.now().strftime('%H:%M:%S')
    log_line = f"[{timestamp}] {msg}"
    print(log_line)
    bot_status["logs"].append(log_line)
    if len(bot_status["logs"]) > 40:
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

def perform_human_mouse_click(page, selector):
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

def inject_youtube_cookies(context):
    if os.path.exists(COOKIES_FILE):
        try:
            with open(COOKIES_FILE, "r", encoding="utf-8") as f:
                cookies = json.load(f)
                context.add_cookies(cookies)
            log_msg("🍪 YouTube Cookies Injected Successfully!")
        except Exception as e:
            log_msg(f"⚠️ Error loading cookies: {e}")

# --- TELEGRAM PERSONAL INBOX DISPATCHER ---
def send_personal_telegram_alert(user_id, task_url, task_id):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    message = (
        f"🎯 *Your Target Task is Now AVAILABLE!*\n\n"
        f"🆔 *Task ID:* {task_id}\n"
        f"🔗 *Task URL:* {task_url}\n\n"
        f"🚀 Aap is task ko ab perform kar sakte hain!"
    )
    payload = {"chat_id": user_id, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Error sending personal alert: {e}")

# --- AUTO LOGIN HELPER FOR BACKGROUND CHECKS ---
def handle_auto_login_if_needed(page):
    try:
        if page.is_visible("input[name='username']") and GLOBAL_CREDS["username"]:
            log_msg("🔐 Auto-Login triggered in background task check...")
            page.fill("input[name='username']", GLOBAL_CREDS["username"])
            time.sleep(0.5)
            page.fill("input[name='password']", GLOBAL_CREDS["password"])
            time.sleep(1)
            
            btn_selector = "button:has-text('Войти')"
            if not page.is_visible(btn_selector): btn_selector = "button[type='submit']"
            perform_human_mouse_click(page, btn_selector)
            time.sleep(5)
            
            # اگر او ٹی پی آرہا ہے تو اسے اگنور کر دے گا جیسا کہ ڈسکس ہوا تھا
            if page.is_visible("input[name='code']"):
                log_msg("🛡️ 2FA detected during background auto-login. Skipping loop to prevent lock.")
                return False
            return True
    except:
        pass
    return True

# --- BACKGROUND 5-MINUTE CUSTOM TASK CHECKER ---
def custom_task_checker_loop():
    from playwright.sync_api import sync_playwright
    log_msg("⏱️ Background Custom Task Checker Thread Started.")
    
    while True:
        # ہر 5 منٹ (300 سیکنڈ) کا ویٹ لوپ
        time.sleep(300)
        
        tracked_tasks = load_tracked_tasks()
        if not tracked_tasks:
            continue
            
        log_msg(f"🔄 Background Check: Scanning {len(tracked_tasks)} custom tasks...")
        proxy_config = get_proxy_config()
        
        try:
            with sync_playwright() as p:
                # اے آئی والے لوپ کو ڈسٹرب کیے بغیر بالکل الگ براؤزر اور ٹیب اوپن کرے گا
                context = p.chromium.launch_persistent_context(
                    USER_DATA_DIR,
                    headless=True,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    proxy=proxy_config,
                    args=["--disable-blink-features=AutomationControlled", "--disable-background-timer-throttling"]
                )
                
                page = context.new_page()
                
                for task in tracked_tasks:
                    try:
                        page.goto(task["url"], timeout=45000)
                        page.wait_for_load_state("networkidle")
                        time.sleep(2)
                        
                        # چیک کریں اگر لاگ ان اڑ گیا ہے تو اٹو لاگ ان کرے گا
                        if not handle_auto_login_if_needed(page):
                            continue
                            
                        # صرف اور صرف اویلیبلٹی کی کنڈیشن میچ ہوگی (باقی سب بلاوجہ اگنور)
                        is_available = page.is_visible("button:has-text('Приступить к выполнению')") or page.is_visible("form[action='/go/gotask.php']")
                        
                        if is_available:
                            log_msg(f"✅ Target Task {task['task_id']} is available! Firing personal alert to User {task['user_id']}.")
                            send_personal_telegram_alert(task["user_id"], task["url"], task["task_id"])
                            
                    except Exception as task_err:
                        print(f"Error scanning custom task {task.get('task_id')}: {task_err}")
                        
                context.close()
        except Exception as e:
            log_msg(f"❌ Custom Task Checker Master Loop Error: {e}")

# --- JS SCANNERS FOR AI POOL ---
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

# --- SILENT-AI PRO STREAMING CLIENT ---
def analyze_with_silent_ai_stream(task_data):
    url = "https://silent-ai-pro-phi.vercel.app/api/ask"
    headers = {"Content-Type": "application/json"}
    persona = (
        "You are a silent ai made by Nothing Is Impossible.\n"
        "RULES:\n"
        "1. LANGUAGE STYLE: Reply ONLY in standard, clean Roman Urdu prose.\n"
        "2. CURRENCY RULES: Convert mentions to upper-case 'RUB'.\n"
        "3. TASK CRITERIA: If requires money/purchases, reply EXACTLY with format 'REJECT: [Reason]'. If easy, mark APPROVED with a step-by-step guide."
    )
    compiled_prompt = f"{persona}\n\nUser: Analyze this micro-task:\nTitle: {task_data['title']}\nCategory: {task_data['category']}\nDescription: {task_data['description']}\nProof: {task_data['requirement']}\n\nAI:"
    
    raw_response = ""
    try:
        resp = requests.post(url, json={"key": "silent-ai", "prompt": compiled_prompt}, headers=headers, stream=True, timeout=90)
        if resp.status_code != 200: return False, "AI Server connection failed"
        for line in resp.iter_lines():
            if not bot_status["is_running"]: break
            if line:
                decoded_line = line.decode('utf-8').strip()
                if decoded_line.startswith("data: "):
                    try:
                        data_chunk = json.loads(decoded_line[6:])
                        if data_chunk.get("type") == "text": raw_response += data_chunk.get("text", "")
                    except: pass
    except Exception as e:
        return False, str(e)
        
    ai_reply_text = raw_response.strip()
    if "REJECT" in ai_reply_text:
        reason = ai_reply_text.split("REJECT:", 1)[1].strip() if "REJECT:" in ai_reply_text else "Filter triggered"
        return False, reason
    return True, ai_reply_text

def fire_alert_to_telegram(task_url, price, ai_content):
    telegram_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    formatted_msg = f"🎯 *New Easy Task Identified!*\n💰 *Payout Value:* {price} RUB\n🔗 *Task URL:* [Open Task]({task_url})\n\n{ai_content}"
    try: requests.post(telegram_url, json={"chat_id": TELEGRAM_CHAT_ID, "text": formatted_msg, "parse_mode": "Markdown", "disable_web_page_preview": True}, timeout=12)
    except: pass

# --- CORE AI SCRAPER RUNNER (WITH 10-SECOND THROTTLING) ---
def process_high_value_scrapes(context, page):
    log_msg("🔍 Navigating to Aviso Task Pool Dashboard...")
    page.goto("https://aviso.bz/tasks")
    page.wait_for_load_state("networkidle")
    time.sleep(2)
    
    processed_history = load_processed_tasks()
    
    while bot_status["is_running"]:
        eligible_tasks = get_high_value_tasks_via_js(page) or []
        unique_tasks = [t for t in eligible_tasks if t['id'] not in processed_history]
        
        if not unique_tasks:
            page.evaluate("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(2)
            continue
            
        for task in unique_tasks:
            if not bot_status["is_running"]: break
            log_msg(f"🚀 Processing Task ID: {task['id']} ({task['price']} RUB)")
            
            try:
                task_page = context.new_page()
                task_page.goto(task['url'], timeout=45000)
                task_page.wait_for_load_state("networkidle")
                
                scraped_payload = extract_task_page_details(task_page)
                task_page.close()
                
                if scraped_payload and scraped_payload['title']:
                    is_approved, ai_result = analyze_with_silent_ai_stream(scraped_payload)
                    if is_approved:
                        fire_alert_to_telegram(task['url'], task['price'], ai_result)
                        log_msg(f"✅ Task {task['id']} Dispached to Telegram.")
                    else:
                        log_msg(f"⚠️ Task {task['id']} Skipped: {ai_result}")
                        
                save_processed_task(task['id'])
                processed_history.add(task['id'])
                
                # 🎯 ریٹ لمیٹ اور فائرنگ سے بچنے کے لیے ہر ایک ٹاسک کے بعد کم از کم 10 سیکنڈ کا لازمی تھروٹل توقف
                log_msg("⏳ Sleeping for 10 seconds to respect AI rate limits...")
                time.sleep(10)
                
            except Exception as e:
                save_processed_task(task['id'])
                processed_history.add(task['id'])
                time.sleep(5)

def run_infinite_loop(username, password):
    global bot_status, current_browser_context
    from playwright.sync_api import sync_playwright

    kill_all_browsers()
    bot_status["is_running"] = True
    bot_status["logs"] = []
    
    proxy_config = get_proxy_config()
    with sync_playwright() as p:
        while bot_status["is_running"]:
            try:
                context = p.chromium.launch_persistent_context(
                    USER_DATA_DIR, headless=True,
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    proxy=proxy_config, args=["--disable-blink-features=AutomationControlled", "--disable-background-timer-throttling"]
                )
                inject_youtube_cookies(context)
                current_browser_context = context
                page = context.new_page()
                
                page.goto("https://aviso.bz/login", timeout=60000)
                if page.is_visible("input[name='username']"):
                    page.fill("input[name='username']", username)
                    page.fill("input[name='password']", password)
                    btn_selector = "button:has-text('Войти')"
                    if not page.is_visible(btn_selector): btn_selector = "button[type='submit']"
                    perform_human_mouse_click(page, btn_selector)
                    time.sleep(5)

                    if page.is_visible("input[name='code']"):
                        bot_status["needs_code"] = True
                        while shared_data["otp_code"] is None and bot_status["is_running"]: time.sleep(1)
                        if shared_data["otp_code"]:
                            page.fill("input[name='code']", shared_data["otp_code"])
                            page.keyboard.press("Enter")
                            time.sleep(6)
                        bot_status["needs_code"] = False
                        shared_data["otp_code"] = None
                
                process_high_value_scrapes(context, page)
                context.close()
            except Exception as e:
                log_msg(f"❌ Scraper loop exception: {e}")
                time.sleep(20)

# --- TELEGRAM INTERACTIVE BOT INTEGRATION (python-telegram-bot v21+) ---
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("➕ Add Task", callback_data="add_task")],
        [InlineKeyboardButton("⚙️ Manage Tasks", callback_data="manage_tasks")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("✨ *Welcome to Target Task Monitor Bot!*\n\nNiche diye gaye buttons se apna task manage karen:", parse_mode="Markdown", reply_markup=reply_markup)

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = str(query.from_user.id)
    
    if query.data == "add_task":
        user_states[user_id] = "waiting_for_link"
        await query.message.reply_text("🔗 Kindly pane task ka *Full URL Link* send karen:\nExample: `https://aviso.bz/task-read?adv=1373852`", parse_mode="Markdown")
        
    elif query.data == "manage_tasks":
        tasks = load_tracked_tasks()
        user_tasks = [t for t in tasks if str(t["user_id"]) == user_id]
        
        if not user_tasks:
            await query.message.reply_text("❌ Aapki list mein koi active task nahi hai.")
            return
            
        keyboard = []
        for t in user_tasks:
            keyboard.append([InlineKeyboardButton(f"🗑️ Delete ID: {t['task_id']}", callback_data=f"del_{t['task_id']}")])
        
        reply_markup = InlineKeyboardMarkup(keyboard)
        await query.message.reply_text("⚙️ *Your Tracked Tasks:*\nKisi bhi task par click karke usko delete karen.", parse_mode="Markdown", reply_markup=reply_markup)
        
    elif query.data.startswith("del_"):
        task_id_to_del = query.data.split("_")[1]
        tasks = load_tracked_tasks()
        updated_tasks = [t for t in tasks if not (str(t["user_id"]) == user_id and str(t["task_id"]) == task_id_to_del)]
        save_tracked_tasks(updated_tasks)
        await query.message.reply_text(f"✅ Task ID *{task_id_to_del}* successfully remove kar diya gaya hai!", parse_mode="Markdown")

async def message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    text = update.message.text.strip()
    
    if user_states.get(user_id) == "waiting_for_link":
        # یو آر ایل سے یونیک ایڈورٹائزمنٹ / ٹاسک آئی ڈی نکالنا
        match = re.search(r'adv=(\d+)', text)
        if not match:
            await update.message.reply_text("❌ Invalid Link! Please enter a valid Aviso task link containing 'adv=ID'.")
            return
            
        task_id = match.group(1)
        tasks = load_tracked_tasks()
        
        # ڈوپلیکیٹ چیک کرنا
        if any(t["task_id"] == task_id and str(t["user_id"]) == user_id for t in tasks):
            await update.message.reply_text("⚠️ Yeh task pehle se aapki list mein added hai.")
            user_states[user_id] = None
            return
            
        tasks.append({
            "user_id": user_id,
            "task_id": task_id,
            "url": text,
            "added_at": str(datetime.datetime.now())
        })
        
        save_tracked_tasks(tasks)
        user_states[user_id] = None
        await update.message.reply_text(f"🎯 *Success!* Task ID *{task_id}* target list mein add ho gaya hai. Har 5 min baad iski checking ki jayegi.", parse_mode="Markdown")

def start_telegram_bot():
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_cmd))
    application.add_handler(CallbackQueryHandler(button_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, message_handler))
    
    print("🤖 Telegram Bot Thread Engine Initialized.")
    application.run_polling(close_loop=False, stop_signals=None)


# --- FLASK ROUTES ---
@app.route('/')
def index(): return render_template('index.html')

@app.route('/start', methods=['POST'])
def start_bot():
    if bot_status["is_running"]: return jsonify({"status": "Running"})
    data = request.json
    username = data.get('username', '')
    password = data.get('password', '')
    GLOBAL_CREDS["username"] = username
    GLOBAL_CREDS["password"] = password
    
    t = threading.Thread(target=run_infinite_loop, args=(username, password))
    t.start()
    return jsonify({"status": "Started"})

@app.route('/stop', methods=['POST'])
def stop_bot():
    bot_status["is_running"] = False
    return jsonify({"status": "Stopping..."})

@app.route('/status')
def status(): return jsonify(bot_status)

@app.route('/submit_code', methods=['POST'])
def submit_code_api():
    data = request.json
    shared_data["otp_code"] = data.get('code')
    return jsonify({"status": "Received"})

if __name__ == '__main__':
    # 1. ٹیلی گرام انٹرایکٹو بوٹ کو الگ تھریڈ میں رن کریں
    bot_thread = threading.Thread(target=start_telegram_bot, daemon=True)
    bot_thread.start()
    
    # 2. 5 منٹ والے کسٹم ٹاسک مانیٹرنگ لوپ کو الگ آزاد تھریڈ میں رن کریں
    custom_checker_thread = threading.Thread(target=custom_task_checker_loop, daemon=True)
    custom_checker_thread.start()
    
    # 3. مین ویب سرور رن کریں
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
