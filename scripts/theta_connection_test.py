#!/usr/bin/env python3
"""
ThetaTerminal Connection Test and Management Utility

This script provides a command-line interface for testing and managing 
ThetaTerminal connections with diagnostic capabilities.
"""

import sys
import os
import argparse
import json
from pathlib import Path

# Add project root to path
script_dir = Path(__file__).parent
project_root = script_dir.parent
sys.path.insert(0, str(project_root))

from src.backtesting_engine.theta_connection_manager import (
    ensure_theta_terminal_connected,
    force_restart_theta_terminal,
    diagnose_theta_terminal,
    get_connection_manager,
    cleanup_theta_terminal
)


def test_connection():
    """Test ThetaTerminal connection."""
    print("🔌 Testing ThetaTerminal Connection")
    print("=" * 50)
    
    success = ensure_theta_terminal_connected(quiet=False)
    
    if success:
        print("\n✅ ThetaTerminal connection test PASSED")
        
        # Test a simple API call
        print("\n🧪 Testing API functionality...")
        manager = get_connection_manager()
        if manager._check_api_connection():
            print("✅ API test PASSED")
        else:
            print("❌ API test FAILED")
            
    else:
        print("\n❌ ThetaTerminal connection test FAILED")
        print("   Run with --diagnose for more information")
    
    return success


def diagnose_connection():
    """Diagnose connection issues."""
    print("🔍 ThetaTerminal Connection Diagnostics")
    print("=" * 50)
    
    manager = get_connection_manager()
    status = manager.get_status()
    
    print("\n📊 System Status:")
    print(f"  JAR file exists: {'✅' if status['jar_exists'] else '❌'}")
    print(f"  Credentials set: {'✅' if status['credentials_set'] else '❌'}")
    print(f"  Creds file exists: {'✅' if status['creds_file_exists'] else '❌'}")
    print(f"  Port {status['port']} in use: {'✅' if status['port_in_use'] else '❌'}")
    print(f"  Process running: {'✅' if status['process_running'] else '❌'}")
    print(f"  API connected: {'✅' if status['api_connected'] else '❌'}")
    
    print(f"\n🌐 API Base: {status['api_base']}")
    
    # Diagnose issues
    issues = diagnose_theta_terminal(quiet=False)
    
    if "status" in issues and issues["status"] == "No issues detected":
        print("\n🎉 No issues detected!")
    else:
        print("\n💡 Recommendations:")
        for issue_type, description in issues.items():
            if issue_type != "status":
                print(f"  • Fix {issue_type}: {description}")


def force_restart():
    """Force restart ThetaTerminal."""
    print("🔄 Force Restarting ThetaTerminal")
    print("=" * 50)
    
    success = force_restart_theta_terminal(quiet=False)
    
    if success:
        print("\n✅ ThetaTerminal restart successful")
    else:
        print("\n❌ ThetaTerminal restart failed")
    
    return success


def cleanup():
    """Clean up ThetaTerminal resources."""
    print("🧹 Cleaning up ThetaTerminal")
    print("=" * 50)
    
    cleanup_theta_terminal()
    print("✅ Cleanup completed")


def show_status():
    """Show detailed status information."""
    print("📊 ThetaTerminal Status")
    print("=" * 50)
    
    manager = get_connection_manager()
    status = manager.get_status()
    
    print(json.dumps(status, indent=2))


def main():
    parser = argparse.ArgumentParser(
        description="ThetaTerminal Connection Test and Management Utility",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/theta_connection_test.py --test        # Test connection
  python3 scripts/theta_connection_test.py --diagnose   # Diagnose issues  
  python3 scripts/theta_connection_test.py --restart    # Force restart
  python3 scripts/theta_connection_test.py --cleanup    # Clean up resources
  python3 scripts/theta_connection_test.py --status     # Show detailed status
        """
    )
    
    parser.add_argument('--test', action='store_true', 
                       help='Test ThetaTerminal connection')
    parser.add_argument('--diagnose', action='store_true',
                       help='Diagnose connection issues')
    parser.add_argument('--restart', action='store_true',
                       help='Force restart ThetaTerminal')
    parser.add_argument('--cleanup', action='store_true',
                       help='Clean up ThetaTerminal resources')
    parser.add_argument('--status', action='store_true',
                       help='Show detailed status information')
    
    args = parser.parse_args()
    
    # If no arguments provided, default to test
    if not any([args.test, args.diagnose, args.restart, args.cleanup, args.status]):
        args.test = True
    
    success = True
    
    try:
        if args.status:
            show_status()
        elif args.diagnose:
            diagnose_connection()
        elif args.restart:
            success = force_restart()
        elif args.cleanup:
            cleanup()
        elif args.test:
            success = test_connection()
            
    except KeyboardInterrupt:
        print("\n\n⚠️ Interrupted by user")
        cleanup()
        sys.exit(1)
    except Exception as e:
        print(f"\n❌ Unexpected error: {e}")
        success = False
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()