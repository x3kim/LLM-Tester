"""
Main application window implementation.

This module provides the main window for the LLM testing application,
implementing the primary UI framework and layout.
"""

import sys
import logging
import asyncio
import math
from typing import Optional, List, Dict, Any
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QDockWidget, QToolBar, 
    QStatusBar, QVBoxLayout, QHBoxLayout, QTabWidget, QLabel, QMessageBox,
    QMenu, QFileDialog, QPushButton, QLineEdit, QFormLayout,
    QComboBox, QGroupBox, QSplitter, QProgressBar, QTextEdit, QListWidget,
    QListWidgetItem, QCheckBox, QSpinBox, QDoubleSpinBox
)
from PyQt6.QtCore import Qt, QSize, pyqtSignal, pyqtSlot, QSettings, QThread, QTimer
from PyQt6.QtGui import QIcon, QAction, QFont
import qasync
from qasync import asyncSlot

from ..api.ollama_client import OllamaClient, ConnectionError, ModelInfo
from ..core.test_manager import TestSuite, TestCase

logger = logging.getLogger(__name__)

class ConnectionPanel(QWidget):
    """Panel for configuring and managing Ollama API connections."""
    
    # Signal emitted when connection state changes
    connection_changed = pyqtSignal(bool, str)  # connected, message
    
    def __init__(self, client: OllamaClient, parent=None):
        """
        Initialize the connection panel.
        
        Args:
            client: The Ollama client to use.
            parent: The parent widget.
        """
        super().__init__(parent)
        self.client = client
        self.is_connected = False
        self._init_ui()
        
    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        
        # Connection group
        conn_group = QGroupBox("Ollama Connection")
        conn_layout = QFormLayout()
        
        # Host input
        self.host_input = QLineEdit("localhost")
        conn_layout.addRow("Host:", self.host_input)
        
        # Port input
        self.port_input = QSpinBox()
        self.port_input.setRange(1, 65535)
        self.port_input.setValue(11434)  # Default Ollama port
        conn_layout.addRow("Port:", self.port_input)
        
        # Connect button
        self.connect_btn = QPushButton("Connect")
        self.connect_btn.clicked.connect(self._connect_to_ollama)
        conn_layout.addRow("", self.connect_btn)
        
        # Connection status
        self.status_label = QLabel("Not connected")
        self.status_label.setStyleSheet("color: red;")
        conn_layout.addRow("Status:", self.status_label)
        
        conn_group.setLayout(conn_layout)
        layout.addWidget(conn_group)
        
        # Available models group (shown after connection)
        self.models_group = QGroupBox("Available Models")
        models_layout = QVBoxLayout()
        
        self.models_list = QListWidget()
        # Enable multi-selection mode
        self.models_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        
        self.refresh_models_btn = QPushButton("Refresh Models")
        self.refresh_models_btn.clicked.connect(self._refresh_models)
        self.refresh_models_btn.setEnabled(False)
        
        models_layout.addWidget(self.models_list)
        models_layout.addWidget(self.refresh_models_btn)
        
        self.models_group.setLayout(models_layout)
        self.models_group.setVisible(False)
        
        layout.addWidget(self.models_group)
        layout.addStretch()
        
    @asyncSlot()
    async def _connect_to_ollama(self):
        """Connect to the Ollama API."""
        host = self.host_input.text()
        port = self.port_input.value()
        
        # Disable controls during connection attempt
        self.host_input.setEnabled(False)
        self.port_input.setEnabled(False)
        self.connect_btn.setEnabled(False)
        self.connect_btn.setText("Connecting...")
        self.status_label.setText("Connecting...")
        self.status_label.setStyleSheet("color: orange;")
        
        # Update UI to show working state
        QApplication.processEvents()
        
        try:
            # Attempt connection
            connected = await self.client.connect(host, port)
            
            if connected:
                self.is_connected = True
                self.status_label.setText("Connected")
                self.status_label.setStyleSheet("color: green;")
                self.connect_btn.setText("Disconnect")
                
                # Show models group and enable refresh button
                self.models_group.setVisible(True)
                self.refresh_models_btn.setEnabled(True)
                
                # Load models
                await self._refresh_models()
                
                # Emit connection status
                self.connection_changed.emit(True, f"Connected to Ollama at {host}:{port}")
            else:
                self.status_label.setText("Connection failed")
                self.status_label.setStyleSheet("color: red;")
                
                # Emit connection status
                self.connection_changed.emit(False, "Failed to connect to Ollama")
        
        except ConnectionError as e:
            self.is_connected = False
            error_msg = str(e)
            self.status_label.setText("Connection error")
            self.status_label.setStyleSheet("color: red;")
            
            # Show error message
            QMessageBox.critical(self, "Connection Error", 
                               f"Failed to connect to Ollama: {error_msg}")
            
            # Emit connection status
            self.connection_changed.emit(False, f"Connection error: {error_msg}")
        
        finally:
            # Re-enable controls
            self.host_input.setEnabled(not self.is_connected)
            self.port_input.setEnabled(not self.is_connected)
            self.connect_btn.setEnabled(True)
            self.connect_btn.setText("Disconnect" if self.is_connected else "Connect")
    
    @asyncSlot()
    async def _refresh_models(self):
        """Refresh the list of available models."""
        if not self.is_connected:
            return
        
        try:
            # Clear current list
            self.models_list.clear()
            
            # Get models from API
            models = await self.client.list_models()
            
            # Add models to list
            for model in models:
                item = QListWidgetItem(model.name)
                item.setData(Qt.ItemDataRole.UserRole, model)
                self.models_list.addItem(item)
            
        except ConnectionError as e:
            QMessageBox.warning(self, "Error", f"Failed to fetch models: {e}")
    
    def get_selected_models(self) -> List[str]:
        """
        Get the list of selected models.
        
        Returns:
            List of selected model names.
        """
        selected_items = self.models_list.selectedItems()
        return [item.text() for item in selected_items]


