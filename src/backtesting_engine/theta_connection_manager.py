#!/usr/bin/env python3
"""
Robust ThetaTerminal Connection Manager

This module provides a reliable, well-tested interface for managing ThetaTerminal 
connections with proper process lifecycle management, error handling, and cleanup.
"""

import os
import sys
import time
import json
import signal
import psutil
import requests
import subprocess
from pathlib import Path
from typing import Optional, Dict, Any
from dotenv import load_dotenv


class ThetaConnectionManager:
    """Manages ThetaTerminal process lifecycle and API connections."""
    
    def __init__(self, project_root: Optional[str] = None):
        self.project_root = Path(project_root) if project_root else self._find_project_root()
        self.jar_path = self.project_root / "ThetaTerminal.jar"
        self.env_path = self.project_root / ".env"
        self.process: Optional[subprocess.Popen] = None
        self.api_base = "http://127.0.0.1:25510"
        
        # Load environment variables
        if self.env_path.exists():
            load_dotenv(self.env_path)
        
        # Get credentials
        self.username = os.getenv("THETADATA_USERNAME")
        self.password = os.getenv("THETADATA_PASSWORD")
        
        # Register cleanup handler
        signal.signal(signal.SIGTERM, self._cleanup_handler)
        signal.signal(signal.SIGINT, self._cleanup_handler)
    
    def _find_project_root(self) -> Path:
        """Find project root by looking for ThetaTerminal.jar."""
        current = Path(__file__).parent
        while current != current.parent:
            if (current / "ThetaTerminal.jar").exists():
                return current
            current = current.parent
        raise FileNotFoundError("Could not find project root with ThetaTerminal.jar")
    
    def _cleanup_handler(self, signum, frame):
        """Handle cleanup on signal."""
        self.cleanup()
        sys.exit(0)
    
    def _is_theta_process_running(self) -> bool:
        """Check if ThetaTerminal process is running."""
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'] and 'java' in proc.info['name'].lower():
                    cmdline = proc.info.get('cmdline', [])
                    if any('ThetaTerminal.jar' in str(arg) for arg in cmdline):
                        return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False
    
    def _check_api_connection(self, timeout: int = 5) -> bool:
        """Check if ThetaTerminal API is responsive."""
        try:
            response = requests.get(
                f"{self.api_base}/v2/system/mdds/status", 
                timeout=timeout
            )
            return response.text.strip() == "CONNECTED"
        except Exception:
            return False
    
    def _validate_setup(self) -> None:
        """Validate that all required components are available."""
        if not self.jar_path.exists():
            raise FileNotFoundError(f"ThetaTerminal.jar not found at {self.jar_path}")
        
        if not self.username or not self.password:
            raise ValueError(
                "THETADATA_USERNAME and THETADATA_PASSWORD must be set in .env file. "
                f"Please check {self.env_path}"
            )
    
    def _start_theta_process(self, quiet: bool = False) -> bool:
        """Start ThetaTerminal process."""
        if not quiet:
            print("🚀 Starting ThetaTerminal process...")
        
        try:
            # Start process with proper credential handling
            self.process = subprocess.Popen(
                ["java", "-jar", str(self.jar_path), self.username, self.password],
                cwd=self.project_root,
                stdout=subprocess.DEVNULL if quiet else None,
                stderr=subprocess.DEVNULL if quiet else None,
                preexec_fn=os.setsid  # Create new process group
            )
            
            if not quiet:
                print(f"✅ ThetaTerminal process started (PID: {self.process.pid})")
            
            return True
            
        except Exception as e:
            if not quiet:
                print(f"❌ Failed to start ThetaTerminal: {e}")
            return False
    
    def _wait_for_connection(self, max_wait: int = 45, quiet: bool = False) -> bool:
        """Wait for ThetaTerminal to establish API connection."""
        if not quiet:
            print("⏳ Waiting for ThetaTerminal to connect to servers...")
        
        start_time = time.time()
        check_interval = 2
        last_status_time = 0
        
        while time.time() - start_time < max_wait:
            # Check if process died
            if self.process and self.process.poll() is not None:
                if not quiet:
                    print("❌ ThetaTerminal process terminated unexpectedly")
                return False
            
            # Check API connection
            if self._check_api_connection(timeout=3):
                if not quiet:
                    print("✅ ThetaTerminal connected successfully!")
                return True
            
            # Status update every 10 seconds
            elapsed = time.time() - start_time
            if not quiet and elapsed - last_status_time >= 10:
                print(f"⏳ Still waiting... ({elapsed:.0f}s elapsed)")
                last_status_time = elapsed
            
            time.sleep(check_interval)
        
        if not quiet:
            print(f"❌ ThetaTerminal failed to connect within {max_wait} seconds")
        return False
    
    def connect(self, quiet: bool = False) -> bool:
        """
        Establish connection to ThetaTerminal.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        try:
            # Validate setup
            self._validate_setup()
            
            # Check if already connected
            if self._check_api_connection():
                if not quiet:
                    print("✅ ThetaTerminal already connected")
                return True
            
            # Check if process is running but not connected yet
            if self._is_theta_process_running():
                if not quiet:
                    print("🔄 ThetaTerminal process found, waiting for connection...")
                return self._wait_for_connection(max_wait=30, quiet=quiet)
            
            # Kill any stale processes
            self._kill_existing_processes(quiet=quiet)
            
            # Start new process
            if not self._start_theta_process(quiet=quiet):
                return False
            
            # Wait for connection
            return self._wait_for_connection(quiet=quiet)
            
        except Exception as e:
            if not quiet:
                print(f"❌ Connection failed: {e}")
            return False
    
    def _kill_existing_processes(self, quiet: bool = False) -> None:
        """Kill any existing ThetaTerminal processes."""
        killed_any = False
        
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'] and 'java' in proc.info['name'].lower():
                    cmdline = proc.info.get('cmdline', [])
                    if any('ThetaTerminal.jar' in str(arg) for arg in cmdline):
                        if not quiet:
                            print(f"🔄 Terminating existing ThetaTerminal (PID: {proc.info['pid']})")
                        proc.terminate()
                        killed_any = True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if killed_any:
            time.sleep(3)  # Give processes time to terminate
    
    def cleanup(self) -> None:
        """Clean up resources and terminate processes."""
        if self.process:
            try:
                # Terminate process group
                os.killpg(os.getpgid(self.process.pid), signal.SIGTERM)
                self.process.wait(timeout=5)
            except (ProcessLookupError, subprocess.TimeoutExpired):
                try:
                    # Force kill if necessary
                    os.killpg(os.getpgid(self.process.pid), signal.SIGKILL)
                except ProcessLookupError:
                    pass
            finally:
                self.process = None
    
    def is_connected(self) -> bool:
        """Check if ThetaTerminal is currently connected."""
        return self._check_api_connection()
    
    def get_status(self) -> Dict[str, Any]:
        """Get detailed connection status."""
        return {
            "process_running": self._is_theta_process_running(),
            "api_connected": self._check_api_connection(),
            "jar_exists": self.jar_path.exists(),
            "env_exists": self.env_path.exists(),
            "credentials_set": bool(self.username and self.password)
        }


# Global connection manager instance
_connection_manager: Optional[ThetaConnectionManager] = None


def get_connection_manager() -> ThetaConnectionManager:
    """Get the global connection manager instance."""
    global _connection_manager
    if _connection_manager is None:
        _connection_manager = ThetaConnectionManager()
    return _connection_manager


def ensure_theta_terminal_connected(quiet: bool = False) -> bool:
    """
    Ensure ThetaTerminal is connected and ready.
    
    This is the main function that should be used by other modules.
    """
    manager = get_connection_manager()
    return manager.connect(quiet=quiet)


def cleanup_theta_terminal() -> None:
    """Clean up ThetaTerminal resources."""
    global _connection_manager
    if _connection_manager:
        _connection_manager.cleanup()
        _connection_manager = None


# Ensure cleanup on module exit
import atexit
atexit.register(cleanup_theta_terminal)