"""Offline evaluation tooling for the PEA Knowledge Voice Agent.

Nothing in this package runs during the voice runtime; it exists so retrieval and answer
quality can be re-measured after Knowledge changes. All generated output goes to the
gitignored ``evaluation/rag/out/`` directory.
"""
