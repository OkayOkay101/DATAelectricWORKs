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

## 2026-10-30 - Dynamic Column CSV Parsing vs Fixed names=range(50)
**Learning:** Setting a fixed `names=range(50)` in `pd.read_csv()` to guard against potential ragged metadata header lines forces Pandas to allocate 50 full columns of string objects across hundreds of thousands of rows. For a 200k-row dataset with only 3 actual columns, this needlessly constructs over 9.4 million empty/NaN string objects, inflating parsing time by over 6.6x and slowing subsequent column filtering and header detection.
**Action:** Attempt reading CSV files with `header=None` first, allowing the Pandas C parser to size the table dynamically based on actual columns. Catch parser exceptions and fall back to `names=range(50)` only when uneven or ragged rows actually occur. This preserves 100% backward compatibility while achieving up to 6.6x faster CSV loading.


## 2026-10-30 - Selective Snapshot Boundary Timestamp Formatting
**Learning:** In `get_usage_snapshots()`, formatting the entire `Clock` datetime Series into strings using `.astype(str)` and string slicing across hundreds of thousands of rows allocates over 1.6 million temporary string objects (~331 ms for 200k rows, or ~745 ms if string parsing is needed). However, only the start and end boundary timestamps of active machine sessions (`pad_s_array` and `pad_e_array`) are ever needed for session labels.
**Action:** Slice only the required boundary timestamps (`clock_series.iloc[np.concatenate((pad_s_array, pad_e_array))]`) before parsing and formatting as strings. This eliminates redundant formatting across inactive rows, achieving over 100x speedup (down to ~3.2 ms for 200k rows) while ensuring 100% parity.

## 2026-10-30 - Vectorized Numeric Month and Time_Str Mapping vs Full Series String Conversion
**Learning:** In `preprocess_data()`, converting the entire `Clock` datetime Series to strings via `Clock.astype(str)` followed by `.str.slice()` to extract `Month` (`YYYY-MM`) and `Time_Str` (`HH:MM`) takes ~250 ms for 200k rows, allocating over 600,000 temporary Python string objects. In reality, timestamps in 15-minute or hourly intervals have very low distinct cardinalities (only 96 unique time-of-day slots, and ~12 unique months per year).
**Action:** Compute numeric combinations using fast integer properties (`clock_dt.year * 100 + clock_dt.month` and `clock_dt.hour * 60 + clock_dt.minute`), then map only the small set of unique values using `.map(dict)` (`f'{v // 60:02d}:{v % 60:02d}'`). This eliminates redundant allocations across hundreds of thousands of rows, achieving an 8.8x speedup for month/time formatting (~28 ms vs ~252 ms for 200k rows) and cutting overall `preprocess_data` execution time by ~28% while guaranteeing 100% exact parity.

## 2026-10-31 - Vectorized Unique Value Mapping for CSV Formula Sanitization
**Learning:** In `sanitize_dataframe_for_csv()`, iterating over object/string columns with `.map(sanitize_csv_cell)` executes Python function calls row-by-row on every single element. For a 200k-row dataset with 4 object columns (`Month`, `Time_Str`, `Period_Detail`, `Anomaly_Type`), this invokes `sanitize_csv_cell` 800,000 times (~252 ms for 200k rows, ~627 ms for 500k rows). In reality, categorical and formatted columns in TOU load profiles have very low unique cardinalities (e.g. 3 periods, 3 anomaly types, 96 time slots, ~12-60 months), and safe values without formula prefixes need no modification.
**Action:** Extract unique values per string column (`s.unique()`), evaluate `sanitize_csv_cell` only on the unique set, and conditionally map back with `.map(dict)` only if dangerous formula prefixes actually exist. This reduces cell sanitization calls from 800,000+ down to ~170 calls, achieving an 8.15x to 8.55x speedup (~30.95 ms vs ~252.12 ms for 200k rows, an 88% reduction in runtime) while guaranteeing 100% exact DataFrame equality.
