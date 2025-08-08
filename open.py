import requests, string, random, time, threading, questionary, os
from colorama import Fore, init
from concurrent.futures import ThreadPoolExecutor

init(autoreset=True)

WEBHOOK_FILE = "webhook.txt"
AVAILABLE_FILE = "available_usernames.txt"
TOKENS_FILE = "tokens.txt"
PROXIES_FILE = "proxies.txt"
THEME_PATH = "theme.txt"
WORD_API_URL = "https://random-word-api.herokuapp.com/word?number=100"

MODES = {
    "3 Characters (letters+digits+_.)": ("c", 3),
    "3 Letters (a-z)": ("l", 3),
    "3 Digits (0-9)": ("d", 3),
    "4 Characters (letters+digits+_.)": ("c", 4),
    "4 Letters (a-z)": ("l", 4),
    "4 Digits (0-9)": ("d", 4),
    "High Tier Words (via API)": ("words", 0),
}

COLOR_THEMES = {
    "White": Fore.WHITE, "Red": Fore.RED, "Green": Fore.GREEN,
    "Cyan": Fore.CYAN, "Magenta": Fore.MAGENTA,
    "Yellow": Fore.YELLOW, "Light Blue": Fore.LIGHTBLUE_EX,
    "Orange": Fore.LIGHTRED_EX,
}

lock = threading.Lock()
stop_flag = False
available, invalid_tokens = [], []
tokens = []
proxies, proxy_index = [], 0
stats = {"checked": 0, "available": 0, "taken": 0, "errors": 0}

def clear(): os.system("cls" if os.name == "nt" else "clear")

def get_font_color():
    if not os.path.exists(THEME_PATH):
        open(THEME_PATH, "w").write("White")
    return COLOR_THEMES.get(open(THEME_PATH).read().strip().title(), Fore.WHITE)

def set_font_color():
    choice = questionary.select("🎨 Select a text color:", list(COLOR_THEMES.keys())).ask()
    open(THEME_PATH, "w").write(choice)
    print(Fore.GREEN + f"[✔] Theme saved as {choice}")
    input("Press Enter to return...")

def about():
    print(Fore.CYAN + """
✨ Discord Username Sniper ✨
✔ Token validation & stats panel
✔ Rotating tokens + proxies
✔ Multi-threaded checks
✔ Webhook alerts & saved results
""")
    input("Press Enter to return...")

def load_list(path):
    return [l.strip() for l in open(path).read().splitlines() if l.strip()] if os.path.exists(path) else []

def load_tokens():
    global tokens
    raw = load_list(TOKENS_FILE)
    tokens = raw.copy()
    if not tokens:
        print(Fore.RED + "[!] No tokens found in tokens.txt")
        exit()

def load_proxies():
    global proxies
    for line in load_list(PROXIES_FILE):
        try:
            u, rest = line.split("@")
            user, pw = u.split(":")
            host, port = rest.split(":")
            proxies.append({
                "http": f"socks5h://{user}:{pw}@{host}:{port}",
                "https": f"socks5h://{user}:{pw}@{host}:{port}"
            })
        except: pass

def next_proxy():
    global proxy_index
    if not proxies: return None
    with lock:
        p = proxies[proxy_index]
        proxy_index = (proxy_index + 1) % len(proxies)
    return p

def token_validator():
    valid = []
    print(Fore.CYAN + "[*] Validating tokens…")
    for t in tokens:
        try:
            r = requests.get("https://discord.com/api/v9/users/@me", headers={"Authorization": t}, timeout=10)
            if r.status_code == 200:
                valid.append(t)
            else:
                invalid_tokens.append(t)
        except:
            invalid_tokens.append(t)
    tokens[:] = valid
    print(Fore.GREEN + f"[✔] Tokens valid: {len(valid)} | Invalid: {len(invalid_tokens)}")
    if not tokens:
        print(Fore.RED + "[!] No valid tokens remaining. Exiting.")
        exit()
    time.sleep(1)

def show_stats():
    clr = get_font_color()
    s = stats
    print(clr + f"\n📊 Stats → Checked: {s['checked']} | Available: {s['available']} | Taken: {s['taken']} | Errors: {s['errors']}\n")

def gen_usernames(mode, length, amt):
    if mode == "words":
        try:
            # Fetch a larger number of words to ensure we get 'amt' unique words
            words = requests.get(WORD_API_URL, timeout=5).json()
            random.shuffle(words) # Shuffle to get different words each time
            return words[:amt]
        except:
            return []
    base = string.ascii_lowercase
    if mode == "c": base += string.digits + "_."
    elif mode == "d": base = string.digits
    return [''.join(random.choice(base) for _ in range(length)) for _ in range(amt)]