class TestExecutionPanel(QWidget):
    """Panel for configuring and executing tests."""
    
    # Signals
    test_started = pyqtSignal(str, list)  # test_suite_name, models
    test_progress = pyqtSignal(int, int)  # current, total
    test_completed = pyqtSignal(dict)  # results
    
    def __init__(self, client=None, parent=None):
        """
        Initialize the test execution panel.
        
        Args:
            client: The Ollama client to use for tests.
            parent: The parent widget.
        """
        super().__init__(parent)
        self.client = client
        self.selected_models = []
        self._init_ui()
    
    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        
        # Test configuration group
        test_group = QGroupBox("Test Configuration")
        test_layout = QFormLayout()
        
        # Test suite selection
        self.test_suite_combo = QComboBox()
        self.test_suite_combo.addItem("Basic Evaluation", "basic")
        self.test_suite_combo.addItem("Math Capabilities", "math")
        self.test_suite_combo.addItem("Code Generation", "code")
        self.test_suite_combo.addItem("General Knowledge", "knowledge")
        test_layout.addRow("Test Suite:", self.test_suite_combo)
        
        # Parallel execution option
        self.parallel_check = QCheckBox("Run tests in parallel")
        self.parallel_check.setChecked(True)
        test_layout.addRow("Execution:", self.parallel_check)
        
        # Max concurrent tests
        self.concurrency_spin = QSpinBox()
        self.concurrency_spin.setRange(1, 10)
        self.concurrency_spin.setValue(3)
        test_layout.addRow("Max concurrent tests:", self.concurrency_spin)
        
        # Run button
        self.run_btn = QPushButton("Run Tests")
        self.run_btn.clicked.connect(self._start_tests)
        self.run_btn.setEnabled(False)  # Disabled until models are selected
        test_layout.addRow("", self.run_btn)
        
        test_group.setLayout(test_layout)
        layout.addWidget(test_group)
        
        # Progress group
        progress_group = QGroupBox("Test Progress")
        progress_layout = QVBoxLayout()
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        
        self.progress_label = QLabel("Ready")
        
        progress_layout.addWidget(self.progress_bar)
        progress_layout.addWidget(self.progress_label)
        
        progress_group.setLayout(progress_layout)
        layout.addWidget(progress_group)
        
        layout.addStretch()
    
    @asyncSlot()
    async def _start_tests(self):
        """Start the test execution."""
        if not self.client:
            QMessageBox.warning(self, "No Client", 
                               "OllamaClient is not initialized.")
            return

        test_suite_id = self.test_suite_combo.currentData()
        
        # Update UI to show test is starting
        self.run_btn.setEnabled(False)
        self.progress_bar.setValue(0)
        self.progress_label.setText("Test starting...")
        
        # Emit that test has started
        self.test_started.emit(test_suite_id, self.selected_models)
        
        # Validate we have models selected
        if not self.selected_models:
            QMessageBox.warning(self, "No Models Selected", 
                               "Please select at least one model to test.")
            self.run_btn.setEnabled(True)
            return
        
        try:
            # Debug logging for test execution
            logger.debug(f"Starting tests with models: {self.selected_models}")
            logger.debug(f"Test suite ID: {test_suite_id}")
            logger.debug(f"Client connection status: {self.client.is_connected}")
            
            # More detailed logging for user feedback
            logger.info("Starting test execution...")
            logger.info(f"Selected models: {self.selected_models}")
            logger.info(f"Test suite: {test_suite_id}")
            
            # Create the test suite (synchronously, since it's just data)
            test_suite = self._create_test_suite(test_suite_id)
            
            # Use the client instance passed in the constructor
            client = self.client
            
            # Create a test manager for executing tests
            from ..core.test_manager import TestManager
            test_manager = TestManager(client)
            
            # Get test settings
            parallel = self.parallel_check.isChecked()
            max_concurrency = self.concurrency_spin.value()
            
            # Update logging for test execution
            logger.info(f"Starting test suite: {test_suite_id}")
            logger.info(f"Selected models: {self.selected_models}")
            logger.info("Test configuration:")
            logger.info(f"- Parallel execution: {parallel}")
            logger.info(f"- Max concurrency: {max_concurrency}")
            logger.info(f"- Total test cases: {len(test_suite.get_test_cases())}")
            
            # Update UI to show test is running
            self.progress_label.setText("Running tests...")
            
            # Calculate total tests to run
            total_tests = len(test_suite.get_test_cases()) * len(self.selected_models)
            completed_tests = 0
            
            # Execute tests
            logger.info("\nBeginning test execution...")
            results = {}
            
            if parallel:
                # Run tests in parallel
                try:
                    results = await test_manager.run_parallel_tests(
                        models=self.selected_models,
                        test_suite=test_suite,
                        max_concurrency=max_concurrency
                    )
                    completed_tests = total_tests
                    self.test_progress.emit(completed_tests, total_tests)
                except Exception as e:
                    logger.error(f"Error running parallel tests: {e}")
                    QMessageBox.critical(self, "Test Error", 
                                       f"Error running tests in parallel: {str(e)}")
            else:
                # Run tests sequentially
                results = {}
                for model in self.selected_models:
                    logger.info(f"\nTesting model: {model}")
                    results[model] = []
                    try:
                        model_results = await test_manager.run_test_suite(model, test_suite)
                        results[model] = model_results
                        
                        # Update progress
                        completed_tests += len(model_results)
                        self.test_progress.emit(completed_tests, total_tests)
                    except Exception as e:
                        logger.error(f"Error testing model {model}: {e}")
                        QMessageBox.warning(self, "Model Test Error", 
                                           f"Error testing model {model}: {str(e)}\n\nContinuing with other models.")
            
            # Update UI to show test is complete
            self.progress_bar.setValue(100)
            self.progress_label.setText("Testing completed")
            
            # Emit that test has completed
            self.test_completed.emit(results)
            
        except Exception as e:
            logger.error(f"Test execution error: {e}", exc_info=True)
            QMessageBox.critical(self, "Test Execution Error", 
                               f"An error occurred during test execution: {str(e)}")
        finally:
            # Re-enable the run button
            self.run_btn.setEnabled(True)
    
    def set_selected_models(self, models: List[str]):
        """
        Set the selected models.
        
        Args:
            models: List of selected model names.
        """
        self.selected_models = models
        self.run_btn.setEnabled(bool(models))
        logger.debug(f"Test panel updated with models: {models}")
    
    def update_progress(self, current: int, total: int):
        """
        Update the progress indicator.
        
        Args:
            current: Current progress value.
            total: Total progress value.
        """
        percentage = int((current / total) * 100) if total > 0 else 0
        self.progress_bar.setValue(percentage)
        self.progress_label.setText(f"Processing {current}/{total} tests...")
        
        if current >= total:
            self.progress_label.setText("Testing completed")
            self.run_btn.setEnabled(True)
    
    def _create_test_suite(self, suite_id: str) -> TestSuite:
        """
        Create a test suite based on the selected type.
        
        Args:
            suite_id: The ID of the test suite to create.
            
        Returns:
            TestSuite: The created test suite.
        """
        if suite_id == "basic":
            return self._create_basic_test_suite()
        elif suite_id == "math":
            return self._create_math_test_suite()
        elif suite_id == "code":
            return self._create_code_test_suite()
        elif suite_id == "knowledge":
            return self._create_knowledge_test_suite()
        else:
            # Default to basic test suite
            return self._create_basic_test_suite()
    
    def _create_basic_test_suite(self) -> TestSuite:
        """Create a basic evaluation test suite."""
        suite = TestSuite("Basic Evaluation", "Basic tests for LLM evaluation")
        
        # Add some simple test cases
        suite.add_test_case(TestCase(
            name="Simple Greeting",
            prompt="Say hello to the user.",
            category="basic",
            validation_function=lambda x: "hello" in x.lower()
        ))
        
        suite.add_test_case(TestCase(
            name="Simple Prompt Response",
            prompt="What is the capital of France?",
            category="basic",
            expected_result="Paris"
        ))
        
        suite.add_test_case(TestCase(
            name="Simple Instruction",
            prompt="Count from 1 to 5.",
            category="basic",
            validation_function=lambda x: all(str(i) in x for i in range(1, 6))
        ))
        
        return suite
    
    def _create_math_test_suite(self) -> TestSuite:
        """Create a math capabilities test suite."""
        suite = TestSuite("Math Capabilities", "Tests for mathematical capabilities")
        
        # Add math test cases
        suite.add_test_case(TestCase(
            name="Simple Addition",
            prompt="What is 1 + 2?",
            category="math",
            expected_result="3"
        ))
        
        suite.add_test_case(TestCase(
            name="Simple Subtraction",
            prompt="What is 10 - 5?",
            category="math",
            expected_result="5"
        ))
        
        suite.add_test_case(TestCase(
            name="Simple Multiplication",
            prompt="What is 7 * 6?",
            category="math",
            expected_result="42"
        ))
        
        suite.add_test_case(TestCase(
            name="Square Root",
            prompt="What is the square root of 64?",
            category="math",
            validation_function=lambda x: "8" in x
        ))
        
        return suite
    
    def _create_code_test_suite(self) -> TestSuite:
        """Create a code generation test suite."""
        suite = TestSuite("Code Generation", "Tests for code generation capabilities")
        
        # Add code generation test cases
        suite.add_test_case(TestCase(
            name="Python Hello World",
            prompt="Write a Python program that prints 'Hello, World!'",
            category="code",
            validation_function=lambda x: "print" in x and "Hello, World" in x
        ))
        
        suite.add_test_case(TestCase(
            name="JavaScript Function",
            prompt="Write a JavaScript function that calculates the factorial of a number.",
            category="code",
            validation_function=lambda x: "function" in x and "factorial" in x
        ))
        
        suite.add_test_case(TestCase(
            name="HTML Structure",
            prompt="Write the basic HTML structure for a webpage with a heading and a paragraph.",
            category="code",
            validation_function=lambda x: "<html" in x.lower() and "<body" in x.lower() and "<h" in x.lower()
        ))
        
        suite.add_test_case(TestCase(
            name="SQL Query",
            prompt="Write a SQL query to select all users from a 'users' table where the age is greater than 18.",
            category="code",
            validation_function=lambda x: "select" in x.lower() and "from" in x.lower() and "users" in x.lower()
        ))
        
        return suite
    
    def _create_knowledge_test_suite(self) -> TestSuite:
        """Create a general knowledge test suite."""
        suite = TestSuite("General Knowledge", "Tests for general knowledge capabilities")
        
        # Add general knowledge test cases
        suite.add_test_case(TestCase(
            name="Historical Fact",
            prompt="Who was the first person to walk on the moon?",
            category="knowledge",
            validation_function=lambda x: "armstrong" in x.lower() or "neil" in x.lower()
        ))
        
        suite.add_test_case(TestCase(
            name="Scientific Fact",
            prompt="What is the chemical symbol for water?",
            category="knowledge",
            expected_result="H2O"
        ))
        
        suite.add_test_case(TestCase(
            name="Geography",
            prompt="What is the largest ocean on Earth?",
            category="knowledge",
            validation_function=lambda x: "pacific" in x.lower()
        ))
        
        suite.add_test_case(TestCase(
            name="Literature",
            prompt="Who wrote 'Pride and Prejudice'?",
            category="knowledge",
            validation_function=lambda x: "austen" in x.lower() or "jane" in x.lower()
        ))
        
        return suite


