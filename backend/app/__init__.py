import sys
from pathlib import Path

# Add project root directory to sys.path so modules can import nifty_algo_core, nifty_algo_live, etc.
root_dir = str(Path(__file__).resolve().parent.parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)
backend_dir = str(Path(__file__).resolve().parent.parent)
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
