# Quickstart Guide

Welcome to **Load Profile & TOU Simulator**. This guide covers the basic steps to install and start the app.

## 1. Prerequisites

The app needs these Python libraries (as the code actually uses them):
- `pandas`
- `numpy`
- `plotly`
- `streamlit`
- `openpyxl` (reads and writes Excel `.xlsx` files)
- `xlrd` (reads Excel `.xls` files)
- `xlwt` (installed by the command below, but no import of it is found in the current code)

## 2. Set up a virtual environment

To keep the app's libraries separate from your system Python, create and activate a virtual environment.

### Create it
Open a terminal or Command Prompt and run:
```bash
python -m venv venv
```

### Activate it
- **Windows:**
  ```cmd
  venv\Scripts\activate
  ```
- **macOS / Linux:**
  ```bash
  source venv/bin/activate
  ```

After activating, install the libraries:
```bash
pip install pandas numpy plotly streamlit openpyxl xlrd xlwt
```

## 3. Start the app

The app is a web application built with Streamlit. Start it with:
```bash
streamlit run app.py
```
Your browser opens the app automatically.

## 4. Optional: start through the launcher

You can also start the app with `run_main.py`. It runs Streamlit with the settings written in that file:
```bash
python run_main.py
```

## 5. Create sample data (mock data)

If you do not have real data for testing, you can create sample files in `.csv`, `.xlsx`, and `.txt` formats:
```bash
python generate_mock_data.py
```
The files are written to the `mock_data/` folder, ready to upload into the app.

## More reference
See the Thai user guide [USER_GUIDE_TH.md](USER_GUIDE_TH.md) and the English user guide [USER_GUIDE_EN.md](USER_GUIDE_EN.md).
