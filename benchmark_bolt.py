import time
import numpy as np
import pandas as pd
from datetime import time as dtime
from tou_analyzer import _apply_tou_and_anomaly_cached

def run_benchmark():
    raw_func = _apply_tou_and_anomaly_cached.__wrapped__ if hasattr(_apply_tou_and_anomaly_cached, '__wrapped__') else _apply_tou_and_anomaly_cached

    holidays = ('2026-01-01', '2026-04-13', '2026-05-01', '2026-07-28', '2026-12-05', '2026-12-31')
    p_start = dtime(9, 0)
    p_end = dtime(22, 0)
    p_rate = 5.7982
    op_rate = 2.6369
    sensitivity = 2.5

    for n in [200_000, 500_000]:
        dates = pd.date_range('2026-01-01', periods=n, freq='15min')
        df = pd.DataFrame({
            'Clock': dates,
            'Date': dates.normalize(),
            'Month': dates.strftime('%Y-%m'),
            'kW_Import': np.random.uniform(10, 100, n),
            'kWh_15min': np.random.uniform(2.5, 25, n),
            'Voltage': np.random.uniform(215, 230, n),
        })

        # Warm up
        for _ in range(3):
            raw_func(df, sensitivity, p_start, p_end, p_rate, op_rate, holidays)

        runs = 20
        t0 = time.perf_counter()
        for _ in range(runs):
            raw_func(df, sensitivity, p_start, p_end, p_rate, op_rate, holidays)
        t1 = time.perf_counter()
        avg_ms = (t1 - t0) / runs * 1000
        print(f"Dataset {n:,} rows: {avg_ms:.2f} ms")

if __name__ == '__main__':
    run_benchmark()
