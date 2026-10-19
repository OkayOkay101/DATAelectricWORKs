import pandas as pd
import numpy as np
import os

def generate_mock_data():
    # 1. Create a date range for 2 days with 15-minute intervals
    dates = pd.date_range(start="2026-01-01 00:00", end="2026-01-02 23:45", freq="15min")

    # 2. Generate random base values
    np.random.seed(42)
    kw_import = []
    voltage = []

    for dt in dates:
        # Daytime load vs nighttime load
        if 8 <= dt.hour <= 18:
            kw = np.random.normal(loc=200, scale=20) # Daytime load
        else:
            kw = np.random.normal(loc=50, scale=10) # Nighttime load

        v = np.random.normal(loc=220, scale=2) # Normal voltage

        kw_import.append(kw)
        voltage.append(v)

    df = pd.DataFrame({
        "Clock": dates.strftime("%d/%m/%Y %H:%M"),
        "kW_Import": kw_import,
        "Voltage": voltage
    })

    # 3. Add power spikes and drops
    # Spikes
    df.loc[30, "kW_Import"] = 450.0  # Spike on day 1
    df.loc[140, "kW_Import"] = 500.0 # Spike on day 2
    df.loc[30, "Voltage"] = 245.0

    # Drops
    df.loc[70, "kW_Import"] = 5.0    # Drop on day 1
    df.loc[180, "kW_Import"] = 0.0   # Drop on day 2
    df.loc[70, "Voltage"] = 190.0

    # Ensure positive kw
    df["kW_Import"] = df["kW_Import"].clip(lower=0).round(2)
    df["Voltage"] = df["Voltage"].round(2)

    # 4. Create the output directory
    output_dir = "mock_data"
    os.makedirs(output_dir, exist_ok=True)

    # 5. Save the data in various formats
    # CSV
    df.to_csv(f"{output_dir}/mock_dataset.csv", index=False)

    # Excel (.xlsx)
    df.to_excel(f"{output_dir}/mock_dataset.xlsx", index=False)

    # TXT (Comma separated)
    df.to_csv(f"{output_dir}/mock_dataset.txt", index=False, sep=",")

    print("Mock datasets generated successfully in 'mock_data' folder.")

if __name__ == "__main__":
    generate_mock_data()