def notify_save(username):
    with lock:
        available.append(username)
        stats["available"] += 1
        with open(AVAILABLE_FILE, "a") as f: f.write(username + "\n")
    try:
        requests.post(WEBHOOK_FILE, json={"content": f"@everyone\nAvailable: {username}"})
    except:
        pass

def check(username, color):
    global stats
    headers = {"Content-Type": "application/json", "User-Agent": "Discord/12345"}
    for attempt in range(3):
        if stop_flag: return
        token = random.choice(tokens)
        headers["Authorization"] = token
        proxy = next_proxy()
        try:
            r = requests.post("https://discord.com/api/v9/users/@me/pomelo-attempt",
                              json={"username": username}, headers=headers, proxies=proxy, timeout=10)
            with lock:
                stats["checked"] += 1
            if r.status_code == 200:
                d = r.json()
                if not d.get("taken", True):
                    notify_save(username)
                    print(color + f"[✔] {username} is AVAILABLE!")
                else:
                    with lock:
                        stats["taken"] += 1
                    print(Fore.LIGHTBLACK_EX + f"[-] {username} is taken")
                return
            elif r.status_code == 429:
                wait = int(r.headers.get("Retry-After", 5))
                print(Fore.YELLOW + f"[!] Ratelimited: waiting {wait}s")
                time.sleep(wait + random.random())
            else:
                with lock:
                    stats["errors"] += 1
                return
        except requests.exceptions.RequestException as e: # Catch network-related errors specifically
            with lock:
                stats["errors"] += 1
            # print(Fore.RED + f"[X] Error checking {username}: {e}") # Optional: for debugging
            time.sleep(2 ** attempt)
        except Exception as e: # Catch other unexpected errors
            with lock:
                stats["errors"] += 1
            # print(Fore.RED + f"[X] Unexpected error for {username}: {e}") # Optional: for debugging
            time.sleep(2 ** attempt)


def monitor_cancel():
    global stop_flag
    while True:
        if input().lower() == "q":
            stop_flag = True
            print(Fore.RED + "\n[!] Stopping… Please wait.")
            break

def run_checker():
    global stop_flag
    clear(); stop_flag = False
    print(get_font_color() + "📛 Username Checker Mode")

    if not os.path.exists(AVAILABLE_FILE):
        open(AVAILABLE_FILE, "w").close()

    userchoice = questionary.select("🔢 Select mode:", list(MODES.keys())).ask()
    mode, length = MODES[userchoice]
    count = questionary.text("💬 How many usernames do you want to check?", validate=lambda x: x.isdigit() and int(x) > 0).ask()
    count = int(count)

    # --- New: Ask for Thread Count ---
    thread_count = questionary.text("⚙️ How many threads do you want to use? (e.g., 10, 20, 50)", validate=lambda x: x.isdigit() and int(x) > 0).ask()
    thread_count = int(thread_count)
    # ---------------------------------

    print(get_font_color() + f"[~] Generating {count} usernames...")
    names = gen_usernames(mode, length, count)
    if not names:
        print(Fore.RED + "[!] Failed to generate usernames. Please check your internet connection for 'High Tier Words' mode or try another mode.")
        input(Fore.GREEN + "\n[✔] Press Enter to return to menu...")
        return

    print(get_font_color() + "⏳ Starting checks… Type 'q' to stop\n")
    threading.Thread(target=monitor_cancel, daemon=True).start()

    # --- Use the chosen thread_count in ThreadPoolExecutor ---
    with ThreadPoolExecutor(max_workers=thread_count) as pool:
        # We use a list comprehension with map to ensure all tasks are submitted
        # map will block until all submitted tasks are complete or stop_flag is set
        for _ in pool.map(lambda u: check(u, get_font_color()), names):
            if stop_flag:
                # If stop_flag is set, we need to manually shutdown the executor
                # and break out of the loop
                pool.shutdown(wait=False, cancel_futures=True)
                break
    # ---------------------------------------------------------

    show_stats()
    input(Fore.GREEN + "\n[✔] Done. Press Enter to return to menu...")

def main():
    clear()
    load_proxies()
    load_tokens()
    token_validator()
    while True:
        clear()
        show_stats()
        print(Fore.CYAN + "🎯 MAIN MENU 🎯")
        choice = questionary.select("Choose action:", ["Checker", "Settings", "About", "Exit"]).ask()
        if choice == "Checker": run_checker()
        elif choice == "Settings": set_font_color()
        elif choice == "About": about()
        else: break

if __name__ == "__main__":
    main()