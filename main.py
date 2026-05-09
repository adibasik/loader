import webview
import json
import os
import sys
import threading
import subprocess
import urllib.request
import zipfile
import shutil
import platform
from pathlib import Path

# Пытаемся импортировать webview-proc
try:
    from webview_proc import WebViewProcess
    USE_WEBVIEW_PROC = True
except ImportError:
    USE_WEBVIEW_PROC = False
    print("webview-proc not installed, using regular pywebview")

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "config.json")

DEFAULT_CONFIG = {
    "language": "ru",
    "minecraft_dir": "",
    "username": "",
    "ram": 2048,
    "java_path": "",
    "theme": "dark",
    "last_version": "1.21.1",
}

FABRIC_INSTALLER_URL = "https://maven.fabricmc.net/net/fabricmc/fabric-installer/1.0.1/fabric-installer-1.0.1.jar"
FABRIC_VERSION = "1.21.1"
FABRIC_LOADER = "0.16.5"

RECOMMENDED_MODS = [
    {
        "id": "sodium",
        "name": "Sodium",
        "desc_ru": "Оптимизация рендеринга, резкий прирост FPS",
        "desc_en": "Rendering optimization, massive FPS boost",
        "url": "https://modrinth.com/mod/sodium",
        "required": False,
        "category": "performance",
        "icon": "⚡"
    },
    {
        "id": "iris",
        "name": "Iris Shaders",
        "desc_ru": "Поддержка шейдеров для Sodium",
        "desc_en": "Shader support for Sodium",
        "url": "https://modrinth.com/mod/iris",
        "required": False,
        "category": "visual",
        "icon": "🌈"
    },
    {
        "id": "lithium",
        "name": "Lithium",
        "desc_ru": "Оптимизация игровой логики и физики",
        "desc_en": "Game logic and physics optimization",
        "url": "https://modrinth.com/mod/lithium",
        "required": False,
        "category": "performance",
        "icon": "🔋"
    },
    {
        "id": "ferrite",
        "name": "FerriteCore",
        "desc_ru": "Снижение использования оперативной памяти",
        "desc_en": "Memory usage reduction",
        "url": "https://modrinth.com/mod/ferrite-core",
        "required": False,
        "category": "performance",
        "icon": "💾"
    },
    {
        "id": "entityculling",
        "name": "Entity Culling",
        "desc_ru": "Не рендерит невидимые сущности",
        "desc_en": "Skip rendering hidden entities",
        "url": "https://modrinth.com/mod/entityculling",
        "required": False,
        "category": "performance",
        "icon": "👁"
    },
    {
        "id": "modmenu",
        "name": "Mod Menu",
        "desc_ru": "Список всех установленных модов в игре",
        "desc_en": "In-game list of all installed mods",
        "url": "https://modrinth.com/mod/modmenu",
        "required": True,
        "category": "utility",
        "icon": "📋"
    },
    {
        "id": "fabricapi",
        "name": "Fabric API",
        "desc_ru": "Обязательная библиотека для большинства модов",
        "desc_en": "Required library for most mods",
        "url": "https://modrinth.com/mod/fabric-api",
        "required": True,
        "category": "utility",
        "icon": "🧩"
    },
    {
        "id": "minimap",
        "name": "Xaero's Minimap",
        "desc_ru": "Компактная мини-карта с маркерами",
        "desc_en": "Compact minimap with markers",
        "url": "https://modrinth.com/mod/xaeros-minimap",
        "required": False,
        "category": "utility",
        "icon": "🗺"
    },
]


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
                for k, v in DEFAULT_CONFIG.items():
                    if k not in cfg:
                        cfg[k] = v
                return cfg
        except Exception:
            pass
    return DEFAULT_CONFIG.copy()


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def get_default_mc_dir():
    system = platform.system()
    home = Path.home()
    if system == "Windows":
        return str(home / "AppData" / "Roaming" / ".minecraft")
    elif system == "Darwin":
        return str(home / "Library" / "Application Support" / "minecraft")
    else:
        return str(home / ".minecraft")


