"""
API module for interacting with Ollama LLM services.

This module provides classes and utilities for connecting to and interacting with
Ollama API endpoints, handling model listing, prompt generation, and response processing.
"""

from .ollama_client import OllamaClient, Response, ModelInfo, ConnectionError

__all__ = ["OllamaClient", "Response", "ModelInfo", "ConnectionError"]

