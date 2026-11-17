"""Windows launcher for the packaged Load Profile & TOU Simulator.

Starts the bundled Streamlit app on a free localhost port and opens the browser.
Built with PyInstaller (onedir).
"""
import os
import socket
import sys
import threading
import webbrowser


def resource_path(relative_path):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, relative_path)


def pick_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def build_flag_options(port):
    # Streamlit's bootstrap expects CLI-style keys (underscores, not dots).
    return {
        "server_port": port,
        "server_address": "127.0.0.1",
        "server_headless": True,
        "global_developmentMode": False,
        "browser_gatherUsageStats": False,
    }


def main():
    from streamlit.web import bootstrap

    port = pick_free_port()
    url = f"http://127.0.0.1:{port}"
    flag_options = build_flag_options(port)
    # The streamlit CLI applies flag options before bootstrap.run; do the same here.
    bootstrap.load_config_options(flag_options=flag_options)
    threading.Timer(3.0, lambda: webbrowser.open(url)).start()
    print(f"Load Profile & TOU Simulator running at {url}")
    print("Close this window to stop the app.")
    bootstrap.run(resource_path("app.py"), False, [], flag_options)


if __name__ == "__main__":
    main()
