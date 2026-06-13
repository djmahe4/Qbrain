import pytest
from brain.docstring_parser import DocstringParser

def test_genome_construction():
    func = {
        "name": "calculateInterest",
        "signature": "principal: float, rate: float",
        "docstring": "Calculates compound interest dynamically over periods."
    }
    genome = DocstringParser.build_genome(func)
    assert genome == "calculateInterest(principal: float, rate: float) — Calculates compound interest dynamically over periods."

    func_no_sig = {
        "name": "compute",
        "docstring": "Performs base computational logic."
    }
    genome_no_sig = DocstringParser.build_genome(func_no_sig)
    assert genome_no_sig == "compute — Performs base computational logic."
