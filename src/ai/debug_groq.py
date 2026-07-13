import traceback

try:
    import groq
    print("Groq imported successfully.")
    print("File path:", groq.__file__)
    try:
        print("Version:", groq.__version__)
    except Exception:
        print("Version: not available")
        
    print("Attempting to initialize Groq client...")
    client = groq.Groq(api_key="gsk_dummy")
    print("Success!")
except Exception:
    print("Initialization failed.")
    traceback.print_exc()
