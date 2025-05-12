"""
Ollama API client implementation.

This module provides a client for interacting with the Ollama API,
supporting model listing, generation of responses, and retrieving model information.
"""

import time
import json
import asyncio
import logging
import traceback
from datetime import datetime
from typing import List, Dict, Any, Optional, NamedTuple, Union
from dataclasses import dataclass

import aiohttp

logger = logging.getLogger(__name__)

class ConnectionError(Exception):
    """Exception raised when connection to Ollama API fails."""
    pass

@dataclass
class ModelInfo:
    """Information about an Ollama model."""
    name: str
    size: int
    modified_at: str
    parameters: Optional[Dict[str, Any]] = None
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ModelInfo':
        """Create a ModelInfo instance from a dictionary."""
        return cls(
            name=data.get('name', ''),
            size=data.get('size', 0),
            modified_at=data.get('modified_at', ''),
            parameters=data.get('parameters', None)
        )

@dataclass
class Response:
    """Ollama API response data."""
    model: str
    created_at: str
    response: str
    done: bool
    context: List[int]
    total_duration: int  # in milliseconds
    load_duration: int   # in milliseconds
    prompt_eval_count: int
    prompt_eval_duration: int  # in milliseconds
    eval_count: int
    eval_duration: int  # in milliseconds
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Response':
        """Create a Response instance from a dictionary."""
        return cls(
            model=data.get('model', ''),
            created_at=data.get('created_at', ''),
            response=data.get('response', ''),
            done=data.get('done', False),
            context=data.get('context', []),
            total_duration=data.get('total_duration', 0),
            load_duration=data.get('load_duration', 0),
            prompt_eval_count=data.get('prompt_eval_count', 0),
            prompt_eval_duration=data.get('prompt_eval_duration', 0),
            eval_count=data.get('eval_count', 0),
            eval_duration=data.get('eval_duration', 0)
        )

