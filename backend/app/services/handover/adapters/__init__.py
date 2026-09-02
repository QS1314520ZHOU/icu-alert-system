"""Handover data adapters — unified data source queries with status reporting.

Each adapter queries a specific MongoDB collection and returns a standardized
result dict with status (available|empty|failed|stale), counts, warnings, etc.
"""
