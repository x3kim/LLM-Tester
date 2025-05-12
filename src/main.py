"""
Main entry point for the LLM testing application.

This module initializes and runs the application.
"""

import sys
import os
import logging
import asyncio
import traceback
from typing import Optional

# Add the src directory to sys.path
src_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if src_path not in sys.path:
    sys.path.insert(0, src_path)

# Configure logging before any other imports
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("llm_tester.log")
    ]
)

logger = logging.getLogger(__name__)

# Global variables
main_window = None  # Will hold reference to main window to prevent garbage collection

try:
    from PyQt6.QtWidgets import QApplication, QMessageBox
    from PyQt6.QtCore import QCoreApplication
    import qasync
    
    from src.ui.main_window import MainWindow  # Updated to use absolute import
except ImportError as e:
    logger.critical(f"Failed to import required modules: {e}")
    print(f"Error: Failed to import required modules: {e}")
    sys.exit(1)

async def async_main() -> int:
    """
    Asynchronous main function that sets up and runs the application.
    
    Returns:
        Exit code for the application.
    """
    try:
        # Set application information
        QCoreApplication.setApplicationName("HamsterN LLM Tester")
        QCoreApplication.setApplicationVersion("0.1.0")
        QCoreApplication.setOrganizationName("HamsterN")
        
        # Log application start
        logger.info("Application started successfully")
        
        # The application will run until the last window is closed
        # This is handled by the QEventLoop in the main function
        
        return 0
        
    except Exception as e:
        # Log the error and display an error message
        logger.critical(f"Unhandled exception in async_main: {e}", exc_info=True)
        
        # If QApplication is running, show a message box
        if QApplication.instance():
            QMessageBox.critical(
                None,
                "Critical Error",
                f"An unhandled exception occurred:\n\n{e}\n\nSee logs for details."
            )
        
        return 1

def main() -> int:
    """
    Main entry point for the application.
    
    Returns:
        Exit code for the application.
    """
    try:
        # Create QApplication instance
        app = QApplication(sys.argv)
        
        # Create and configure the asyncio event loop using qasync
        # Use with statement for proper cleanup
        with qasync.QEventLoop(app) as loop:
            # Set as the default event loop
            asyncio.set_event_loop(loop)
            
            # Run the initial setup in async_main and get the exit code
            exit_code = loop.run_until_complete(async_main())
            
            # If setup was successful, create and show the main window
            if exit_code == 0:
                # Create the main window
                global main_window
                main_window = MainWindow()
                main_window.show()
                
                # This makes app.exec() compatible with asyncio
                # The loop will run until app.quit() is called (when all windows close)
                loop.run_forever()
        
        # The with statement takes care of loop cleanup
        return exit_code
        
    except Exception as e:
        # Handle any exceptions that occur during initialization
        logger.critical(f"Failed to initialize application: {e}", exc_info=True)
        
        # Print error to console if logging setup failed
        print(f"Critical Error: Failed to initialize application: {e}")
        traceback.print_exc()
        
        return 1

if __name__ == "__main__":
    sys.exit(main())