class OllamaClient:
    """Client for interacting with the Ollama API."""
    
    def __init__(self):
        """Initialize the Ollama client."""
        self.base_url = None
        self.session = None
        self.is_connected = False
        self.last_error = None
        # Track API performance
        self.last_request_time = 0
        self.last_response_time = 0
        
    async def connect(self, host: str, port: int) -> bool:
        """
        Connect to an Ollama instance.
        
        Args:
            host: The host address of the Ollama instance.
            port: The port number of the Ollama instance.
            
        Returns:
            bool: True if connection is successful, False otherwise.
            
        Raises:
            ConnectionError: If connection to Ollama API fails.
        """
        logger.info(f"Connecting to Ollama API at {host}:{port}")
        self.base_url = f"http://{host}:{port}/api"
        self.is_connected = False
        self.last_error = None
        
        # Create a new client session if one doesn't exist
        if self.session is None or self.session.closed:
            logger.debug("Creating new aiohttp ClientSession")
            self.session = aiohttp.ClientSession()
            
        # Test the connection by listing models
        try:
            logger.debug("Testing connection by listing models...")
            await self.list_models()
            logger.info(f"Successfully connected to Ollama API at {host}:{port}")
            self.is_connected = True
            return True
        except Exception as e:
            self.last_error = str(e)
            logger.error(f"Failed to connect to Ollama API: {e}")
            logger.debug(f"Connection error details: {traceback.format_exc()}")
            raise ConnectionError(f"Failed to connect to Ollama API: {e}")
    
    async def close(self):
        """Close the client session."""
        logger.debug("Closing Ollama client session")
        if self.session and not self.session.closed:
            try:
                await self.session.close()
                logger.debug("Session closed successfully")
            except Exception as e:
                logger.error(f"Error closing session: {e}")
        self.is_connected = False
    
    async def list_models(self) -> List[ModelInfo]:
        """
        Get a list of available models from the Ollama instance.
        
        Returns:
            List[ModelInfo]: List of available models.
            
        Raises:
            ConnectionError: If the request to Ollama API fails.
        """
        if not self.base_url or not self.session:
            logger.error("Cannot list models: Not connected to Ollama API")
            raise ConnectionError("Not connected to Ollama API")
        
        logger.debug(f"Listing models from: {self.base_url}/tags")    
        start_time = time.time()
        self.last_request_time = start_time
        
        try:
            async with self.session.get(f"{self.base_url}/tags") as response:
                response_time = time.time() - start_time
                self.last_response_time = response_time
                logger.debug(f"Response received in {response_time:.3f}s with status {response.status}")
                
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Failed to list models with status {response.status}: {error_text}")
                    raise ConnectionError(f"Failed to list models (status {response.status}): {error_text}")
                
                data = await response.json()
                models = []
                
                # Log the raw response at debug level
                logger.debug(f"Raw models data: {json.dumps(data, indent=2)}")
                
                # Process models data
                model_list = data.get('models', [])
                if not model_list:
                    logger.warning("No models found in Ollama response")
                
                for model_data in model_list:
                    models.append(ModelInfo.from_dict(model_data))
                
                logger.info(f"Retrieved {len(models)} models from Ollama")
                return models
                
        except aiohttp.ClientError as e:
            logger.error(f"Client error while listing models: {e}")
            self.last_error = str(e)
            raise ConnectionError(f"Failed to list models: {e}")
        except Exception as e:
            logger.error(f"Unexpected error while listing models: {e}")
            logger.debug(f"Error details: {traceback.format_exc()}")
            self.last_error = str(e)
            raise ConnectionError(f"Failed to list models: {e}")
    
    async def generate_response(self, model: str, prompt: str, 
                              params: Optional[Dict[str, Any]] = None) -> Response:
        """
        Generate a response from the specified model.
        
        Args:
            model: The name of the model to use.
            prompt: The prompt to send to the model.
            params: Optional parameters for the model (temperature, etc.).
            
        Returns:
            Response: The model's response.
            
        Raises:
            ConnectionError: If the request to Ollama API fails.
        """
        if not self.is_connected or not self.base_url or not self.session:
            logger.error("Cannot generate response: Not connected to Ollama API")
            raise ConnectionError("Not connected to Ollama API")
            
        request_data = {
            "model": model,
            "prompt": prompt
        }
        
        if params:
            request_data.update(params)
        
        # Log the request details (truncating the prompt if too long)
        truncated_prompt = prompt[:100] + "..." if len(prompt) > 100 else prompt
        logger.debug(f"Generating response for model '{model}' with prompt: '{truncated_prompt}'")
        logger.debug(f"Request parameters: {params}")
        
        start_time = time.time()
        self.last_request_time = start_time
            
        try:
            full_response = ""
            last_data = {}
            
            async with self.session.post(f"{self.base_url}/generate", 
                                      json=request_data) as response:
                logger.info(f"Starting response generation with model {model}...")
                response_time = time.time() - start_time
                self.last_response_time = response_time
                logger.debug(f"Response received in {response_time:.3f}s with status {response.status}")
                
                if response.status != 200:
                    error_text = await response.text()
                    logger.error(f"Failed to generate response with status {response.status}: {error_text}")
                    raise ConnectionError(f"Failed to generate response (status {response.status}): {error_text}")
                
                # Process the NDJSON streaming response
                done = False
                async for line in response.content:
                    if not line:
                        continue
                    
                    line_str = line.decode('utf-8').strip()
                    if not line_str:
                        continue
                        
                    try:
                        data = json.loads(line_str)
                        last_data = data  # Save for metrics
                        
                        if 'response' in data:
                            chunk = data['response']
                            full_response += chunk
                            # Log each response chunk for real-time display
                            logger.info(f"Model {model} response: {chunk}")
                            
                        if data.get('done', False):  # Check if response is complete
                            logger.info(f"Response completed. Total tokens: {data.get('eval_count', 0)}")
                            # Explicitly set done flag and break immediately
                            done = True
                            break
                            
                    except json.JSONDecodeError as e:
                        logger.warning(f"Failed to decode response line: {e}")
                        continue
            
            response_time = time.time() - start_time
            
            # Create final response object with the collected data
            final_data = {
                'model': model,
                'created_at': datetime.now().isoformat(),
                'response': full_response,
                'done': True,
                'context': last_data.get('context', []),
                'total_duration': int(response_time * 1000),  # convert to ms
                'load_duration': last_data.get('load_duration', 0),
                'prompt_eval_count': last_data.get('prompt_eval_count', 0),
                'prompt_eval_duration': last_data.get('prompt_eval_duration', 0),
                'eval_count': last_data.get('eval_count', len(full_response.split())),  # Fallback to word count
                'eval_duration': last_data.get('eval_duration', int(response_time * 1000))
            }
            
            # Log a summary of the response
            truncated_response = full_response[:100] + "..." if len(full_response) > 100 else full_response
            logger.debug(f"Response from model '{model}': '{truncated_response}'")
            logger.debug(f"Response metrics: time={response_time:.3f}s, tokens={final_data.get('eval_count', 0)}")
            # Note: We already logged the completion message when done=True was received
            
            return Response.from_dict(final_data)
        except aiohttp.ClientError as e:
            logger.error(f"Client error while generating response: {e}")
            self.last_error = str(e)
            raise ConnectionError(f"Failed to generate response: {e}")
        except Exception as e:
            logger.error(f"Unexpected error while generating response: {e}")
            logger.debug(f"Error details: {traceback.format_exc()}")
            self.last_error = str(e)
            raise ConnectionError(f"Failed to generate response: {e}")
    
    async def get_model_info(self, model: str) -> ModelInfo:
        """
        Get information about a specific model.
        
        Args:
            model: The name of the model.
            
        Returns:
            ModelInfo: Information about the model.
            
        Raises:
            ConnectionError: If the request to Ollama API fails.
        """
        if not self.is_connected or not self.base_url or not self.session:
            logger.error("Cannot get model info: Not connected to Ollama API")

