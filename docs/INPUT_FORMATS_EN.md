# Input Format Guide

This guide describes the input formats the system accepts. It is based on `data_handler.py` and `generate_mock_data.py`.

## 1. Supported file types
- Supported files: `.csv`, `.txt`, `.xls`, `.xlsx`

## 2. Columns and header row
The header row must be in the **first 50 lines** of the file. The system finds columns by the keywords below (case-insensitive):

* **Date / Clock:** supports separate columns (for example Date and Clock) or one combined column (for example Clock, Time, Datetime, CH1, เวลา, วันที่).
* **Import energy (kW_Import):** finds columns that contain `kW` together with `Import`, `Export`, or `Demand`; columns with `Active Power`; columns named พลังงาน or กำลังไฟฟ้า; a column named `CH4`; or a column named just `kW`. Columns that contain `kWh` are never selected.
  * *Limit:* if several columns match, the system picks **one** column with the highest total in the first 20 rows. It does not combine several columns, which prevents the chart from showing 0 values.
* **Voltage:** finds columns that contain `Voltage`, `Volt`, `V`, แรงดัน, or `CH3`. If none is found, the default is 220.

* *Column name limit:* if column names are duplicated, the system renames each duplicate by adding `_` and its column position (for example `kw_5`).

## 3. Delimiters (TXT and CSV)
The system detects and supports these delimiters:
- Comma `,`
- Tab
- Semicolon `;`
- Space

## 4. Date and time parsing
- Supports date-times that start with the day, such as `dd/mm/yyyy HH:MM` (parsed with `pd.to_datetime(dayfirst=True)`).
- If a time cell holds an invalid value (for example `total`, `p`, `op`, `h`, `kwh`, `nan`, or dnv/err), that row is skipped.

## 5. Numeric values
- The system removes other text and symbols with a regular expression that keeps only digits, decimal points, and minus signs.
- Values of **2,000,000 or more** in `kW_Import` or `Voltage` are **not removed**. The system shows a warning with the number of rows found, and you should check the data.

## 6. Sample input
This sample comes from the first row of `mock_data/mock_dataset.csv`, which is committed to the repo. Note that the current `generate_mock_data.py` starts at 00:00 and uses random values, so the committed file may not match what the script produces now.

```csv
Clock,kW_Import,Voltage
2026-01-01T10:00:00,10,220
```

## Verification and status
- **Source:** the rules above were read from `data_handler.py` and `generate_mock_data.py` in the current version.
- **Not yet tested:** this document has not been checked against real user files.

## More reference
See the English user guide [USER_GUIDE_EN.md](USER_GUIDE_EN.md).
