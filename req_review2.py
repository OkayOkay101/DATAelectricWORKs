plan = """
1. **Task 1: Optimize numeric conversions in `data_handler.py`**
   - **Problem:** `astype(str).str.replace(regex)` across entire arrays followed by `pd.to_numeric` is slow.
   - **Action:** Edit `data_handler.py` to optimize numeric conversions for `kW_Import` and `Voltage` in `preprocess_data` by applying `pd.to_numeric` first and handling the NaN failures. Specifically, use `pd.to_numeric(..., errors='coerce')`, and only apply the regex cleanup to the rows that return NaN, replacing values back into the numeric series.

2. **Task 2: Optimize date extraction in `data_handler.py`**
   - **Problem:** `df['Clock'].dt.date` creates slow Python `datetime.date` objects.
   - **Action:** Edit `data_handler.py` to replace `df['Date'] = df['Clock'].dt.date` with `df['Date'] = df['Clock'].dt.normalize()` in `preprocess_data`.

3. **Task 3: Optimize datetime filtering in `app.py`**
   - **Problem:** In `app.py`, filtering `df_new_recalc['Original_Clock'].dt.date == view_date` evaluates using slow python objects.
   - **Action:** Edit `app.py` to replace `plot_new = df_new_recalc[df_new_recalc['Original_Clock'].dt.date == view_date].sort_values('Clock')` with `plot_new = df_new_recalc[df_new_recalc['Original_Clock'].dt.normalize() == pd.Timestamp(view_date)].sort_values('Clock')`.
   - **Action:** Edit `app.py` to update the date input filtering condition in tab 4. Streamlit's `st.date_input` returns `datetime.date`, so `df_summary = df_display[(df_display['Date'] >= start_date) & (df_display['Date'] <= end_date)]` and `df_summary = df_display[df_display['Date'] == date_range[0]]` will raise errors when comparing with `datetime64`. Convert `start_date`, `end_date`, and `date_range[0]` to `pd.Timestamp` before comparison. E.g. `pd.Timestamp(start_date)`. Also, replace `available_dates = sorted(df_display['Date'].unique())` with `available_dates = [pd.Timestamp(d).date() for d in sorted(df_display['Date'].unique())]` or explicitly cast `sel_date` to `pd.Timestamp` in `day_df = df_display[df_display['Date'] == pd.Timestamp(sel_date)].copy()` to preserve UI display and ensure equality works. Do the same for `dates_for_shift` / `view_date` and `df_display['Date'] == st.selectbox(...)`. To keep it simple, I will explicitly cast `sel_date` and `view_date` and `st.selectbox` returns to `pd.Timestamp` where `df_display['Date'] == ...` occurs, and update `unique()` logic to extract `.date()` for presentation if needed.

4. **Task 4: Run Tests**
   - Run `python scripts/check_python_syntax.py` to verify the syntax of the changes.

5. **Task 5: Complete pre commit steps**
   - Complete pre-commit steps to ensure proper testing, verification, review, and reflection are done.

6. **Task 6: Report Results**
   - Write results, update `.jules/bolt.md` journal if new learnings found, and submit.
"""
print(plan)
