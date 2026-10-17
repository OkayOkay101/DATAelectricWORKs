import pandas as pd
import numpy as np

# Mocking df_display
N = 500000
df_display = pd.DataFrame({'Clock': pd.date_range('2023-01-01', periods=N, freq='15min')})
df_display['Date'] = df_display['Clock'].dt.normalize()

# what is the type of element from unique()?
available_dates = sorted(df_display['Date'].unique())
print(type(available_dates[0]))