class DebugConsolePanel(QWidget):
    """Panel for displaying debug output and streaming responses."""
    
    def __init__(self, parent=None):
        """
        Initialize the debug console panel.
        
        Args:
            parent: The parent widget.
        """
        super().__init__(parent)
        self._init_ui()
    
    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        
        # Debug output text area
        self.console = QTextEdit()
        self.console.setReadOnly(True)
        self.console.setFont(QFont("Courier New", 10))
        self.console.setStyleSheet("background-color: #1e1e1e; color: #ffffff;")
        layout.addWidget(self.console)
        
        # Control buttons
        btn_layout = QHBoxLayout()
        self.clear_btn = QPushButton("Clear Console")
        self.clear_btn.clicked.connect(self.clear_console)
        btn_layout.addWidget(self.clear_btn)
        
        self.auto_scroll = QCheckBox("Auto-scroll")
        self.auto_scroll.setChecked(True)
        btn_layout.addWidget(self.auto_scroll)
        
        btn_layout.addStretch()
        layout.addLayout(btn_layout)
    
    def log(self, message: str):
        """Add a message to the console."""
        self.console.append(message)
        if self.auto_scroll.isChecked():
            self.console.verticalScrollBar().setValue(
                self.console.verticalScrollBar().maximum()
            )
    
    def clear_console(self):
        """Clear the console."""
        self.console.clear()


