"""Test configuration.

Force the whole suite into deterministic offline mode and disable disk writes,
regardless of any .env on the machine. ``load_dotenv`` does not override values
already present in the environment, so setting these here wins.
"""

import os

os.environ["FABLE5_OFFLINE"] = "true"
os.environ["FABLE5_WRITE_CODE"] = "false"
