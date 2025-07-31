
from src.backtesting_engine.theta_connection_manager import ThetaConnectionManager
import time

manager = ThetaConnectionManager()
manager._validate_setup()
manager._start_theta_process()

# Keep the script alive to keep the terminal running
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    manager.cleanup()
