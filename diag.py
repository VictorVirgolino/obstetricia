import sys
import platform
import os

print(f"Python version: {sys.version}")
print(f"Platform: {platform.platform()}")
print(f"Executable: {sys.executable}")
print(f"Current Directory: {os.getcwd()}")
try:
    import sqlite3
    print("sqlite3: Available")
except ImportError:
    print("sqlite3: NOT Available")

try:
    import pandas
    print(f"pandas: Available ({pandas.__version__})")
except ImportError:
    print("pandas: NOT Available")
