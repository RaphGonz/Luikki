"""Layered colour-flatting pipeline for comic and manga production.

Architecture: exactness comes from deterministic segmentation. The generative
model is a colour *proposer* behind a swappable interface, never the output
path. See flatting-pipeline-spec.md.
"""

__version__ = "0.4.1"
