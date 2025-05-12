"""
Test management functionality for the LLM testing framework.

This module provides classes for managing test cases, test suites, and test execution.
"""

import asyncio
import time
from typing import List, Dict, Any, Optional, Callable, Awaitable, Union
from dataclasses import dataclass
from datetime import datetime
import uuid

from ..api.ollama_client import OllamaClient, Response

@dataclass
class TestCase:
    """A single test case for an LLM model."""
    id: str
    name: str
    prompt: str
    category: str
    expected_result: Optional[str] = None
    validation_function: Optional[Callable[[str], bool]] = None
    parameters: Optional[Dict[str, Any]] = None
    
    def __init__(self, name: str, prompt: str, category: str, 
                expected_result: Optional[str] = None,
                validation_function: Optional[Callable[[str], bool]] = None,
                parameters: Optional[Dict[str, Any]] = None):
        """
        Initialize a new test case.
        
        Args:
            name: The name of the test case.
            prompt: The prompt to send to the model.
            category: The category of the test case (e.g., math, code, general knowledge).
            expected_result: Optional expected result for simple string matching.
            validation_function: Optional function for complex validation logic.
            parameters: Optional model parameters for this specific test case.
        """
        self.id = str(uuid.uuid4())
        self.name = name
        self.prompt = prompt
        self.category = category
        self.expected_result = expected_result
        self.validation_function = validation_function
        self.parameters = parameters or {}
    
    def validate_response(self, response: str) -> bool:
        """
        Validate the model's response against expected results.
        
        Args:
            response: The response from the model.
            
        Returns:
            bool: True if the response is valid, False otherwise.
        """
        if self.validation_function:
            return self.validation_function(response)
        elif self.expected_result:
            return response.strip() == self.expected_result.strip()
        else:
            # No validation criteria specified
            return True

@dataclass
class TestResult:
    """Result of a test case execution."""
    test_case_id: str
    test_case_name: str
    model_name: str
    prompt: str
    response: str
    response_time: float  # in seconds
    token_count: int
    is_valid: bool
    category: str
    timestamp: datetime
    metrics: Dict[str, Any]
    
    def __init__(self, test_case: TestCase, model_name: str, response: Response):
        """
        Initialize a test result.
        
        Args:
            test_case: The test case that was executed.
            model_name: The name of the model that was tested.
            response: The response from the model.
        """
        self.test_case_id = test_case.id
        self.test_case_name = test_case.name
        self.model_name = model_name
        self.prompt = test_case.prompt
        self.response = response.response
        self.response_time = response.total_duration / 1000.0  # convert ms to seconds
        self.token_count = response.prompt_eval_count + response.eval_count
        self.is_valid = test_case.validate_response(response.response)
        self.category = test_case.category
        self.timestamp = datetime.now()
        self.metrics = {
            "load_duration": response.load_duration,
            "prompt_eval_count": response.prompt_eval_count,
            "prompt_eval_duration": response.prompt_eval_duration,
            "eval_count": response.eval_count,
            "eval_duration": response.eval_duration
        }


class TestSuite:
    """A collection of test cases to be executed together."""
    
    def __init__(self, name: str, description: str = ""):
        """
        Initialize a new test suite.
        
        Args:
            name: The name of the test suite.
            description: A description of the test suite.
        """
        self.id = str(uuid.uuid4())
        self.name = name
        self.description = description
        self.test_cases: List[TestCase] = []
        
    def add_test_case(self, test_case: TestCase) -> None:
        """
        Add a test case to the suite.
        
        Args:
            test_case: The test case to add.
        """
        self.test_cases.append(test_case)
        
    def add_test_cases(self, test_cases: List[TestCase]) -> None:
        """
        Add multiple test cases to the suite.
        
        Args:
            test_cases: The test cases to add.
        """
        self.test_cases.extend(test_cases)
        
    def get_test_cases(self) -> List[TestCase]:
        """
        Get all test cases in this suite.
        
        Returns:
            List[TestCase]: The test cases in this suite.
        """
        return self.test_cases


class TestManager:
    """Manages the execution of tests against LLM models."""
    
    def __init__(self, client: OllamaClient):
        """
        Initialize a new test manager.
        
        Args:
            client: The Ollama client to use for executing tests.
        """
        self.client = client
        self.results: Dict[str, List[TestResult]] = {}  # model_name -> results
        
    async def run_test(self, model: str, test_case: TestCase) -> TestResult:
        """
        Run a single test case against a model.
        
        Args:
            model: The name of the model to test.
            test_case: The test case to execute.
            
        Returns:
            TestResult: The result of the test execution.
            
        Raises:
            ConnectionError: If the request to Ollama API fails.
        """
        # Combine default and test-specific parameters
        params = test_case.parameters.copy() if test_case.parameters else {}
        
        try:
            # Execute the test and wait for completion
            response = await self.client.generate_response(
                model=model,
                prompt=test_case.prompt,
                params=params
            )
            
            # Ensure the response is marked as complete
            if not response.done:
                import logging
                logging.getLogger(__name__).warning(f"Response for test '{test_case.name}' with model '{model}' may not be complete")
            
            # Create test result from response
            result = TestResult(test_case, model, response)
            
            # Store the result
            if model not in self.results:
                self.results[model] = []
            self.results[model].append(result)
            
            # Break immediately after getting a complete response
            return result
            
        except Exception as e:
            import logging
            logging.getLogger(__name__).error(f"Error in test execution: {e}")
            raise ConnectionError(f"Failed to execute test: {e}")
        
    async def run_test_suite(self, model: str, test_suite: TestSuite) -> List[TestResult]:
        """
        Run a test suite against a model.
        
        Args:
            model: The name of the model to test.
            test_suite: The test suite to execute.
            
        Returns:
            List[TestResult]: The results of the test executions.
            
        Raises:
            ConnectionError: If the request to Ollama API fails.
        """
        results = []
        for test_case in test_suite.get_test_cases():
            result = await self.run_test(model, test_case)
            results.append(result)
        return results
        
    async def run_parallel_tests(self, models: List[str], test_suite: TestSuite, 
                              max_concurrency: int = 5) -> Dict[str, List[TestResult]]:
        """
        Run a test suite against multiple models in parallel.
        
        Args:
            models: The names of the models to test.
            test_suite: The test suite to execute.
            max_concurrency: Maximum number of concurrent tests.
            
        Returns:
            Dict[str, List[TestResult]]: The results of the test executions, organized by model.
            
        Raises:
            ConnectionError: If the request to Ollama API fails.
        """
        all_results = {}
        
        # Create a semaphore to limit concurrency
        semaphore = asyncio.Semaphore(max_concurrency)
        
        async def _run_test_with_semaphore(model: str, test_case: TestCase):
            async with semaphore:
                return await self.run_test(model, test_case)
        
        # Create tasks for all models and test cases
        tasks = []
        for model in models:
            if model not in all_results:
                all_results[model] = []
                
            for test_case in test_suite.get_test_cases():
                tasks.append(_run_test_with_semaphore(model, test_case))
        
        # Run all tasks
        results = await asyncio.gather(*tasks)
        
        # Organize results by model
        for result in results:
            if result.model_name not in all_results:
                all_results[result.model_name] = []
            all_results[result.model_name].append(result)
        
        return all_results
    
    def get_results(self, model: Optional[str] = None) -> Union[Dict[str, List[TestResult]], List[TestResult]]:
        """
        Get test results.
        
        Args:
            model: Optional model name to filter results.
            
        Returns:
            Either a dictionary mapping model names to lists of results,
            or a list of results for a specific model.
        """
        if model:
            return self.results.get(model, [])
        return self.results

