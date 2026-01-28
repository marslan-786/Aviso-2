import time
import os
from playwright.sync_api import sync_playwright

# --- CONFIGURATION ---
# یہ وہی پاتھ ہونا چاہیے جو app.py میں ہے تاکہ کوکیز شیئر ہو سکیں
USER_DATA_DIR = "/app/browser_data2"  

def run_gmail_login_center():
    print("🚀 STARTING GMAIL SECURE LOGIN...")
    print(f"📂 Session Path: {USER_DATA_DIR}")

    with sync_playwright() as p:
        # --- ULTIMATE STEALTH LAUNCHER ---
        # گوگل کو دھوکہ دینے کے لیے یہ سیٹنگز سب سے اہم ہیں
        context = p.chromium.launch_persistent_context(
            USER_DATA_DIR,
            headless=True, # سرور پر ہے اس لیے ہیڈلیس
            channel="chrome", # اگر سرور پر اصلی کروم ہے تو وہ استعمال کرے گا (زیادہ محفوظ)
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
            
            # --- GOOGLE SECURITY BYPASS ARGS ---
            args=[
                "--disable-blink-features=AutomationControlled", # سب سے اہم: روبوٹ کا ٹیگ ہٹاتا ہے
                "--no-sandbox",
                "--disable-infobars",
                "--disable-dev-shm-usage",
                "--disable-browser-side-navigation",
                "--disable-features=IsolateOrigins,site-per-process",
                "--ignore-certificate-errors",
                "--disable-gpu",
                # WebGL اور دیگر چیزوں کو فیک کرنا
                "--use-gl=swiftshader",
                "--lang=en-US"
            ]
        )

        page = context.new_page()

        # --- JAVASCRIPT INJECTION (EXTRA STEALTH) ---
        # پیج لوڈ ہونے سے پہلے یہ اسکرپٹ چلے گا تاکہ گوگل کے جاوا سکرپٹ چیکس فیل ہو جائیں
        page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            Object.defineProperty(navigator, 'languages', {get: () => ['en-US', 'en']});
            Object.defineProperty(navigator, 'plugins', {get: () => [1, 2, 3, 4, 5]});
            window.chrome = { runtime: {} };
        """)

        try:
            print("🌍 Opening Google Login Page...")
            page.goto("https://accounts.google.com/signin/v2/identifier?flowName=GlifWebSignIn&flowEntry=ServiceLogin")
            page.wait_for_load_state("networkidle")
            
            print("📸 Taking initial screenshot...")
            page.screenshot(path="static/screenshots/gmail_debug_1_start.png")

            # --- USERNAME ---
            email = input("⌨️  Enter your Gmail Address: ")
            
            if page.is_visible('input[type="email"]'):
                print("✍️  Typing Email...")
                page.fill('input[type="email"]', email)
                time.sleep(1)
                page.keyboard.press("Enter")
                
                # انتظار کریں کہ اگلا پیج آئے
                time.sleep(5)
                page.screenshot(path="static/screenshots/gmail_debug_2_after_email.png")
                
                # چیک کریں کہ کیا "Browser not secure" آیا؟
                content = page.content()
                if "couldn't sign you in" in content or "browser or app may not be secure" in content:
                    print("❌ FAILED: Google blocked this browser secure check.")
                    print("💡 Tip: Try running this script locally on your PC first, then upload the 'browser_data' folder.")
                    return
            else:
                print("❌ Email field not found!")
                return

            # --- PASSWORD ---
            if page.is_visible('input[type="password"]'):
                password = input("⌨️  Enter your Password: ")
                print("✍️  Typing Password...")
                page.fill('input[type="password"]', password)
                time.sleep(1)
                page.keyboard.press("Enter")
                
                print("⏳ Waiting for login result...")
                time.sleep(8)
                page.screenshot(path="static/screenshots/gmail_debug_3_after_password.png")
            else:
                print("⚠️ Password field not appeared. Check screenshot 2.")

            # --- 2FA / VERIFICATION ---
            # یہاں ہم چیک کریں گے کہ کیا گوگل نے کچھ اور مانگا ہے
            if "challenge" in page.url or "signinOptions" in page.url:
                print("⚠️ 2FA / Verification Required!")
                print("📸 Check 'static/screenshots/gmail_debug_3_after_password.png'")
                print("🔴 This script handles simple login. For 2FA, you might need manual intervention.")
            
            # --- FINAL CHECK ---
            if "myaccount.google.com" in page.url or "accounts.google.com/ManageAccount" in page.url:
                print("✅ LOGIN SUCCESSFUL! Session saved.")
            else:
                print(f"ℹ️ Current URL: {page.url}")
                print("📸 Final screenshot saved as 'gmail_debug_final.png'")
                page.screenshot(path="static/screenshots/gmail_debug_final.png")

        except Exception as e:
            print(f"❌ Error: {e}")
            page.screenshot(path="static/screenshots/gmail_error.png")

        finally:
            print("🔒 Closing Browser & Saving Session...")
            context.close()
            print("✅ Done. Now you can restart app.py and it will use this login.")

if __name__ == "__main__":
    # پہلے فولڈر کو صاف نہ کریں، ورنہ پرانا ڈیٹا اڑ جائے گا۔
    # صرف اگر فولڈر نہیں ہے تو بنائیں۔
    if not os.path.exists(USER_DATA_DIR):
        os.makedirs(USER_DATA_DIR)
        
    run_gmail_login_center()
