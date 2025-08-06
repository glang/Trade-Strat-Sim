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
import httpx
import subprocess
import socket
from pathlib import Path
from typing import Optional, Dict, Any
from dotenv import load_dotenv


class ThetaConnectionManager:
    """Manages ThetaTerminal process lifecycle and API connections."""
    
    def __init__(self, project_root: Optional[str] = None):
        self.project_root = Path(project_root) if project_root else self._find_project_root()
        self.jar_path = self.project_root / "ThetaTerminalv3.jar"
        self.env_path = self.project_root / ".env"
        self.process: Optional[subprocess.Popen] = None
        # ThetaTerminalv3 uses port 25503 with v3 API structure
        self.api_base = "http://localhost:25503/v3"
        self.port = 25503
        
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
        """Find project root by looking for ThetaTerminalv3.jar."""
        current = Path(__file__).parent
        while current != current.parent:
            if (current / "ThetaTerminalv3.jar").exists():
                return current
            current = current.parent
        raise FileNotFoundError("Could not find project root with ThetaTerminalv3.jar")
    
    def _cleanup_handler(self, signum, frame):
        """Handle cleanup on signal."""
        self.cleanup()
        sys.exit(0)
    
    def _is_theta_process_running(self) -> bool:
        """Check if ThetaTerminal process is running."""
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'] and 'java' in proc.info['name'].lower():
                    cmdline = proc.info.get('cmdline') or []
                    if any('ThetaTerminal' in str(arg) for arg in cmdline):
                        return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        return False
    
    def _is_port_in_use(self, port: int) -> bool:
        """Check if a port is currently in use."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            result = sock.connect_ex(('localhost', port))
            return result == 0
    
    def _wait_for_port_free(self, port: int, max_wait: int = 10, quiet: bool = False) -> bool:
        """Wait for a port to become available."""
        start_time = time.time()
        while time.time() - start_time < max_wait:
            if not self._is_port_in_use(port):
                return True
            if not quiet:
                elapsed = time.time() - start_time
                if elapsed % 2 == 0:  # Print every 2 seconds
                    print(f"⏳ Waiting for port {port} to become available... ({elapsed:.0f}s)")
            time.sleep(0.5)
        return False
    
    def _force_kill_port_users(self, port: int, quiet: bool = False) -> bool:
        """Force kill any processes using the specified port."""
        try:
            import subprocess
            
            # Find processes using the port
            result = subprocess.run(['ss', '-tulpn'], capture_output=True, text=True)
            if result.returncode != 0:
                return False
            
            processes_to_kill = []
            for line in result.stdout.split('\n'):
                if f':{port}' in line and 'LISTEN' in line:
                    # Extract PID from ss output (format: users:(("java",pid=12345,fd=58)))
                    if 'users:' in line:
                        user_part = line.split('users:')[1]
                        if 'pid=' in user_part:
                            try:
                                pid_str = user_part.split('pid=')[1].split(',')[0]
                                pid = int(pid_str)
                                processes_to_kill.append(pid)
                            except (ValueError, IndexError):
                                continue
            
            if not processes_to_kill:
                return True
            
            if not quiet:
                print(f"💀 Force killing {len(processes_to_kill)} processes using port {port}")
            
            # Kill the processes
            for pid in processes_to_kill:
                try:
                    os.kill(pid, signal.SIGKILL)
                    if not quiet:
                        print(f"   Killed PID {pid}")
                except (ProcessLookupError, OSError):
                    continue
            
            # Wait a moment for cleanup
            time.sleep(2)
            return not self._is_port_in_use(port)
            
        except Exception as e:
            if not quiet:
                print(f"   Error during force kill: {e}")
            return False
    
    def _check_api_connection(self, timeout: int = 5) -> bool:
        """Check if ThetaTerminal API is responsive."""
        try:
            # Test with v3 stock EOD endpoint - simpler and more reliable
            with httpx.Client(timeout=timeout) as client:
                response = client.get(
                    f"{self.api_base}/stock/history/eod",
                    params={
                        "symbol": "GOOG",
                        "start_date": "2024-01-03",
                        "end_date": "2024-01-03"
                    }
                )
                # Check if we got a valid CSV response
                return (response.status_code == 200 and 
                       len(response.text.strip()) > 0 and 
                       'created' in response.text)  # CSV header check
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
    
    def _create_credentials_file(self) -> Path:
        """Create credentials file for ThetaTerminalv3."""
        creds_file = self.project_root / "creds.txt"
        with open(creds_file, 'w') as f:
            f.write(f"{self.username}\n{self.password}\n")
        return creds_file
    
    def _start_theta_process(self, quiet: bool = False) -> bool:
        """Start ThetaTerminal process in background using documented command."""
        if not quiet:
            print("🚀 Starting ThetaTerminal process in background...")
        
        try:
            # Check if already running first
            if self._is_port_in_use(self.port) and self._check_api_connection():
                if not quiet:
                    print("✅ ThetaTerminal already running and responsive")
                return True
            
            # Create credentials file for ThetaTerminalv3
            creds_file = self._create_credentials_file()
            
            # Use the documented background command from CLAUDE.md
            # nohup java -jar ThetaTerminalv3.jar --creds-file creds.txt > theta_terminal.log 2>&1 &
            log_file = self.project_root / "theta_terminal.log"
            
            # Execute the background command via shell to properly handle nohup
            cmd_str = f"nohup java -jar {self.jar_path} --creds-file {creds_file} > {log_file} 2>&1 &"
            
            if not quiet:
                print(f"   Command: {cmd_str}")
            
            # Start process in background using shell execution
            self.process = subprocess.Popen(
                cmd_str,
                shell=True,
                cwd=self.project_root,
                start_new_session=True  # Detach from parent session
            )
            
            # Give process a moment to start
            time.sleep(3)
            
            # Don't check process status since it's running in background/detached
            # Instead, check if port becomes available
            if not quiet:
                print(f"✅ ThetaTerminal background process started, logs at: {log_file}")
            
            return True
            
        except Exception as e:
            if not quiet:
                print(f"❌ Failed to start ThetaTerminal: {e}")
            return False
    
    def _wait_for_connection(self, max_wait: int = 60, quiet: bool = False) -> bool:
        """Wait for ThetaTerminal to establish API connection."""
        if not quiet:
            print("⏳ Waiting for ThetaTerminal to connect to servers...")
        
        start_time = time.time()
        check_interval = 2
        last_status_time = 0
        connection_attempts = 0
        
        while time.time() - start_time < max_wait:
            # For background processes started with nohup, don't check process status
            # since we lose track of the actual process. Instead, rely on port and API checks.
            
            # Check API connection with progressive timeout
            connection_attempts += 1
            api_timeout = min(3 + (connection_attempts // 5), 10)  # Progressive timeout 3-10s
            
            if self._check_api_connection(timeout=api_timeout):
                if not quiet:
                    print("✅ ThetaTerminal connected successfully!")
                return True
            
            # Status update every 10 seconds with more detail
            elapsed = time.time() - start_time
            if not quiet and elapsed - last_status_time >= 10:
                port_status = "in use" if self._is_port_in_use(self.port) else "free"
                process_status = "running" if self._is_theta_process_running() else "not found"
                print(f"⏳ Still waiting... ({elapsed:.0f}s elapsed, port {self.port}: {port_status}, process: {process_status})")
                last_status_time = elapsed
            
            time.sleep(check_interval)
        
        if not quiet:
            print(f"❌ ThetaTerminal failed to connect within {max_wait} seconds")
            # Diagnostic information
            print(f"   Port {self.port} status: {'in use' if self._is_port_in_use(self.port) else 'free'}")
            print(f"   Process running: {self._is_theta_process_running()}")
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
                
                # Give existing process time to connect (up to 60 seconds)
                # We don't kill existing processes anymore - let them run
                if self._wait_for_connection(max_wait=60, quiet=quiet):
                    if not quiet:
                        print("✅ Existing ThetaTerminal process connected successfully!")
                    return True
                else:
                    if not quiet:
                        print("⚠️  Existing process not responding, but leaving it running")
                        print("    You may want to manually check ThetaTerminal status")
                    return False
            
            # Start new process only if none is running
            if not self._start_theta_process(quiet=quiet):
                return False
            
            # Wait for connection
            return self._wait_for_connection(quiet=quiet)
            
        except Exception as e:
            if not quiet:
                print(f"❌ Connection failed: {e}")
            return False
    
    def _kill_existing_processes(self, quiet: bool = False) -> None:
        """Kill any existing ThetaTerminal processes and wait for port to be free."""
        processes_to_kill = []
        
        # First, identify all ThetaTerminal processes
        for proc in psutil.process_iter(['pid', 'name', 'cmdline']):
            try:
                if proc.info['name'] and 'java' in proc.info['name'].lower():
                    cmdline = proc.info.get('cmdline') or []
                    if any('ThetaTerminal' in str(arg) for arg in cmdline):
                        processes_to_kill.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if not processes_to_kill:
            if not quiet:
                print("🔍 No existing ThetaTerminal processes found")
            return
        
        if not quiet:
            print(f"🧹 Found {len(processes_to_kill)} ThetaTerminal processes to terminate")
        
        # Attempt graceful termination first
        for proc in processes_to_kill:
            try:
                if not quiet:
                    print(f"🔄 Gracefully terminating ThetaTerminal (PID: {proc.pid})")
                proc.terminate()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        # Wait for graceful termination
        if not quiet:
            print("⏳ Waiting for graceful termination...")
        time.sleep(5)  # Increased wait time for graceful shutdown
        
        # Force kill any remaining processes
        remaining_processes = []
        for proc in processes_to_kill:
            try:
                if proc.is_running():
                    remaining_processes.append(proc)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
        
        if remaining_processes:
            if not quiet:
                print(f"💀 Force killing {len(remaining_processes)} stubborn processes")
            for proc in remaining_processes:
                try:
                    proc.kill()
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    continue
        
        # Wait for port to become available
        if not quiet:
            print(f"🔌 Waiting for port {self.port} to be released...")
        if not self._wait_for_port_free(self.port, max_wait=10, quiet=quiet):
            if not quiet:
                print(f"⚠️  Port {self.port} still in use, attempting force cleanup...")
            # Force kill any remaining processes using the port
            if self._force_kill_port_users(self.port, quiet=quiet):
                if not quiet:
                    print(f"✅ Port {self.port} forcefully freed")
            else:
                if not quiet:
                    print(f"❌ Could not free port {self.port}")
        else:
            if not quiet:
                print(f"✅ Port {self.port} is now available")
    
    def cleanup(self) -> None:
        """Clean up resources without terminating ThetaTerminal processes."""
        # Note: We intentionally do NOT kill ThetaTerminal processes
        # ThetaTerminal should remain running in the background for other scripts
        # Only clean up our local process reference
        if self.process:
            self.process = None
        
        # Note: We do not delete creds.txt to allow persistent credentials
    
    def is_connected(self) -> bool:
        """Check if ThetaTerminal is currently connected."""
        return self._check_api_connection()
    
    def get_status(self) -> Dict[str, Any]:
        """Get detailed connection status."""
        creds_file = self.project_root / "creds.txt"
        return {
            "process_running": self._is_theta_process_running(),
            "api_connected": self._check_api_connection(),
            "port_in_use": self._is_port_in_use(self.port),
            "jar_exists": self.jar_path.exists(),
            "env_exists": self.env_path.exists(),
            "credentials_set": bool(self.username and self.password),
            "creds_file_exists": creds_file.exists(),
            "port": self.port,
            "api_base": self.api_base
        }
    
    def force_restart(self, quiet: bool = False) -> bool:
        """Force a connection attempt without killing existing processes."""
        if not quiet:
            print("🔄 Attempting fresh ThetaTerminal connection...")
        
        # Clean up our own process reference only
        if self.process:
            self.process = None
        
        if not quiet:
            print("⚠️  Note: This no longer kills existing ThetaTerminal processes")
            print("    Use 'lsof -ti:25503 | xargs kill' manually if needed")
        
        # Attempt to connect
        return self.connect(quiet=quiet)
    
    def diagnose_issues(self, quiet: bool = False) -> Dict[str, str]:
        """Diagnose common connection issues and provide recommendations."""
        issues = {}
        status = self.get_status()
        
        if not status["jar_exists"]:
            issues["jar_missing"] = f"ThetaTerminalv3.jar not found at {self.jar_path}"
        
        if not status["credentials_set"]:
            issues["credentials_missing"] = "THETADATA_USERNAME or THETADATA_PASSWORD not set in .env"
        
        if status["port_in_use"] and not status["api_connected"]:
            issues["port_conflict"] = f"Port {self.port} is in use but API is not responding"
        
        if status["process_running"] and not status["api_connected"]:
            issues["unresponsive_process"] = "ThetaTerminal process is running but not responding to API calls"
        
        if not status["process_running"] and status["port_in_use"]:
            issues["zombie_port"] = f"Port {self.port} is in use but no ThetaTerminal process found"
        
        if not issues:
            issues["status"] = "No issues detected"
        
        if not quiet:
            print("🔍 ThetaTerminal Diagnostics:")
            for issue_type, description in issues.items():
                print(f"  - {issue_type}: {description}")
        
        return issues


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


def force_restart_theta_terminal(quiet: bool = False) -> bool:
    """
    Force a complete restart of ThetaTerminal.
    
    Use this when experiencing persistent connection issues.
    """
    manager = get_connection_manager()
    return manager.force_restart(quiet=quiet)


def diagnose_theta_terminal(quiet: bool = False) -> Dict[str, str]:
    """
    Diagnose ThetaTerminal connection issues.
    
    Returns a dictionary of detected issues and recommendations.
    """
    manager = get_connection_manager()
    return manager.diagnose_issues(quiet=quiet)


def cleanup_theta_terminal() -> None:
    """Clean up ThetaTerminal resources without killing processes."""
    global _connection_manager
    if _connection_manager:
        _connection_manager.cleanup()
        _connection_manager = None


# Register cleanup on module exit (but won't kill ThetaTerminal)
import atexit
atexit.register(cleanup_theta_terminal)