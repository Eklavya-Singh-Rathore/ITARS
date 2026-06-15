"""ITARS V2 backend package — single source of truth for the serving system.

Ported from the Hugging Face deployment (`hf_deploy/`) and refactored into
modular services with one configuration source, fatal artifact validation,
and a single shared feature-extraction function (skew fix).
"""

__version__ = "2.0.0-phase1"
