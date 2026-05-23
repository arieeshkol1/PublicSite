"""
Baseline file source.

Reads and parses the bundled aws-cost-optimization-tips.json file
to include manually curated tips in the sync process.
"""

import json
import logging

logger = logging.getLogger(__name__)


def load_baseline_tips(file_path: str) -> list[dict]:
    """Read the bundled tips JSON file and return the list of tip dicts.

    Each tip is marked with syncSource="baseline" for tracking.

    Args:
        file_path: Path to the aws-cost-optimization-tips.json file.

    Returns:
        List of tip dicts from the file, or an empty list on error.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        tips = data.get("tips", [])

        # Mark each tip with the baseline sync source
        for tip in tips:
            tip["syncSource"] = "baseline"

        logger.info(
            json.dumps({
                "event": "baseline_tips_loaded",
                "file_path": file_path,
                "tips_count": len(tips),
            })
        )

        return tips

    except FileNotFoundError:
        logger.warning(
            json.dumps({
                "event": "baseline_file_not_found",
                "file_path": file_path,
                "message": "Baseline tips file not found, continuing without baseline tips",
            })
        )
        return []

    except json.JSONDecodeError as e:
        logger.warning(
            json.dumps({
                "event": "baseline_file_parse_error",
                "file_path": file_path,
                "error": str(e),
                "message": "Failed to parse baseline tips JSON, continuing without baseline tips",
            })
        )
        return []

    except Exception as e:
        logger.warning(
            json.dumps({
                "event": "baseline_file_error",
                "file_path": file_path,
                "error": str(e),
                "message": "Unexpected error reading baseline tips file, continuing without baseline tips",
            })
        )
        return []