class ResultsPanel(QWidget):
    """Panel for displaying and comparing test results."""
    
    def __init__(self, parent=None):
        """
        Initialize the results panel.
        
        Args:
            parent: The parent widget.
        """
        super().__init__(parent)
        self._init_ui()
        self.results = {}
    
    def _init_ui(self):
        """Initialize the user interface."""
        layout = QVBoxLayout(self)
        
        # Tabs for different result views
        self.tabs = QTabWidget()
        
        # Summary tab
        self.summary_tab = QWidget()
        summary_layout = QVBoxLayout(self.summary_tab)
        self.summary_text = QTextEdit()
        self.summary_text.setReadOnly(True)
        self.summary_text.setFont(QFont("Segoe UI", 10))
        summary_layout.addWidget(self.summary_text)
        
        # Details tab
        self.details_tab = QWidget()
        details_layout = QVBoxLayout(self.details_tab)
        self.details_text = QTextEdit()
        self.details_text.setReadOnly(True)
        self.details_text.setFont(QFont("Segoe UI", 10))
        details_layout.addWidget(self.details_text)
        
        # Comparison tab
        self.comparison_tab = QWidget()
        comparison_layout = QVBoxLayout(self.comparison_tab)
        self.comparison_text = QTextEdit()
        self.comparison_text.setReadOnly(True)
        self.comparison_text.setFont(QFont("Courier New", 10))
        comparison_layout.addWidget(self.comparison_text)
        
        # Console tab
        self.console_tab = QWidget()
        console_layout = QVBoxLayout(self.console_tab)
        self.debug_console = DebugConsolePanel()
        console_layout.addWidget(self.debug_console)
        
        # Add tabs
        self.tabs.addTab(self.console_tab, "Console")  # Show console first
        self.tabs.addTab(self.summary_tab, "Summary")
        self.tabs.addTab(self.details_tab, "Details")
        self.tabs.addTab(self.comparison_tab, "Comparison")
        
        # Set console tab as active
        self.tabs.setCurrentIndex(0)  # Show console tab by default
        
        layout.addWidget(self.tabs)
        
        # Export buttons
        export_layout = QHBoxLayout()
        
        self.export_pdf_btn = QPushButton("Export PDF")
        self.export_pdf_btn.clicked.connect(self._export_pdf)
        
        self.export_json_btn = QPushButton("Export JSON")
        self.export_json_btn.clicked.connect(self._export_json)
        
        self.export_md_btn = QPushButton("Export Markdown")
        self.export_md_btn.clicked.connect(self._export_markdown)
        
        export_layout.addWidget(self.export_pdf_btn)
        export_layout.addWidget(self.export_json_btn)
        export_layout.addWidget(self.export_md_btn)
        
        layout.addLayout(export_layout)
    
    def display_results(self, results: Dict[str, Any]):
        """
        Display test results.
        
        Args:
            results: Test results to display.
        """
        self.results = results
        
        # Generate and set summary text
        summary = self._generate_summary(results)
        self.summary_text.setText(summary)
        
        # Generate and set details text
        details = self._generate_details(results)
        self.details_text.setText(details)
        
        # Generate and set comparison text
        comparison = self._generate_comparison(results)
        self.comparison_text.setText(comparison)
    
    def _generate_summary(self, results: Dict[str, Any]) -> str:
        """
        Generate a summary of the test results.
        
        Args:
            results: Test results to summarize.
            
        Returns:
            Formatted summary text.
        """
        summary = []
        summary.append("Test Results Summary")
        summary.append("===================\n")
        
        for model, model_results in results.items():
            if not model_results:  # Skip empty results
                continue
            
            total_tests = len(model_results)
            if total_tests == 0:
                continue
                
            passed_tests = sum(1 for r in model_results if r.is_valid)
            avg_response_time = sum(r.response_time for r in model_results) / total_tests
            avg_tokens = sum(r.token_count for r in model_results) / total_tests
            
            summary.append(f"Model: {model}")
            summary.append(f"Tests Run: {total_tests}")
            summary.append(f"Tests Passed: {passed_tests}")
            summary.append(f"Success Rate: {(passed_tests/total_tests)*100:.1f}%")
            summary.append(f"Average Response Time: {avg_response_time:.2f}s")
            summary.append(f"Average Tokens Used: {avg_tokens:.1f}")
            summary.append("")  # Add blank line between models
        
        if len(summary) <= 3:  # Only has header
            summary.append("No test results available.")
            
        return "\n".join(summary)
    
    def _generate_details(self, results: Dict[str, Any]) -> str:
        """
        Generate detailed test results.
        
        Args:
            results: Test results to detail.
            
        Returns:
            Formatted details text.
        """
        details = []
        details.append("Detailed Test Results")
        details.append("===================\n")
        
        has_results = False
        
        for model, model_results in results.items():
            if not model_results:  # Skip models with no results
                continue
                
            has_results = True
            details.append(f"Model: {model}")
            details.append("-" * (len(model) + 7))
            
            for result in model_results:
                details.append(f"\nTest: {result.test_case_name}")
                details.append(f"Category: {result.category}")
                details.append(f"Status: {'✓ Passed' if result.is_valid else '✗ Failed'}")
                details.append(f"Response Time: {result.response_time:.2f}s")
                details.append(f"Tokens Used: {result.token_count}")
                details.append("\nPrompt:")
                details.append(result.prompt)
                details.append("\nResponse:")
                details.append(result.response)
                details.append("-" * 80)
            
            details.append("\n")
        
        if not has_results:
            details.append("No test results available.")
            
        return "\n".join(details)
    
    def _generate_comparison(self, results: Dict[str, Any]) -> str:
        """
        Generate a comparison of test results across models.
        
        Args:
            results: Test results to compare.
            
        Returns:
            Formatted comparison text.
        """
        comparison = []
        comparison.append("Model Comparison")
        comparison.append("===============\n")
        
        # Check if we have valid results
        has_results = any(model_results for model_results in results.values())
        if not has_results:
            comparison.append("No test results available.")
            return "\n".join(comparison)
        
        # Filter out empty result lists
        results = {model: results for model, results in results.items() if results}
        
        # Get model names
        model_names = list(results.keys())
        if not model_names:
            comparison.append("No models with results.")
            return "\n".join(comparison)
        
        # Organize results by test case
        test_cases = {}
        for model, model_results in results.items():
            for result in model_results:
                if result.test_case_name not in test_cases:
                    test_cases[result.test_case_name] = {}
                test_cases[result.test_case_name][model] = result
        
        # Compare each test case across models
        for test_name, test_results in test_cases.items():
            comparison.append(f"Test: {test_name}")
            comparison.append("-" * (len(test_name) + 6))
            
            # Create comparison table header
            comparison.append("\nMetric      | " + " | ".join(model_names))
            comparison.append("-" * (12 + sum(len(m) + 3 for m in model_names)))
            
            # Compare metrics
            metrics = ["Status", "Time (s)", "Tokens"]
            for metric in metrics:
                values = []
                for model in model_names:
                    result = test_results.get(model)
                    if result:
                        if metric == "Status":
                            values.append("Pass" if result.is_valid else "Fail")
                        elif metric == "Time (s)":
                            values.append(f"{result.response_time:.2f}")
                        else:  # Tokens
                            values.append(str(result.token_count))
                    else:
                        values.append("N/A")
                comparison.append(f"{metric:<10} | " + " | ".join(values))
            
            comparison.append("\n")
        
        return "\n".join(comparison)
    
    def _export_pdf(self):
        """Export results to PDF file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export PDF", "", "PDF Files (*.pdf)"
        )
        
        if not file_path:
            return
            
        try:
            # This is a placeholder for PDF export functionality
            # In the actual implementation, we would use reportlab to generate the PDF
            QMessageBox.information(
                self, "Export PDF", 
                "PDF export would be implemented here.\nFile: " + file_path
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Export Error", 
                f"Failed to export PDF: {str(e)}"
            )
    
    def _export_json(self):
        """Export results to JSON file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export JSON", "", "JSON Files (*.json)"
        )
        
        if not file_path:
            return
            
        try:
            # This is a placeholder for JSON export functionality
            # In the actual implementation, we would use json.dump to write the file
            QMessageBox.information(
                self, "Export JSON", 
                "JSON export would be implemented here.\nFile: " + file_path
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Export Error", 
                f"Failed to export JSON: {str(e)}"
            )
    
    def _export_markdown(self):
        """Export results to Markdown file."""
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Markdown", "", "Markdown Files (*.md)"
        )
        
        if not file_path:
            return
            
        try:
            # This is a placeholder for Markdown export functionality
            # In the actual implementation, we would generate markdown and write to file
            QMessageBox.information(
                self, "Export Markdown", 
                "Markdown export would be implemented here.\nFile: " + file_path
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Export Error", 
                f"Failed to export Markdown: {str(e)}"
            )


