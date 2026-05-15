import streamlit.web.cli as stcli
import os, sys

def resolve_path(path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, path)
    return os.path.join(os.path.abspath("."), path)

if __name__ == "__main__":
    sys.argv = [
        "streamlit",
        "run",
        resolve_path("electric_app.py"),
        "--global.developmentMode=false",
    ]
    sys.exit(stcli.main())