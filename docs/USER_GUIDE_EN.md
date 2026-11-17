# User Guide: Load Profile & TOU Simulator

> 🇹🇭 ภาษาไทย: [USER_GUIDE_TH.md](USER_GUIDE_TH.md)

This guide is for new users. It explains what the app can do, what you need before you start, how to use it step by step, and what each screen shows.

> If the app is not installed yet, start with the [Quickstart Guide](GETTING_STARTED_TH.md) (Thai).
> If an upload fails, see [Input Formats](INPUT_FORMATS_TH.md) and [Troubleshooting](TROUBLESHOOTING_TH.md) (both Thai).

---

## 1. What the App Does

The app takes **Load Profile** files (electricity usage recorded over time, usually every 15 minutes, from a utility or a data logger) and helps you:

- **See an overview of energy use**, such as total energy (kWh), peak demand (kW), and estimated electricity cost.
- **Inspect daily data** to see which days use the most power and at what times of day the load is highest.
- **Detect anomalies**, such as load above normal or unusually low load (sags).
- **Simulate shifting usage in time**, for example moving work out of the On-Peak period, and see how the cost changes.
- **Calculate cost** under either **TOU** (Time of Use: different rates by time period) or **Single Rate** tariffs.
- **Download results** as CSV files.

The app runs in your web browser on your own computer. Your data is not sent to any other service.

---

## 2. What You Need

1. **An electricity usage file** with a time column and a power (kW) column. Supported formats: `.csv`, `.txt`, `.xlsx`, `.xls`.
   - If you do not have a real file yet, download the sample template from the "📥 ดาวน์โหลดไฟล์ตัวอย่างแม่แบบ (.csv)" button (Download sample template) on the welcome screen.
2. **The app installed** by following the [Quickstart Guide](GETTING_STARTED_TH.md) (Thai).
3. **The app started** with `streamlit run app.py`. Your browser opens the app automatically.

Upload limits:

| Item | Maximum |
| :--- | :--- |
| Files per upload | 20 |
| Size per file | 50 MB |
| Total size of all files | 200 MB |

---

## 3. Screen Overview

The screen has two main areas.

### Left Sidebar (settings)

| Section | What it does |
| :--- | :--- |
| **1. Upload data** | Drag files in or click to choose files to analyze. |
| **2. Billing settings** | Choose the tariff type, enter rates, set the On-Peak hours, and list holidays. |
| **3. Display settings** | Choose the chart style (bar or line) and adjust anomaly sensitivity. |

### Main Area

- **Before you upload:** a welcome screen shows steps 1 to 3 and the sample template download button.
- **After you upload:** the app shows the date and time range of the data, the number of rows, a period filter, and four tabs.

---

## 4. Step-by-Step Usage

### Step 1: Upload Files

1. In the sidebar, under **1. Upload data**, drag your files in or click to select them.
2. If you upload several files, the app combines them automatically.
3. If a file cannot be read, the app shows a "⚠️ ข้ามไฟล์ที่อ่านไม่ได้" (Skipped unreadable files) message with the reason and continues with the files that can be read.
4. When the upload succeeds, you see "✅ วิเคราะห์ข้อมูลสำเร็จ" (Analysis successful), and the date and time range of the data appears below it.

### Step 2: Set Up Billing

1. Choose the **tariff type**.
   - **TOU (Time of Use):** the rate depends on the time period. Enter both the On-Peak rate and the Off-Peak / Holiday rate.
   - **Single Rate:** the same rate applies at all times. Enter one rate.
2. Check the rates under "ตั้งค่าเรทราคา (บาท/หน่วย)" (Rate settings, THB per unit) against your electricity bill. The default values are examples only.
3. Set the **On-Peak** hours under "ตั้งค่าเวลา On-Peak" (On-Peak time settings). The default is 09:00 to 22:00.
   - If the start and end times are the same, the app charges no On-Peak rate at all.
   - If the end time is earlier than the start time, the On-Peak period crosses midnight.
4. Check the **holiday list** under "ตั้งค่าวันหยุดนักขัตฤกษ์" (Public holiday settings). Enter dates as `YYYY-MM-DD`, separated by commas. Days in the list are charged at the Off-Peak / Holiday rate for the whole day.
   - Holiday entries that are malformed or not real dates are ignored.
   - The default list covers the current year. To use another year, edit the list yourself.

### Step 3: Choose a Period Filter (if available)

Under the data date range, a filter section labeled **"🔍 กรองช่วงเวลา"** (Filter by time period) appears with a selector for the machine operating cycle (snapshot). If the data contains several operating cycles, choose the one you want to view. Every tab then calculates only for that period.