def find_java():
    try:
        result = subprocess.run(
            ["java", "-version"],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return "java"
    except Exception:
        pass

    # Common Java locations on Windows
    java_paths = [
        r"C:\Program Files\Eclipse Adoptium",
        r"C:\Program Files\Java",
        r"C:\Program Files\Microsoft",
        r"C:\Program Files (x86)\Java",
    ]
    for base in java_paths:
        if os.path.exists(base):
            try:
                for d in os.listdir(base):
                    exe = os.path.join(base, d, "bin", "java.exe")
                    if os.path.exists(exe):
                        return exe
                    # Check direct bin folder
                    if d == "bin":
                        exe = os.path.join(base, "java.exe")
                        if os.path.exists(exe):
                            return exe
            except Exception:
                continue
    return "java"


def get_html_path():
    """Get correct path to HTML file (works for development and frozen builds)"""
    if getattr(sys, 'frozen', False):
        # Running as compiled executable
        base_path = sys._MEIPASS
    else:
        # Running as script
        base_path = os.path.dirname(os.path.abspath(__file__))
    
    html_path = os.path.join(base_path, "web", "index.html")
    
    # If not found, try current directory
    if not os.path.exists(html_path):
        html_path = os.path.join(os.getcwd(), "web", "index.html")
    
    return html_path


class LauncherAPI:
    def __init__(self):
        self.config = load_config()
        self.window = None
        self._launch_progress = 0

    def set_window(self, window):
        self.window = window

    # ── Config ────────────────────────────────────────────────────────────────

    def get_config(self):
        return json.dumps(self.config)

    def save_settings(self, data):
        try:
            cfg = json.loads(data)
            self.config.update(cfg)
            save_config(self.config)
            return json.dumps({"ok": True})
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)})

    # ── System info ───────────────────────────────────────────────────────────

    def get_system_info(self):
        info = {
            "os": platform.system(),
            "os_version": platform.version(),
            "python": sys.version,
            "java": find_java(),
            "default_mc_dir": get_default_mc_dir(),
            "mc_dir_exists": os.path.exists(
                self.config.get("minecraft_dir") or get_default_mc_dir()
            ),
        }
        return json.dumps(info)

    def pick_folder(self):
        try:
            if self.window:
                # Try to use webview file dialog
                result = self.window.create_file_dialog(
                    webview.FOLDER_DIALOG
                )
                if result and len(result) > 0:
                    return json.dumps({"path": result[0]})
        except Exception as e:
            print(f"WebView dialog error: {e}")
        
        # Fallback to tkinter dialog
        try:
            import tkinter as tk
            from tkinter import filedialog
            
            root = tk.Tk()
            root.withdraw()  # Hide the main window
            folder = filedialog.askdirectory(title="Выберите папку .minecraft")
            root.destroy()
            
            if folder:
                return json.dumps({"path": folder})
        except Exception as e:
            print(f"Tkinter dialog error: {e}")
        
        return json.dumps({"path": ""})

    # ── Mods ──────────────────────────────────────────────────────────────────

    def get_mods(self):
        mc_dir = self.config.get("minecraft_dir") or get_default_mc_dir()
        mods_dir = os.path.join(mc_dir, "mods")
        installed = []
        if os.path.exists(mods_dir):
            installed = [f.lower() for f in os.listdir(mods_dir) if f.endswith(".jar")]
        
        result = []
        for mod in RECOMMENDED_MODS:
            m = mod.copy()
            # Check if mod is installed (by checking if mod id appears in filename)
            m["installed"] = any(mod["id"].lower() in f for f in installed)
            result.append(m)
        return json.dumps(result)

    def open_mod_url(self, url):
        import webbrowser
        webbrowser.open(url)
        return json.dumps({"ok": True})

    # ── Fabric install ────────────────────────────────────────────────────────

    def check_fabric(self):
        mc_dir = self.config.get("minecraft_dir") or get_default_mc_dir()
        versions_dir = os.path.join(mc_dir, "versions")
        fabric_installed = False
        fabric_version_found = ""
        
        if os.path.exists(versions_dir):
            for v in os.listdir(versions_dir):
                if "fabric" in v.lower() and FABRIC_VERSION in v:
                    fabric_installed = True
                    fabric_version_found = v
                    break
        
        return json.dumps({
            "installed": fabric_installed, 
            "version": FABRIC_VERSION, 
            "loader": FABRIC_LOADER,
            "found_version": fabric_version_found
        })

    def install_fabric(self):
        def _install():
            try:
                self._emit("fabric_progress", {"step": "download", "pct": 0})
                tmp = os.path.join(os.path.dirname(__file__), "fabric-installer.jar")

                def _progress(count, block, total):
                    if total > 0:
                        pct = int(count * block * 100 / total)
                        self._emit("fabric_progress", {"step": "download", "pct": min(pct, 90)})

                urllib.request.urlretrieve(FABRIC_INSTALLER_URL, tmp, _progress)
                self._emit("fabric_progress", {"step": "install", "pct": 90})

                java = self.config.get("java_path") or find_java() or "java"
                mc_dir = self.config.get("minecraft_dir") or get_default_mc_dir()

                # Ensure minecraft directory exists
                os.makedirs(mc_dir, exist_ok=True)

                # Run fabric installer
                result = subprocess.run([
                    java, "-jar", tmp,
                    "client",
                    "-mcversion", FABRIC_VERSION,
                    "-loader", FABRIC_LOADER,
                    "-dir", mc_dir,
                    "-noprofile"
                ], capture_output=True, text=True)

                if result.returncode != 0:
                    raise Exception(f"Fabric installer failed: {result.stderr}")

                # Clean up
                if os.path.exists(tmp):
                    os.remove(tmp)
                    
                self._emit("fabric_progress", {"step": "done", "pct": 100})
            except Exception as e:
                self._emit("fabric_progress", {"step": "error", "pct": 0, "error": str(e)})

        threading.Thread(target=_install, daemon=True).start()
        return json.dumps({"ok": True})

    # ── Launch ────────────────────────────────────────────────────────────────

    def launch_game(self):
        def _launch():
            try:
                self._emit("launch_status", {"step": "checking", "pct": 10})
                
                mc_dir = self.config.get("minecraft_dir") or get_default_mc_dir()
                username = self.config.get("username") or "Player"
                ram = self.config.get("ram") or 2048
                java = self.config.get("java_path") or find_java() or "java"

                if not os.path.exists(mc_dir):
                    self._emit("launch_status", {"step": "error", "error": "Minecraft directory not found"})
                    return

                # Find fabric version json
                versions_dir = os.path.join(mc_dir, "versions")
                fabric_ver = None
                fabric_json = None
                
                if os.path.exists(versions_dir):
                    for v in os.listdir(versions_dir):
                        if "fabric" in v.lower() and FABRIC_VERSION in v:
                            fabric_ver = v
                            fabric_json = os.path.join(versions_dir, v, f"{v}.json")
                            break

                if not fabric_ver or not os.path.exists(fabric_json):
                    self._emit("launch_status", {"step": "error", "error": "Fabric not installed. Please install Fabric first."})
                    return

                self._emit("launch_status", {"step": "launching", "pct": 60})

                # Build launch command
                game_dir = mc_dir
                assets_dir = os.path.join(mc_dir, "assets")
                libraries_dir = os.path.join(mc_dir, "libraries")
                
                # Simple launch using Minecraft launcher
                system = platform.system()
                
                if system == "Windows":
                    # Try to find Minecraft Launcher
                    launcher_paths = [
                        os.path.join(os.environ.get("ProgramFiles", ""), "Minecraft Launcher", "MinecraftLauncher.exe"),
                        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Minecraft Launcher", "MinecraftLauncher.exe"),
                        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Minecraft Launcher", "MinecraftLauncher.exe")
                    ]
                    
                    launched = False
                    for path in launcher_paths:
                        if os.path.exists(path):
                            subprocess.Popen([path])
                            launched = True
                            break
                    
                    if not launched:
                        # Open .minecraft folder as fallback
                        os.startfile(mc_dir)
                        
                elif system == "Darwin":  # macOS
                    subprocess.Popen(["open", "-a", "Minecraft"])
                else:  # Linux
                    subprocess.Popen(["minecraft-launcher"])

                self._emit("launch_status", {"step": "done", "pct": 100})
            except Exception as e:
                self._emit("launch_status", {"step": "error", "error": str(e)})

        threading.Thread(target=_launch, daemon=True).start()
        return json.dumps({"ok": True})

    # ── News ──────────────────────────────────────────────────────────────────

    def get_news(self):
        news = [
            {
                "id": 1,
                "date": "2025-05-01",
                "title_ru": "Обновление до Fabric 0.16.5",
                "title_en": "Updated to Fabric 0.16.5",
                "body_ru": "Лоадер обновлён до версии 0.16.5 — улучшена совместимость с модами и исправлены критические баги.",
                "body_en": "Loader updated to 0.16.5 — improved mod compatibility and fixed critical bugs.",
                "tag": "update"
            },
            {
                "id": 2,
                "date": "2025-04-20",
                "title_ru": "Добавлен список рекомендуемых модов",
                "title_en": "Recommended mods list added",
                "body_ru": "Теперь в лаунчере есть раздел с рекомендуемыми модами для оптимизации и удобства игры.",
                "body_en": "Launcher now has a section with recommended mods for optimization and quality of life.",
                "tag": "feature"
            },
            {
                "id": 3,
                "date": "2025-04-10",
                "title_ru": "Поддержка Minecraft 1.21.1",
                "title_en": "Minecraft 1.21.1 support",
                "body_ru": "Лаунчер теперь поддерживает Minecraft 1.21.1 с Fabric. Проверьте настройки Java.",
                "body_en": "Launcher now supports Minecraft 1.21.1 with Fabric. Check your Java settings.",
                "tag": "release"
            },
        ]
        return json.dumps(news)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _emit(self, event, data):
        """Send event to JavaScript frontend"""
        if self.window:
            try:
                # Escape properly for JavaScript
                import json as json_module
                data_str = json_module.dumps(data)
                # Use a safer approach to call JavaScript
                js_code = f"""
                (function() {{
                    if (window.onPyEvent && typeof window.onPyEvent === 'function') {{
                        window.onPyEvent('{event}', {data_str});
                    }}
                }})();
                """
                self.window.evaluate_js(js_code)
            except Exception as e:
                print(f"Emit error: {e}")


