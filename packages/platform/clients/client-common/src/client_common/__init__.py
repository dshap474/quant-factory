"""Shared transport and frame helpers for quant-factory platform clients.

USAGE: from client_common import HTTPClient, RetryConfig, records_to_frame
"""

from .frames import csv_text_to_frame, key_value_frame, records_to_frame
from .http import DEFAULT_USER_AGENT, HTTPClient, RetryConfig

__all__ = [
    "DEFAULT_USER_AGENT",
    "HTTPClient",
    "RetryConfig",
    "csv_text_to_frame",
    "key_value_frame",
    "records_to_frame",
]