class MainWindow(QMainWindow):
    """Main application window for the LLM testing application."""
    
    def __init__(self):
        """Initialize the main window."""
        super().__init__()
        
        # Set window properties
        self.setWindowTitle("HamsterN LLM Tester")
        self.setMinimumSize(1200, 800)
        
        # Initialize settings
        self.settings = QSettings("HamsterN", "LLM-Tester")
        
        # Initialize API client
        self.client = OllamaClient()
        
        # Set up the UI
        self._setup_ui()
        self._setup_menu()
        self._setup_status_bar()
        
        # Connect signals
        self._connect_signals()
        
        # Restore window geometry from settings
        self._restore_settings()
    
    def _setup_ui(self):
        """Set up the main user interface."""
        # Create main widget
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
        
        # Create main layout
        self.main_layout = QHBoxLayout(self.central_widget)
        
        # Create left panel (Connection and Test Configuration)
        self.left_panel = QWidget()
        self.left_layout = QVBoxLayout(self.left_panel)
        
        # Create connection panel
        self.connection_panel = ConnectionPanel(self.client)
        self.left_layout.addWidget(self.connection_panel)
        
        # Create test execution panel with client reference
        self.test_panel = TestExecutionPanel(client=self.client)
        self.left_layout.addWidget(self.test_panel)
        
        # Add stretch to push panels to the top
        self.left_layout.addStretch()
        
        # Create right panel (Results) first
        self.results_panel = ResultsPanel()
        
        # Now set up logging handler after results panel is created
        self._setup_logging_handler()
        
        # Set logging level to debug to capture more detailed messages
        logger.setLevel(logging.DEBUG)
        
        # Create splitter to allow resizing
        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.addWidget(self.left_panel)
        self.splitter.addWidget(self.results_panel)
        self.splitter.setSizes([300, 900])  # Initial sizes
        
        self.main_layout.addWidget(self.splitter)
    
    def _setup_menu(self):
        """Set up the application menu bar."""
        menu_bar = self.menuBar()
        
        # File menu
        file_menu = menu_bar.addMenu("&File")
        
        # Export submenu
        export_menu = QMenu("&Export", self)
        
        export_pdf_action = QAction("Export as &PDF", self)
        export_pdf_action.setStatusTip("Export results as PDF")
        export_pdf_action.triggered.connect(self._export_results_pdf)
        
        export_json_action = QAction("Export as &JSON", self)
        export_json_action.setStatusTip("Export results as JSON")
        export_json_action.triggered.connect(self._export_results_json)
        
        export_md_action = QAction("Export as &Markdown", self)
        export_md_action.setStatusTip("Export results as Markdown")
        export_md_action.triggered.connect(self._export_results_markdown)
        
        export_menu.addAction(export_pdf_action)
        export_menu.addAction(export_json_action)
        export_menu.addAction(export_md_action)
        
        file_menu.addMenu(export_menu)
        
        # Import action
        import_action = QAction("&Import Results...", self)
        import_action.setStatusTip("Import previously saved test results")
        import_action.triggered.connect(self._import_results)
        file_menu.addAction(import_action)
        
        file_menu.addSeparator()
        
        # Exit action
        exit_action = QAction("E&xit", self)
        exit_action.setStatusTip("Exit the application")
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)
        
        # Test menu
        test_menu = menu_bar.addMenu("&Test")
        
        run_tests_action = QAction("&Run Tests", self)
        run_tests_action.setStatusTip("Run tests on selected models")
        run_tests_action.triggered.connect(self._run_tests)
        test_menu.addAction(run_tests_action)
        
        refresh_models_action = QAction("&Refresh Models", self)
        refresh_models_action.setStatusTip("Refresh available models")
        refresh_models_action.triggered.connect(self._refresh_models_menu)
        test_menu.addAction(refresh_models_action)
        
        # Help menu
        help_menu = menu_bar.addMenu("&Help")
        
        about_action = QAction("&About", self)
        about_action.setStatusTip("Show about dialog")
        about_action.triggered.connect(self._show_about)
        help_menu.addAction(about_action)
    
    def _setup_status_bar(self):
        """Set up the status bar."""
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        
        # Connection status label
        self.connection_status = QLabel("Not connected")
        self.status_bar.addPermanentWidget(self.connection_status)
    
    def _connect_signals(self):
        """Connect signals between components."""
        # Connection panel signals
        self.connection_panel.connection_changed.connect(self._on_connection_changed)
        self.connection_panel.models_list.itemSelectionChanged.connect(self._on_model_selection_changed)
        
        # Test panel signals
        self.test_panel.test_started.connect(self._on_test_started)
        self.test_panel.test_progress.connect(self._on_test_progress)
        self.test_panel.test_completed.connect(self._on_test_completed)
    
    def _setup_logging_handler(self):
        """Set up logging handler for debug console."""
        class DebugConsoleHandler(logging.Handler):
            def __init__(self, console_widget):
                super().__init__()
                self.console = console_widget
                
            def emit(self, record):
                msg = self.format(record)
                # Use QTimer.singleShot instead of callLater
                QTimer.singleShot(10, lambda: self.console.log(msg))
        
        # Create and add handler
        handler = DebugConsoleHandler(self.results_panel.debug_console)
        handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
        
        # Add handler to both our logger and the api logger
        logger.addHandler(handler)
        logging.getLogger('src.api.ollama_client').addHandler(handler)
        
        # Add a special handler for response streaming
        class ResponseStreamHandler(logging.Handler):
            def __init__(self, console_widget):
                super().__init__()
                self.console = console_widget
                self.setLevel(logging.DEBUG)
                
            def emit(self, record):
                if "Model" in record.msg and ":" in record.msg:
                    # Display model responses directly in the console
                    QTimer.singleShot(1, lambda: self.console.log(record.msg))
        
        # Add the stream handler
        stream_handler = ResponseStreamHandler(self.results_panel.debug_console)
        logging.getLogger('src.api.ollama_client').addHandler(stream_handler)
    
    def _restore_settings(self):
        """Restore settings from previous sessions."""
        # Restore window geometry if available
        geometry = self.settings.value("geometry")
        if geometry:
            self.restoreGeometry(geometry)
        
        # Restore splitter state if available
        splitter_state = self.settings.value("splitter_state")
        if splitter_state:
            self.splitter.restoreState(splitter_state)
    
    def _on_connection_changed(self, connected: bool, message: str):
        """
        Handle connection status changes.
        
        Args:
            connected: Whether the connection is established.
            message: Status message.
        """
        # Update status bar
        self.connection_status.setText(message)
        
        # Update status bar color
        if connected:
            self.connection_status.setStyleSheet("color: green;")
        else:
            self.connection_status.setStyleSheet("color: red;")
    
    def _on_model_selection_changed(self):
        """Handle model selection changes."""
        selected_models = self.connection_panel.get_selected_models()
        
        # Debug log to see what models are selected
        logger.debug(f"Model selection changed: {selected_models}")
        
        # Update the test panel with selected models
        self.test_panel.set_selected_models(selected_models)
        
        # Update status bar
        if selected_models:
            self.status_bar.showMessage(f"Selected models: {', '.join(selected_models)}")
        else:
            self.status_bar.showMessage("No models selected")
    
    def _on_test_started(self, test_suite: str, models: List[str]):
        """
        Handle test start event.
        
        Args:
            test_suite: The name of the test suite being executed.
            models: The list of models being tested.
        """
        # Update status bar
        model_names = ", ".join(models)
        self.status_bar.showMessage(f"Running {test_suite} tests on models: {model_names}")
    
    def _on_test_progress(self, current: int, total: int):
        """
        Handle test progress updates.
        
        Args:
            current: Current test count.
            total: Total test count.
        """
        # Update status bar with progress
        percentage = int((current / total) * 100) if total > 0 else 0
        self.status_bar.showMessage(f"Testing progress: {current}/{total} ({percentage}%)")
    
    def _on_test_completed(self, results: Dict[str, Any]):
        """
        Handle test completion.
        
        Args:
            results: Test results.
        """
        # Update status bar
        self.status_bar.showMessage("Testing completed")
        
        # Add debug log
        logger.info("Test execution completed. Displaying results...")
        
        # Display results
        self.results_panel.display_results(results)
        
        # Switch to results tab
        self.results_panel.tabs.setCurrentIndex(1)  # Show summary tab (now at index 1)
    
    def _run_tests(self):
        """Run tests action."""
        # Forward to the test panel's start tests method
        asyncio.create_task(self.test_panel._start_tests())
    
    @asyncSlot()
    async def _refresh_models_menu(self):
        """Refresh models action from menu."""
        # Forward to the connection panel's refresh models method
        await self.connection_panel._refresh_models()
    
    def _export_results_pdf(self):
        """Export results as PDF."""
        self.results_panel._export_pdf()
    
    def _export_results_json(self):
        """Export results as JSON."""
        self.results_panel._export_json()
    
    def _export_results_markdown(self):
        """Export results as Markdown."""
        self.results_panel._export_markdown()
    
    def _import_results(self):
        """Import previously saved results."""
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Import Results", "", "JSON Files (*.json)"
        )
        
        if not file_path:
            return
            
        try:
            # This is a placeholder for import functionality
            QMessageBox.information(
                self, "Import Results", 
                "Results import would be implemented here.\nFile: " + file_path
            )
        except Exception as e:
            QMessageBox.critical(
                self, "Import Error", 
                f"Failed to import results: {str(e)}"
            )
    
    def _show_about(self):
        """Show the about dialog."""
        QMessageBox.about(self, "About HamsterN LLM Tester",
            "<h1>HamsterN LLM Tester</h1>"
            "<p>A desktop application for testing and benchmarking Ollama LLM models.</p>"
            "<p>Version: 0.1.0</p>"
            "<p>&copy; 2025 HamsterN</p>")
    
    def closeEvent(self, event):
        """Handle window close event."""
        # Save window geometry
        self.settings.setValue("geometry", self.saveGeometry())
        
        # Save splitter state
        self.settings.setValue("splitter_state", self.splitter.saveState())
        
        # Close client connection
        if self.client:
            # Note: In a real implementation, we would use a async executor to close the connection
            # For simplicity, we're just showing what would be done
            pass
        
        event.accept()

