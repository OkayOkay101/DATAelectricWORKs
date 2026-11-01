import time
import numpy as np
import pandas as pd
from data_handler import parse_excel_df

def make_test_df(n, seed=42):
    rng = np.random.default_rng(seed)
    dates = pd.date_range('2026-01-01', periods=n, freq='15min')
    date_col = dates.strftime('%d/%m/%Y')
    time_col = dates.strftime('%H:%M')
    kw_col = rng.uniform(10, 100, n).astype(str)

    raw = pd.DataFrame({
        'c0': ['Date'] + list(date_col),
        'c1': ['Time'] + list(time_col),
        'c2': ['kW'] + list(kw_col),
    })
    return raw

def legacy_parse_excel_df(df_raw):
    # Legacy implementation of parse_excel_df
    import re
    if df_raw is None or len(df_raw) == 0:
        return None

    header_row_idx = 0
    cols = ['date', 'time', 'kw']
    df = df_raw.iloc[header_row_idx+1:].reset_index(drop=True)
    df.columns = cols

    clock_series = df['time']
    date_series = df['date']
    kw_series = df['kw']

    invalid_pattern = r'^(?:total.*|p|op|h|kwh|nan)$'
    invalid_clock_pattern = r'^(?:total.*|p|op|h|kwh|nan|dnv/err)$'
    re_clock = re.compile(invalid_clock_pattern)
    u_c = clock_series.unique()
    map_c = {}
    for v in u_c:
        if pd.isna(v):
            map_c[v] = False
        else:
            s = str(v).strip().lower()
            map_c[v] = False if (not s or (s[0] in 'tpohknd' and re_clock.match(s))) else True
    mask_c = clock_series.map(map_c).fillna(False).astype(bool)

    re_date = re.compile(invalid_pattern)
    u_d = date_series.unique()
    map_d = {}
    for v in u_d:
        if pd.isna(v):
            map_d[v] = False
        else:
            s = str(v).strip().lower()
            map_d[v] = False if (not s or (s[0] in 'tpohkn' and re_date.match(s))) else True
    mask_d = date_series.map(map_d).fillna(False).astype(bool)
    valid_mask = mask_c & mask_d

    valid_mask_np = valid_mask.to_numpy()
    clock_valid = clock_series[valid_mask_np]
    kw_valid = kw_series[valid_mask_np]
    date_valid = date_series[valid_mask_np]

    u_dv = date_valid.unique()
    d_strip_map = {v: str(v).strip() for v in u_dv}
    u_cv = clock_valid.unique()
    c_strip_map = {v: str(v).strip() for v in u_cv}
    merged_clock = date_valid.map(d_strip_map).astype(str) + ' ' + clock_valid.map(c_strip_map).astype(str)

    out_df = pd.DataFrame({
        'Clock': merged_clock.reset_index(drop=True),
        'kW_Import': kw_valid.reset_index(drop=True),
        'Voltage': 220.0
    })
    return out_df

def benchmark():
    for n in [100_000, 200_000, 500_000]:
        raw = make_test_df(n)

        # Warm up
        for _ in range(3):
            legacy_parse_excel_df(raw)
            parse_excel_df(raw)

        runs = 15
        t0 = time.perf_counter()
        for _ in range(runs):
            res_leg = legacy_parse_excel_df(raw)
        t1 = time.perf_counter()
        leg_ms = (t1 - t0) / runs * 1000

        t0 = time.perf_counter()
        for _ in range(runs):
            res_opt = parse_excel_df(raw)
        t1 = time.perf_counter()
        opt_ms = (t1 - t0) / runs * 1000

        pd.testing.assert_frame_equal(res_leg, res_opt)
        reduction = (leg_ms - opt_ms) / leg_ms * 100
        factor = leg_ms / opt_ms
        print(f"End-to-End parse_excel_df {n:,} rows: Legacy={leg_ms:.2f} ms | Optimized={opt_ms:.2f} ms | Reduction={reduction:.1f}% ({factor:.2f}x)")

if __name__ == '__main__':
    benchmark()
