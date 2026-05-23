from typing import Dict, Any

import anyio.to_thread
import pandas as pd
import subprocess
import os
import re


def extract_text2qti_error(err: str) -> Dict[str, Any]:
    lines = err.splitlines()

    for i, line in enumerate(lines):
        if "text2qti.err.Text2qtiError: In" in line:

            match = re.search(r'In ".*/([^/]+)" on line (\d+):', line)

            file_name = None
            line_num = None

            if match:
                file_name = match.group(1)
                line_num = int(match.group(2))

            detail = lines[i + 1].strip() if i + 1 < len(lines) else ""

            return {
                "type": "text2qti_error",
                "file": file_name,
                "line": line_num,
                "message": detail,
                "raw": err
            }

    # fallback (unknown error shape)
    return {
        "type": "unknown_error",
        "file": None,
        "line": None,
        "message": err.strip(),
        "raw": err
    }


def run_text2qti_sync(input_path: str, workdir: str) -> str:
    try:
        res = subprocess.run(
            ["text2qti", input_path],
            check=True,
            cwd=workdir,
            capture_output=True,
            text=True
        )
    except subprocess.CalledProcessError as e:
        err = e.stdout or e.stderr or "Unknown Error"
        # print(f'‼️ ERROR:: {err}')
        clean_error = extract_text2qti_error(err)
        raise RuntimeError(clean_error)

    base = os.path.splitext(os.path.basename(input_path))[0]
    output_path = os.path.join(workdir, f'{base}.zip')

    if not os.path.exists(output_path):
        raise RuntimeError({
            "type": "missing_output",
            "file": None,
            "line": None,
            "message": "No QTI zip generated",
            "raw": ""
        })
    return output_path


async def run_text2qti(input_path: str, workdir: str) -> str:
    return await anyio.to_thread.run_sync(
        run_text2qti_sync,
        input_path,
        workdir
    )


def excel_to_json(input_path: str):
    df = pd.read_excel(input_path, engine="openpyxl");

    questions = []

    for _, row in df.iloc[0:].iterrows():
        if row["Question Text"]:
            q = {
                "text": str(row["Question Text"]),
                "type": str(row["Question Type"]).lower(),
                "points": (float(row["Question Points"])
                           if not pd.isna(row["Question Points"]) else 1),
                "correct": (str(row["Correct Answer(s)"]).split(",")
                            if not pd.isna(row["Correct Answer(s)"]) else []),
                "feedback": {
                    "general": str(row.get("Question Feedback", "") or ""),
                    "correct": str(row.get("Correct Answer Feedback", "") or ""),
                    "incorrect": str(row.get("Incorrect Answer Feedback", "") or ""),
                }
            }
        questions.append(q)

    print({
        "title": input_path.split("/")[-1].replace(".xlsx", ""),
        "questions": questions,
        "settings": []
    }

    )

    return {
        "title": input_path.split("/")[-1].replace(".xlsx", ""),
        "questions": questions,
        "settings": []
    }


def flexiquiz_response_summary_to_markdown(input_file):
    df = pd.read_excel(input_file, header=None)

    lines = []

    for _, row in df.iterrows():
        a, b = row[0], row[1]  # extract first 2 column values
        print(a, b)
