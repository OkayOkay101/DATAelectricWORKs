import unittest
import pandas as pd
import numpy as np
from data_handler import preprocess_data

class TestDataHandler(unittest.TestCase):

    def test_preprocess_data_negative_values(self):
        # Create a mock DataFrame with negative values that might need string cleaning
        data = {
            'Clock': ['01/01/2023 00:15', '01/01/2023 00:30', '01/01/2023 00:45'],
            'kW_Import': ['-10.5', 'abc-20.7xyz', -30.0],
            'Voltage': ['-220.5', 'volt-230.1', -240.0]
        }
        df = pd.DataFrame(data)

        # Call preprocess_data
        result_df = preprocess_data(df)

        # Verify the length is correct
        self.assertEqual(len(result_df), 3)

        # Check if the negative values are preserved in kW_Import
        self.assertEqual(result_df.loc[0, 'kW_Import'], -10.5)
        self.assertEqual(result_df.loc[1, 'kW_Import'], -20.7)
        self.assertEqual(result_df.loc[2, 'kW_Import'], -30.0)

        # Check if the negative values are preserved in Voltage
        self.assertEqual(result_df.loc[0, 'Voltage'], -220.5)
        self.assertEqual(result_df.loc[1, 'Voltage'], -230.1)
        self.assertEqual(result_df.loc[2, 'Voltage'], -240.0)

if __name__ == '__main__':
    unittest.main()
