import csv
import json
from pathlib import Path


class EvaluationExporter:
    """
    Exports evaluation reports.

    Supported formats:
        - JSON
        - CSV
        - Markdown
    """

    @staticmethod
    def export_json(
        report: dict,
        output_path: str | Path,
    ):

        output_path = Path(output_path)

        with output_path.open(
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                report,
                f,
                indent=4,
                ensure_ascii=False,
            )

    @staticmethod
    def export_csv(
        rows: list[dict],
        output_path: str | Path,
    ):

        if not rows:
            return

        output_path = Path(output_path)

        with output_path.open(
            "w",
            newline="",
            encoding="utf-8"
        ) as f:

            writer = csv.DictWriter(
                f,
                fieldnames=rows[0].keys()
            )

            writer.writeheader()

            writer.writerows(rows)

    @staticmethod
    def export_markdown(
        report: dict,
        output_path: str | Path,
    ):

        output_path = Path(output_path)

        lines = []

        lines.append("# RAG Evaluation Report\n")

        lines.append(
            f"Generated: {report['created_at']}\n"
        )

        lines.append(
            f"Questions: {report['num_questions']}\n"
        )

        lines.append("## Retrieval Summary\n")

        for key, value in report[
            "retrieval_summary"
        ].items():

            lines.append(
                f"- **{key}**: {value:.4f}"
            )

        lines.append("")

        lines.append("## Generation Summary\n")

        for key, value in report[
            "generation_summary"
        ].items():

            lines.append(
                f"- **{key}**: {value:.4f}"
            )

        lines.append("")

        if report["llm_summary"]:

            lines.append("## LLM Judge Summary\n")

            for key, value in report[
                "llm_summary"
            ].items():

                lines.append(
                    f"- **{key}**: {value:.4f}"
                )

            lines.append("")

        output_path.write_text(
            "\n".join(lines),
            encoding="utf-8",
        )