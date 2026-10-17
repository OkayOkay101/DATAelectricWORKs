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
