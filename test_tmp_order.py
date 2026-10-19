import sys

# simulate test_data_handler loading
class MockSt:
    pass
sys.modules['streamlit'] = MockSt()

# simulate test_app running afterwards
try:
    from streamlit.testing.v1 import AppTest
except ImportError as e:
    print("Caught:", e)

# Now what if I delete it and reload?
del sys.modules['streamlit']
import streamlit
from streamlit.testing.v1 import AppTest
print("Success!")
