"""Citation builder.

Constructs deduplicated, human-readable source references from the list of
retrieved chunks that backed an answer. Never fabricates locations — it only
reports what is present in the chunk metadata.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .retriever import RetrievedChunk


@dataclass
class Citation:
    """A single source citation."""

    filename: str
    file_type: str
    locations: list[str] = field(default_factory=list)

    def display(self) -> str:
        """Render as a readable string, e.g. 'sales_q1.xlsx → Sheet1 → rows 2–31'."""
        if self.locations:
            return "; ".join(self.locations)
        return self.filename


class CitationBuilder:
    """Aggregates RetrievedChunks into a deduplicated list of Citations."""

    def build(self, chunks: list[RetrievedChunk]) -> list[Citation]:
        """Build citations from retrieved chunks.

        Groups by filename so each source file appears once with a list of
        distinct location references.

        Args:
            chunks: Retrieved chunks that contributed to the answer.

        Returns:
            List of Citation objects, one per unique source file, preserving
            the order in which sources first appeared.
        """
        # Use an ordered dict to preserve first-appearance order
        seen: dict[str, Citation] = {}

        for chunk in chunks:
            fname = chunk.source_filename
            if fname not in seen:
                seen[fname] = Citation(filename=fname, file_type=chunk.file_type)

            location = chunk.location_label()
            # Only the part after the filename (i.e. sheet/slide/row info)
            if " → " in location:
                loc_detail = location.split(" → ", 1)[1]
            else:
                loc_detail = ""

            if loc_detail and loc_detail not in seen[fname].locations:
                seen[fname].locations.append(loc_detail)

        return list(seen.values())

    def format_for_response(self, citations: list[Citation]) -> list[dict]:
        """Serialise citations to a list of dicts for API response inclusion."""
        result = []
        for c in citations:
            result.append(
                {
                    "filename": c.filename,
                    "file_type": c.file_type,
                    "locations": c.locations,
                    "display": c.display(),
                }
            )
        return result
