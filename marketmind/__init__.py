"""
MarketMind
==========

An AI-Powered Financial Intelligence & Quantitative Research Platform.

MarketMind is not a stock prediction application.
It is a quantitative research platform whose purpose is to discover hypotheses,
validate hypotheses, reject weak hypotheses, quantify uncertainty, evaluate
robustness, and explain model behaviour.

Finding no edge is a valid and valuable research outcome.

Usage
-----
    from marketmind.config import get_settings
    from marketmind.core.domain.asset import Asset

Architecture
------------
The package follows a hexagonal (ports & adapters) architecture.
Module dependency rules are enforced in CI. See docs/architecture/ for the
full architecture document.
"""

__version__ = "0.1.0"
__author__ = "MarketMind Contributors"
