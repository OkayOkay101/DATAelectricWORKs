# Load Profile & TOU Simulator

Analyze electricity **load profile** data (power readings, usually every 15 minutes) and simulate **TOU (Time of Use)** or single-rate electricity cost. The app runs in your web browser on your own computer, so your data stays local.

> 🇹🇭 ภาษาไทย: [README_TH.md](README_TH.md)

## What it does

1. **Upload** `.csv`, `.txt`, `.xlsx`, or `.xls` files (up to 20 files, 50 MB each, 200 MB total). Multiple files are combined automatically.
2. **Configure billing**: choose TOU or single rate, enter the rates, the On-Peak hours, and a holiday list.
3. **Review results** in four tabs:
   - **Energy Overview**: total energy (kWh), peak demand (kW), estimated cost, and anomalies.
   - **Daily Insights**: a 15-minute chart and table for a selected day.
   - **Shift Graph**: move load earlier or later and compare it with the original.
   - **Cost Analysis**: cost summaries by total, month, day, or custom date range.
4. **Download** the results as CSV files.

For a full walkthrough, see the [User Guide](docs/USER_GUIDE_EN.md).

## Download (Windows)

Download the latest build from the [Releases page](https://github.com/OkayOkay101/DATAelectricWORKs/releases). Extract the zip and double-click `DATAelectricWORKs.exe`. Python does not need to be installed.

The executable is not digitally signed, so Windows may show a SmartScreen warning. Choose "More info", then "Run anyway", if you trust the download.

## Run from source

Requirements: Python 3.12 is recommended.

```bash
python -m venv venv
venv\Scripts\activate            # macOS / Linux: source venv/bin/activate
pip install pandas numpy plotly streamlit openpyxl xlrd xlwt
streamlit run app.py
```

To generate sample data, run `python generate_mock_data.py`. This creates files in `mock_data/`.

## Documentation

For developers (tests, CI, Windows build, project layout), see the [Developer Guide](docs/DEVELOPMENT_EN.md).

| Document | Language |
| :--- | :--- |
| [User Guide](docs/USER_GUIDE_EN.md) / [คู่มือผู้ใช้งาน](docs/USER_GUIDE_TH.md) | EN / TH |
| [Quickstart Guide](docs/GETTING_STARTED_EN.md) / [คู่มือเริ่มต้นใช้งานอย่างรวดเร็ว](docs/GETTING_STARTED_TH.md) | EN / TH |
| [Input Formats](docs/INPUT_FORMATS_EN.md) / [รูปแบบข้อมูลนำเข้า](docs/INPUT_FORMATS_TH.md) | EN / TH |
| [Troubleshooting](docs/TROUBLESHOOTING_EN.md) / [แก้ปัญหาการใช้งาน](docs/TROUBLESHOOTING_TH.md) | EN / TH |
| [Developer Guide](docs/DEVELOPMENT_EN.md) / [คู่มือนักพัฒนา](docs/DEVELOPMENT_TH.md) | EN / TH |
| [Functional Tests](docs/FUNCTIONAL_TESTS_EN.md) / [การทดสอบเชิงฟังก์ชัน](docs/FUNCTIONAL_TESTS_TH.md) | EN / TH |
| [Test Quality](docs/TEST_QUALITY_EN.md) / [คุณภาพของการทดสอบ](docs/TEST_QUALITY_TH.md) | EN / TH |

## License

No license file has been added yet.