def main():
    """Main entry point for the launcher"""
    global USE_WEBVIEW_PROC
    api = LauncherAPI()
    html_path = get_html_path()
    
    # Check if HTML file exists
    if not os.path.exists(html_path):
        print(f"Error: HTML file not found at {html_path}")
        print("Creating web directory and index.html...")
        
        # Create web directory if it doesn't exist
        web_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
        os.makedirs(web_dir, exist_ok=True)
        
        # Create a minimal index.html
        index_path = os.path.join(web_dir, "index.html")
        with open(index_path, "w", encoding="utf-8") as f:
            f.write("""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Fabric Launcher</title>
    <style>
        body { font-family: Arial; padding: 20px; background: #0a0a0f; color: white; }
    </style>
</head>
<body>
    <h1>Fabric Launcher</h1>
    <p>Loading... Please create the full web interface.</p>
    <script>
        console.log("Minimal interface loaded");
    </script>
</body>
</html>""")
        html_path = index_path
    
    print(f"Loading HTML from: {html_path}")
    
    # Choose between webview-proc and regular webview
    if USE_WEBVIEW_PROC:
        print("Using webview-proc (separate process)")
        try:
            wv_proc = WebViewProcess(
                title="Fabric Launcher — 1.21.1",
                url=f"file://{html_path}",
                width=1100,
                height=700,
                min_size=(900, 600),
                resizable=True,
                background_color="#0a0a0f",
                js_api=api
            )
            
            api.set_window(wv_proc)
            wv_proc.start()
            wv_proc.join()
        except Exception as e:
            print(f"Error with webview-proc: {e}")
            print("Falling back to regular pywebview...")
            USE_WEBVIEW_PROC = False
    
    if not USE_WEBVIEW_PROC:
        # Fallback to regular pywebview
        print("Using regular pywebview")
        window = webview.create_window(
            title="Fabric Launcher — 1.21.1",
            url=f"file://{html_path}",
            js_api=api,
            width=1100,
            height=700,
            min_size=(900, 600),
            resizable=True,
            frameless=False,
            background_color="#0a0a0f",
        )
        
        api.set_window(window)
        webview.start(debug=False, http_server=True)


if __name__ == "__main__":
    main()