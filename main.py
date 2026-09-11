"""
Astra — minimal Windows voice assistant prototype (push-to-talk).

How to use (end-user):
- Download the built executable from the GitHub Actions artifacts (or build locally).
- Double-click to run. A console window will open.
- Press Enter to speak. Speak a short command. The assistant will reply by voice.

Notes for packaging: The workflow in .github/workflows/build-windows.yml runs on windows-latest and uses PyInstaller to build a single EXE.

Config (optional): Add an OpenAI API key to %USERPROFILE%\\.astra\\config.ini under [openai]\napi_key=YOUR_KEY to enable better world-knowledge answers.
"""

import os
import time
import subprocess
import webbrowser
import sys
import configparser

try:
    import speech_recognition as sr
except Exception as e:
    print("Missing dependency: speech_recognition. If running locally: pip install SpeechRecognition")
    raise

try:
    import pyttsx3
except Exception:
    print("Missing dependency: pyttsx3. If running locally: pip install pyttsx3")
    raise

# Optional OpenAI integration
OPENAI_AVAILABLE = False
try:
    import openai
    OPENAI_AVAILABLE = True
except Exception:
    OPENAI_AVAILABLE = False

APP_NAME = "Astra"
CONFIG_DIR = os.path.join(os.path.expanduser("~"), ".astra")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.ini")

# Load config
config = configparser.ConfigParser()
if os.path.exists(CONFIG_PATH):
    try:
        config.read(CONFIG_PATH)
        if OPENAI_AVAILABLE and config.has_section("openai") and config.get("openai", "api_key", fallback=""):
            openai.api_key = config.get("openai", "api_key")
    except Exception:
        pass

r = sr.Recognizer()
engine = pyttsx3.init()
engine.setProperty("rate", 150)

# Prefer a Windows voice if available
voices = engine.getProperty('voices')
for v in voices:
    if 'Zira' in v.name or 'David' in v.name or 'Microsoft' in v.name:
        engine.setProperty('voice', v.id)
        break


def speak(text):
    print(f"{APP_NAME}: {text}")
    try:
        engine.say(text)
        engine.runAndWait()
    except Exception as e:
        print("TTS error:", e)


def run_allowed_action(text):
    t = text.lower()
    # Open default browser
    if any(k in t for k in ["open browser", "open chrome", "open firefox", "open edge", "open browser"]):
        webbrowser.open("https://www.google.com")
        return "Opened browser."
    if "search for" in t or t.startswith("search "):
        # extract query
        q = t.replace("search for", "").replace("search", "").strip()
        if not q:
            return None
        webbrowser.open(f"https://www.google.com/search?q={q.replace(' ', '+')}")
        return f"Searched the web for {q}."
    if "open notepad" in t or "open text" in t:
        subprocess.Popen(["notepad.exe"])
        return "Opened Notepad."
    if "open calculator" in t or "open calc" in t:
        subprocess.Popen(["calc.exe"])
        return "Opened Calculator."
    if "what time" in t or "tell me the time" in t:
        return time.strftime("It is %I:%M %p")
    if "shutdown" in t or "restart" in t or "delete" in t or "format" in t:
        return "That is a potentially dangerous action. I will not perform it automatically."
    return None


def ask_llm(prompt):
    if not OPENAI_AVAILABLE or not getattr(openai, 'api_key', None):
        return None
    try:
        resp = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            messages=[{"role": "system", "content": "You are a helpful assistant."},
                      {"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=250,
        )
        return resp.choices[0].message.content.strip()
    except Exception as e:
        print("OpenAI error:", e)
        return None


def listen_once(timeout=5, phrase_time_limit=8):
    with sr.Microphone() as source:
        print("Listening... (speak now)")
        r.adjust_for_ambient_noise(source, duration=0.4)
        try:
            audio = r.listen(source, timeout=timeout, phrase_time_limit=phrase_time_limit)
        except sr.WaitTimeoutError:
            return ""
    try:
        text = r.recognize_google(audio)
        print("You:", text)
        return text
    except sr.UnknownValueError:
        return ""
    except Exception as e:
        print("STT error:", e)
        return ""


def main_loop():
    speak(f"Hello. I am {APP_NAME}. Press Enter, then speak a command.")
    while True:
        try:
            input("Press Enter to speak (or Ctrl-C to quit)...")
        except KeyboardInterrupt:
            print("Exiting...")
            break

        user_text = listen_once()
        if not user_text:
            speak("I didn't catch that. Try again.")
            continue

        # quick allowlist actions
        result = run_allowed_action(user_text)
        if result:
            speak(result)
            continue

        # If OpenAI key configured, ask LLM for a helpful answer
        llm_prompt = f"User said: '{user_text}'. Provide a short helpful response (or suggest an ACTION: open-notepad/search:<query> if appropriate)."
        llm_answer = ask_llm(llm_prompt)
        if llm_answer:
            print("LLM:", llm_answer)
            # naive ACTION parsing
            if llm_answer.startswith("ACTION:"):
                action = llm_answer.split(":", 1)[1].strip()
                safe = run_allowed_action(action)
                if safe:
                    speak(safe)
                else:
                    speak("I can't perform that action automatically.")
            else:
                speak(llm_answer)
            continue

        # fallback: do a web search for the phrase and tell user
        speak("I can search the web for that. Opening your browser.")
        webbrowser.open(f"https://www.google.com/search?q={user_text.replace(' ', '+')}")


if __name__ == '__main__':
    try:
        # Ensure config dir exists
        if not os.path.exists(CONFIG_DIR):
            os.makedirs(CONFIG_DIR, exist_ok=True)
            # create example config
            cfg = configparser.ConfigParser()
            cfg['openai'] = {'api_key': ''}
            with open(CONFIG_PATH, 'w') as f:
                cfg.write(f)

        main_loop()
    except Exception as e:
        print("Fatal error:", e)
        sys.exit(1)