### Step 4: Review the Results

See section 5 below for what each tab shows.

---

## 5. What Each Tab Shows

### Tab 1: Energy Overview

- **Four metric cards**
  - ⚡ **Total energy (kWh):** total energy in the selected period.
  - 🔥 **Peak demand (kW):** the highest power value that occurred.
  - 💰 **Estimated electricity cost (THB):** calculated from the rates in the sidebar.
  - 📊 **Average power (kW)**
- **Total demand and anomalies chart (kW):** the load curve over the full period, with triangle markers for abnormal load.
  - ▲ Red = load above the threshold.
  - ▼ Blue = low load (sag).
- **kW and kWh charts at 15-minute intervals**, and a **daily total energy (kWh) chart**, with a downloadable daily summary table.

Period colors in the charts:

| Color | Meaning |
| :--- | :--- |
| 🟧 Orange | On-Peak (the configured hours on working days) |
| 🟩 Green | Off-Peak (weekday hours outside On-Peak) |
| 🟨 Yellow | Holiday (a date in the holiday list, or Saturday and Sunday) |

### Tab 2: Daily Insights

- Pick a day in the **"📅 เลือกวันที่ต้องการเจาะลึก"** (Select a date to inspect) box.
- See summary cards for that day and a 15-minute chart with anomaly markers.
- View a 15-minute data table and download that day's data.
- If no dates are available, the app shows a message that no date data was found.

### Tab 3: Shift Graph

Use this tab to test **what happens if you move when power is used**.

1. Enter **minutes to shift** in steps of 15.
   - Positive values (+) move the load later.
   - Negative values (-) move it earlier.
   - 0 keeps the original time.
2. Choose the date you want to compare.
3. The app shows:
   - A comparison line chart. The solid dark blue line is the original data. The dashed red line is the shifted data.
   - A cost simulation result that says whether the cost goes down, goes up, or stays the same, with the amount in THB and the percentage.
4. You can download the simulation result.

> Example: if you move heavy load from 10:00 to after 22:00, which is Off-Peak, the estimated cost goes down.

### Tab 4: Cost Analysis & Simulator

Choose one of four summary scopes.

| Scope | Meaning |
| :--- | :--- |
| Total | Summary for the whole file |
| Monthly | Summary per month |
| Daily | Summary per day; choose a date |
| Custom | Choose your own start and end dates |

Results include energy by period (On-Peak, Off-Peak, Holiday), cost by period, and total cost, with tables and a CSV download.

The simulator in this tab works the same way as Tab 3: enter the minutes to shift and see the difference in cost.

---

## 6. Glossary

| Term | Meaning |
| :--- | :--- |
| **Load profile** | Power readings recorded continuously over time, usually every 15 minutes. |
| **kW (kilowatt)** | Power at one moment in time. |
| **kWh (kilowatt-hour)** | Energy used over a period. The app calculates each 15-minute interval as kW ÷ 4, because 15 minutes is 0.25 hours. |
| **TOU (Time of Use)** | A tariff with different rates for different time periods. |
| **On-Peak** | The period with the highest configured rate, usually weekday daytime hours. |
| **Off-Peak** | The period with the lower rate: weekday hours outside On-Peak. |
| **Holiday** | A public holiday listed in the holiday list, and also Saturday and Sunday. These days are charged at the Off-Peak / Holiday rate for the whole day. |
| **Anomaly** | A value much higher or lower than normal. The app calculates it from the mean and standard deviation of the data. You can adjust sensitivity in the sidebar. |

---

## 7. Tips and Cautions

- **Check the rates every time.** The default values are examples. The cost shown is an **estimate**, not the amount you will actually be billed.
- **Anomaly sensitivity:** a lower setting reports more anomalies. A higher setting reports only clearly abnormal points.
- **Unrealistic values:** kW values above 2,000,000 are treated as outliers and removed.
- **Rows with invalid timestamps** are skipped.
- **Try the sample file first** to see the format the app expects.

---

## 8. Related Documents

The following documents are currently available in Thai only:

- [Quickstart Guide](GETTING_STARTED_TH.md): installation and starting the app
- [Input Formats](INPUT_FORMATS_TH.md): columns, delimiters, and supported date formats
- [Troubleshooting](TROUBLESHOOTING_TH.md): warning messages and how to fix them
- [Functional Tests](FUNCTIONAL_TESTS_TH.md): behavior guaranteed by the tests
