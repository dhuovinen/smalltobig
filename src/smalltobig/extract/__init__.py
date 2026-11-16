"""Chunk, extract, verify — Stage 2 of docs/PLAN.md §2. The gate in
verify.py is the cheapest high-value thing in the whole system: a claim
that fails it is rejected deterministically, no model or judgment call.
"""
