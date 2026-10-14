import sys
from pathlib import Path

root_dir = str(Path(__file__).resolve().parent.parent.parent.parent)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)

import nifty_algo_core as core
from nifty_algo_core import *
