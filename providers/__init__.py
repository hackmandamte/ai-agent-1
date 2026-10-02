"""LLM provider implementations.

Each module in this package implements one provider against the shared
contract in :mod:`providers.base`. ``llm`` wires them into a deterministic
provider router; nothing here imports ``llm``, so the dependency only ever
points inwards.
"""
