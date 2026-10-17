plan = """
1. **Task 1: Optimize numeric conversions in `data_handler.py`**
   - **Problem:** `astype(str).str.replace(regex)` across entire arrays followed by `pd.to_numeric` is slow.
   - **Evidence:** Our benchmark showed optimizing the `df['kW_Import']` parsing by attempting `pd.to_numeric` first, and only applying regex to rows that failed (`isna()`), improves parsing time from ~0.5s to ~0.002s when most data is valid.
   - **Action:** In `preprocess_data`, convert `kW_Import` and `Voltage` to numeric directly, and selectively regex-clean and re-parse only those elements that fail.

2. **Task 2: Optimize date extraction in `data_handler.py`**
   - **Problem:** `df['Clock'].dt.date` returns Python `datetime.date` objects, which takes ~0.16s for 500k rows. In pandas filtering `datetime.date` vs `pd.Timestamp` filtering logic impacts performance.
   - **Evidence:** We've seen `dt.normalize()` is ~10x faster (~0.015s). The agent memory mentions using `.dt.normalize()`.
   - **Action:** We will replace `df['Date'] = df['Clock'].dt.date` with `df['Date'] = df['Clock'].dt.normalize()`.

3. **Task 3: Optimize datetime filtering in `app.py`**
   - **Problem:** When querying `Date` equality, Streamlit dates are passed as `datetime.date`, leading to scalar comparisons. And `Original_Clock.dt.date == view_date` evaluates using slow python objects.
   - **Evidence:** `df[df['Original_Clock'].dt.date == view_date]` took 0.22s, while `df[df['Original_Clock'].dt.normalize() == view_date_ts]` took 0.02s.
   - **Action:** Ensure Streamlit UI dates selected are cast to `pd.Timestamp` when filtering DataFrames by the new `Date` (which will be `datetime64` thanks to Task 2). Also update the `plot_new` selection condition to use `.dt.normalize() == pd.Timestamp(view_date)`.

4. **Task 4: Complete pre commit steps**
   - Ensure proper testing, verification, review, and reflection are done.

5. **Task 5: Report Results**
   - Write results, update `.jules/bolt.md` journal if new learnings found, and submit.
"""
print(plan)
