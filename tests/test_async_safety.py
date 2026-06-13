import pytest
from brain.language_parser import LanguageParser

def test_language_parser_async_safety_blocking_calls():
    parser = LanguageParser()
    
    # Positive case: async def with time.sleep
    code = """
async def fetch_data():
    time.sleep(1)
    return {"ok": True}
"""
    warnings = parser.parse_coding_standards({"name": "fetch", "code_snippet": code})
    assert any("async safety" in w.lower() and "time.sleep" in w.lower() for w in warnings)
    
    # Positive case: async def with requests
    code = """
async def sync_remote():
    res = requests.get("https://api.com")
    return res.json()
"""
    warnings = parser.parse_coding_standards({"name": "sync", "code_snippet": code})
    assert any("async safety" in w.lower() and "requests" in w.lower() for w in warnings)

def test_language_parser_async_safety_negative():
    parser = LanguageParser()
    
    # Negative case: normal def with time.sleep (allowed, though maybe not ideal, it's not an async safety issue)
    code = """
def slow_op():
    time.sleep(1)
"""
    warnings = parser.parse_coding_standards({"name": "slow", "code_snippet": code})
    assert not any("async safety" in w.lower() for w in warnings)
    
    # Negative case: async def with await asyncio.sleep
    code = """
async def fast_op():
    await asyncio.sleep(1)
"""
    warnings = parser.parse_coding_standards({"name": "fast", "code_snippet": code})
    assert not any("async safety" in w.lower() for w in warnings)
