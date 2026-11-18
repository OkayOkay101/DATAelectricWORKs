# Developer Guide

This guide is for people who change the code, run the tests, or build the Windows app. For using the app, see the [User Guide](USER_GUIDE_EN.md).

## Requirements

- **Python 3.12** is recommended. The CI workflows use Python 3.12.
- **App libraries:** `pandas`, `numpy`, `plotly`, `streamlit`, `openpyxl`, `xlrd`, `xlwt`. The install command is in the [README](../README.md).
- **Windows build:** `packaging/build_windows.ps1` installs `pandas==2.2.3` and `numpy==2.1.3`, plus `streamlit`, `plotly`, `openpyxl`, `xlrd`, `xlwt`, and `pyinstaller`.
- **Test libraries:** `requirements-test.txt` pins `pandas==2.2.3` and `numpy==2.1.3`, and requires `streamlit>=1.35.0` and `plotly>=5.0.0`.

## Run the tests

From the repository root:
```bash
pip install -r requirements-test.txt
python -m unittest discover -s tests -p "test_*.py"
```

The test files are in `tests/`. Some of them check that the documentation says what the code does, for example `test_functional_test_docs.py` and `test_mock_data_docs.py`.

## CI workflows

The workflows are in `.github/workflows/`.

| Workflow | Runs when | What it does |
| :--- | :--- | :--- |
| `python-baseline.yml` | push, pull_request, manual | Runs `scripts/check_python_syntax.py` on Python 3.12. It parses the Python files tracked by Git without importing them. Timeout 5 minutes. |
| `python-functional.yml` | push, pull_request, manual | Runs the unittest command above on Python 3.12. Timeout 10 minutes. See [FUNCTIONAL_TESTS_EN.md](FUNCTIONAL_TESTS_EN.md). |
| `jules-quality.yml` | pull_request that changes files under `.github/quality/`, the workflow, or `tests/test_quality_runner.py`; manual with inputs | Self-test for the quality adapter. Timeout 15 minutes. See [TEST_QUALITY_EN.md](TEST_QUALITY_EN.md). |

## Build the Windows app

Run from the repository root:
```powershell
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1
powershell -ExecutionPolicy Bypass -File packaging\build_windows.ps1 -Python "C:\Path\To\python.exe" -Version 1.0.0
```

Parameters:
- `-Python`: the Python executable to use. Default `python`.
- `-Version`: the version used in the zip name. Default `1.0.0`.

The script installs the dependencies, runs PyInstaller in onedir mode with `packaging\launcher.py` as the entry point, and then creates a zip. Output (written to the `dist` folder):
- The app folder named DATAelectricWORKs, which contains DATAelectricWORKs.exe
- A zip file named DATAelectricWORKs-v{Version}-windows-x64.zip, where {Version} is the value of `-Version`

`packaging/launcher.py` picks a free port on `127.0.0.1`, starts the bundled `app.py` with Streamlit, and opens the browser after about 3 seconds. Closing the console window stops the app.

## Project layout

| Path | Purpose |
| :--- | :--- |
| `app.py` | Streamlit user interface |
| `data_handler.py` | Upload checks, file parsing, and preprocessing |
| `tou_analyzer.py` | TOU period assignment, cost, and anomaly detection |
| `generate_mock_data.py` | Creates sample data in `mock_data/` (`.csv`, `.xlsx`, `.txt`) |
| `run_main.py` | Starts the app with Streamlit |
| `packaging/` | Windows build script and launcher |
| `scripts/` | Repo checks, such as the syntax check |
| `tests/` | Unit and documentation tests |
| `docs/` | Documentation |
| `.github/` | CI workflows and the quality adapter |

`mock_data/` also holds `mock_dataset.xls`, which `generate_mock_data.py` does not create. Other root files, such as `benchmark_bolt.py`, are not described here.
