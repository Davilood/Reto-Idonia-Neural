from __future__ import annotations


class ReportService:
    def summarize_for_recog(self, extracted_text: str) -> str:
        compact = " ".join(extracted_text.split())
        if len(compact) <= 6000:
            return compact
        return f"{compact[:5800]} ... [texto truncado para Recog]"
