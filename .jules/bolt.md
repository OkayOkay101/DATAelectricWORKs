## 2024-03-24 - Pandas Date and Time Accessors Bottleneck
**Learning:** In Pandas, operations using `.dt.time` and `.dt.strftime()` to extract time/date string objects from a datetime column are extremely slow because they create Python objects for each row instead of using vectorized NumPy operations.
**Action:** Replace `.dt.time` comparisons with integer calculations derived from `.dt.hour`, `.dt.minute`, `.dt.second`. Replace string date checks (`.dt.strftime('%Y-%m-%d').isin(...)`) with datetime comparisons (`.dt.normalize().isin(pd.to_datetime(...))`).

## 2024-03-24 - Pandas map vs apply
**Learning:** Using `.apply()` with a Python function to map values in a Pandas series is slow because it executes at the Python level.
**Action:** Replace `.apply(func)` with `.map(dict)` using a dictionary for simple value translations.
