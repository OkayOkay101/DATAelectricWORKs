# Troubleshooting Guide

This guide helps you fix the import and calculation problems most often seen in the app. It is based on the source code in `app.py`, `data_handler.py`, and `tou_analyzer.py`.

For installation and general use, see the other guides linked from the README.

## 1. Source review

Reviewing the source code (`data_handler.py`, `app.py`, `tou_analyzer.py`) shows the following behavior:

* **Missing imports (a file fails to load):**
  * `load_file` in `data_handler.py` accepts `.csv`, `.xls`, `.xlsx`, and text data.
  * If reading fails, the function tries to read the file as plain text, line by line, with these encodings: `utf-8-sig`, `cp874`, `utf-16`, `utf-16le`, and `tis-620`.
  * If no table can be extracted, or no time column (`Clock`) is found, the system raises `UploadValidationError` (a subclass of `ValueError`) and skips that file. `app.py` then shows the message "⚠️ ข้ามไฟล์... (ไม่มีข้อมูลเวลา)" (file skipped, no time data).

* **Unrecognized headers:** `parse_excel_df` and `parse_text_lines` in `data_handler.py` search for text such as `clock`, `date`, `ch1`, `kw`, `import`, `เวลา`, and `พลังงาน` (case-insensitive) to find the header row within the first 50 lines.
  * The required columns are a time column and an energy column. If either is missing, the system treats the file as having no usable data.

* **Invalid timestamps:** in `preprocess_data`, the `Clock` column is converted to datetime with `pd.to_datetime(..., dayfirst=True, errors='coerce')`. Values that cannot be converted become NaT and are dropped (`df.dropna(subset=['Clock'])`).

* **Empty data:** if a file has no data, or the DataFrame is empty after processing, `preprocess_data` returns an empty DataFrame. `app.py` checks for this. If no DataFrame passes the check, it shows the message "⚠️ ไม่มีข้อมูลที่สามารถนำมาวิเคราะห์ได้เลย โปรดตรวจสอบไฟล์ที่อัปโหลด" (no data could be analyzed; check the uploaded files).

* **Calculation assumptions** (`tou_analyzer.py`):
  * All rows start as **Off-Peak**.
  * **On-Peak** applies only inside the configured time window, and not on Saturday or Sunday (`Is_Weekend` is True for weekdays 5 and 6, Saturday and Sunday), and not on a holiday listed in `holiday_list`.
  * Weekend and holiday rows are labeled `Holiday` and use the Off-Peak/Holiday rate.
  * Energy cost (`Cost_THB`) = `kWh_15min × Rate_THB`.
  * Anomaly detection: rows with `kW_Import` ≤ 0.05 (treated as inactive) are left out of the mean and standard deviation. The high threshold is mean + sensitivity × SD, and the low threshold is max(0.01, mean − sensitivity × SD). `sensitivity` is set by the user.

## 2. Runtime checks and suggestions

The suggestions below are based on the code above. They are not bug fixes.

* **A file uploads with no data, or is skipped:**
  * Check that the file has a date/time column (for example `Date`, `Clock`, or `เวลา`) and an energy column (for example `kW`, `Import kW`, or `Active Power`) that match the names the system looks for.
  * Delete unneeded header lines so that the header row is within the first 50 lines of the file.
* **Energy (kWh) or cost is wrong:**
  * The system assumes each row covers 15 minutes, so `kWh_15min = kW_Import / 4.0`. If the data is not at a 15-minute interval, the computed cost will be wrong.
  * Check that the rate settings (On-Peak / Off-Peak / Single Rate) and the holiday list match the month and year of your data, because the cost depends on which days are holidays.
* **Peak / Off-Peak periods look wrong:**
  * Saturday and Sunday are charged the Off-Peak/Holiday rate all day, and the chart shows them in the Holiday color (yellow).
  * The times on the chart depend on which timestamps were converted successfully. If the chart has gaps, check that the time column in the source file matches a format the system can read (for example DD/MM/YYYY HH:MM).
