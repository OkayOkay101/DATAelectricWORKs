try:
    import streamlit.testing.v1
    print("Success")
except Exception as e:
    print("Exception", repr(e))
