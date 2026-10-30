## 2024-03-24 - Pandas Date and Time Accessors Bottleneck
**Learning:** In Pandas, operations using `.dt.time` and `.dt.strftime()` to extract time/date string objects from a datetime column are extremely slow because they create Python objects for each row instead of using vectorized NumPy operations.
**Action:** Replace `.dt.time` comparisons with integer calculations derived from `.dt.hour`, `.dt.minute`, `.dt.second`. Replace string date checks (`.dt.strftime('%Y-%m-%d').isin(...)`) with datetime comparisons (`.dt.normalize().isin(pd.to_datetime(...))`).
## 2024-10-16 - Pandas Date and Time Accessors Bottleneck 2
**Learning:** In Pandas, operations using `.dt.strftime()` to extract time/date string objects from a datetime column are extremely slow. They can be replaced with `.astype(str)` and vectorized string slicing (`str.slice`). However, `pd.NaT` becomes a string (`"nan"` or `"NaT"`) under `.astype(str)`. Also, datetimes without a time component (e.g. exactly midnight) might omit the time in `.astype(str)`, yielding an empty string when sliced.
**Action:** Replace `.dt.strftime` with vectorized string slicing, but ensure `NaT` handling is explicit (`series.loc[df['Clock'].isna()] = np.nan`) and empty time strings are handled (`.replace('', '00:00')`).


## 2024-03-24 - Pandas map vs apply
**Learning:** Using `.apply()` with a Python function to map values in a Pandas series is slow because it executes at the Python level.
**Action:** Replace `.apply(func)` with `.map(dict)` using a dictionary for simple value translations.
## 2024-10-17 - Fast Pandas Data Cleaning and Filtering
**Learning:** Cleaning numeric strings in pandas by blindly applying `.str.replace(regex)` across an entire series is slow. Calling `.dt.date` to filter dates creates slow python `datetime.date` objects.
**Action:** Use `pd.to_numeric(series, errors='coerce')` first, and only apply the regex cleanup on the elements that failed to parse (`mask = num.isna()`). To filter datetimes by date, use `.dt.normalize() == pd.Timestamp(date)` instead of `.dt.date == date`.

## 2026-10-17 - Streamlit Date vs Pandas Datetime Selection Performance
**Learning:** Extracting `df['Date'] = df['Clock'].dt.date` forces the creation of python `datetime.date` objects, making equality filtering in Pandas very slow (e.g., 0.22s per filter for 500k rows). While switching to `df['Date'] = df['Clock'].dt.normalize()` is 10x faster (0.02s per filter) and uses vectorized operations, it breaks compatibility with `st.date_input` and `st.selectbox` UI states which rely on or return `datetime.date`.
**Action:** When filtering a DataFrame in Streamlit using a normalized Datetime64 column, extract `.date()` selectively for UI elements (`[pd.Timestamp(d).date() for d in unique_dates]`), but cast the returned variable back with `pd.Timestamp()` when querying against the DataFrame.

## 2026-10-17 - Pandas to_numeric vs str.replace Regex Cleanup
**Learning:** Cleaning numeric strings across a large Series using `astype(str).str.replace(r'[^\d.]', '', regex=True)` takes significant time (0.6s to 0.9s per column for 500k rows), even if most of the data is already valid numbers.
**Action:** Always attempt `pd.to_numeric(series, errors='coerce')` first. If invalid entries exist (`isna().any()`), apply the slow regex cleanup *only* to the failed rows (`df.loc[mask]`), and patch them back in. This reduces parsing time to under 0.005s when most data is clean.

## 2026-10-30 - Fast Vectorized Datetime Parsing vs format='mixed'
**Learning:** Using `pd.to_datetime(series, format='mixed')` across large datasets (hundreds of thousands of rows) falls back to row-by-row Python `dateutil` parsing, taking 7 to 30+ seconds for 200k rows. In reality, timestamps in load profile files follow consistent formats (such as `%d/%m/%Y %H:%M` or ISO 8601).
**Action:** Inspect sample timestamps and attempt vectorized C-speed parsing using candidate `format` strings with `errors='coerce'`. If any valid entries fail to parse (e.g., occasional mixed/corrupted formats), selectively fallback to `format='mixed'` only on the failed rows (`df.loc[mask_failed]`). This achieves up to 9-20x speedup while guaranteeing exact parity.
