from typing import Dict, Any

import anyio.to_thread
import pandas as pd
import subprocess
import textwrap
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
                "feedback": {
                    "general": (str(row["Question Feedback"])
                                if not pd.isna(row["Question Feedback"]) else None),
                    "correct": (str(row["Correct Answer Feedback"])
                                if not pd.isna(row["Correct Answer Feedback"]) else None),
                    "incorrect": (str(row["Incorrect Answer Feedback"])
                                  if not pd.isna(row["Incorrect Answer Feedback"]) else None),
                },
                "options": [],
                "correct": (str(row["Correct Answer(s)"]).split(",")
                            if not pd.isna(row["Correct Answer(s)"]) else []),
            }

            if row["Question Type"] == "Multiple Choice":
                for i in range(1, 11):
                    col = f"Option {i}"
                    if col in row and not pd.isna(row[col]):
                        q['options'].append(str(row[col]).strip())

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


def wrap_text(prefix, text, width=80):
    wrapped = textwrap.wrap(text, width=width)

    if not wrapped:
        return [prefix]

    lines = [prefix + wrapped[0]]

    indent = " " * len(prefix)

    for line in wrapped[1:]:
        lines.append(indent + line)

    return lines


def render_feedback(feedback):
    out = []

    if feedback['general']:
        out.append(f"... {feedback['general']}")

    if feedback['correct']:
        out.append(f"+   {feedback['correct']}")

    if feedback['incorrect']:
        out.append(f"-   {feedback['incorrect']}")

    return out


def render_multiple_choice(q, index):
    out = [f"Points: {q['points']}", f"{index}.  {q['text']}"]

    feedback = render_feedback(q["feedback"])

    if feedback:
        out.extend(feedback)

    correct = set(ans.strip() for ans in q["correct"])

    for idx, option in enumerate(q["options"], start=1):
        letter = chr(96 + idx)

        if str(idx) in correct:
            out.append(f"*{letter}) {option}")
        else:
            out.append(f"{letter})  {option}")

    return out


def render_multiple_answer(q, index):
    out = [f"Points: {q['points']}", f"{index}.  {q['text']}"]

    feedback = render_feedback(q["feedback"])

    if feedback:
        out.extend(feedback)

    correct = set(ans.strip() for ans in q["correct"])

    for idx, option in enumerate(q["options"], start=1):

        if str(idx) in correct:
            out.append(f"[*] {option}")
        else:
            out.append(f"[ ] {option}")

    return out


def render_short_answer(q, index):
    out = [f"Points: {q['points']}", f"{index}.  {q['text']}"]

    feedback = render_feedback(q["feedback"])

    if feedback:
        out.extend(feedback)

    for answer in q["correct"]:
        out.append(f"*   {answer.strip()}")

    return out


def render_numerical(q, index):
    out = [f"Points: {q['points']}", f"{index}.  {q['text']}"]

    feedback = render_feedback(q["feedback"])

    if feedback:
        out.extend(feedback)

    for answer in q["correct"]:
        out.append(f"=   {answer.strip()}")

    return out


def render_essay(q, index):
    out = [f"Points: {q['points']}", f"{index}.  {q['text']}"]

    feedback = render_feedback(q["feedback"])

    if feedback:
        out.extend(feedback)

    out.append("____")

    return out


def render_upload(q, index):
    out = [f"Points: {q['points']}", f"{index}.  {q['text']}"]

    feedback = render_feedback(q["feedback"])

    if feedback:
        out.extend(feedback)

    out.append("^^^^")

    return out


def render_quiz(quiz):
    out = [f"Quiz title: {quiz['title']}"]

    for idx, q in enumerate(quiz["questions"], start=1):
        qtype = q["type"]

        if qtype == "multiple choice" and len(q['correct']) > 1:
            out.extend(render_multiple_answer(q, idx))

        elif qtype == "multiple choice" and len(q['correct']) == 1:
            out.extend(render_multiple_choice(q, idx))

        elif qtype == "numerical":
            out.extend(render_numerical(q, idx))

        elif qtype == "essay":
            out.extend(render_essay(q, idx))

        elif qtype == "file upload":
            out.extend(render_upload(q, idx))

    return "\n".join(out)


def flexiquiz_response_summary_to_markdown(input_file):
    df = pd.read_excel(input_file, header=None)

    lines = []

    for _, row in df.iterrows():
        a, b = row[0], row[1]  # extract first 2 column values
        print(a, b)
