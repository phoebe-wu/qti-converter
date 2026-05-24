from typing import Dict, Any, List
from dataclasses import dataclass, field
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


@dataclass
class Feedback:
    general: str
    correct: str
    incorrect: str


@dataclass
class Question:
    text: str
    type: str
    points: str
    options: list[str]
    correct: list[str]
    feedback: Feedback


@dataclass
class Settings:
    shuffle_answers: bool
    show_correct_answers: bool
    one_question_at_a_time: bool
    cant_go_back: bool


def default_settings():
    return Settings(
        shuffle_answers=False,
        show_correct_answers=False,
        one_question_at_a_time=False,
        cant_go_back=False
    )


@dataclass
class Quiz:
    title: str
    questions: List[Question]
    settings: Settings


def normalize_row(row):
    print(row)

    def clean(val):
        if pd.isna(val):
            return None
        return str(val).strip()

    def parse_list(val):
        if pd.isna(val) or str(val).strip() == "":
            return []
        return [x.strip() for x in str(val).split(",") if x.strip()]

    # options (Option 1..10)
    options = []
    for i in range(1, 11):
        col = f"Option {i}"
        if col in row and not pd.isna(row[col]):
            options.append(row[col])

    return Question(
        text=clean(row["Question Text"]),
        type=clean(row["Question Type"]).lower(),
        points=str(row["Question Points"]) if not pd.isna(row["Question Points"]) else "1",
        options=options,
        correct=parse_list(row.get("Correct Answer(s)")),
        feedback= Feedback(
            general=clean(row.get("Question Feedback")),
            correct=clean(row.get("Correct Answer Feedback")),
            incorrect=clean(row.get("Incorrect Answer Feedback")),
    )
    )


def validate_mc(q: Question):
    if len(q.correct) < 1:
        raise ValueError("Multiple choice questions must have at least one correct answer")

    if len(set(q.options)) != len(q.options):
        raise ValueError("Duplicate correct answers provided")

    if len(q.options) < 2:
        raise ValueError("Multiple choice questions must have at least two options")

    if not all(c.isdigit() for c in q.correct):
        raise ValueError("Multiple choice answers must be numeric indices only")

    for c in q.correct:
        idx = int(c)
        if idx < 1 or idx > len(q.options):
            raise ValueError("Answer index out of range")


def validate_short_answer(q: Question):
    if q.options:
        raise ValueError("Short answer questions do not require options")

    if not q.correct:
        raise ValueError("Short answer questions must have at least one correct answer")

    if len(set(q.options)) != len(q.options):
        raise ValueError("Duplicate correct answers provided")

    if all(a.isdigit() for a in q.correct):
        raise ValueError("Numeric answers should use the numerical question type")


def validate_numerical(q: Question):
    if q.options:
        raise ValueError("Numerical must not have options")

    answer = q.correct[0]

    if not answer:
        raise ValueError("Numerical questions must have at least one correct answer")

    patterns = [
        r"\d+(\.\d+)?",  # single number
        r"\[\d+(\.\d+)?,\s*\d+(\.\d+)?\]",  # range
        r"\d+(\.\d+)?\s*\+-\s*\d+(\.\d+)?%?"  # tolerance
    ]

    if not any(re.fullmatch(p, answer) for p in patterns):
        raise ValueError(f"Invalid numerical format: {answer}")


def validate_essay(q: Question):
    if q.options:
        raise ValueError("Essay questions must not have options")

    if q.correct:
        raise ValueError("Essay questions should not have correct answers")


def validate_file_upload(q: Question):
    if q.options:
        raise ValueError("File upload questions must not have options")

    if q.correct:
        raise ValueError("File upload questions should not have correct answers")


def validate_question(q: Question):
    qtype = q.type

    if qtype == "multiple choice":
        validate_mc(q)

    elif qtype == "short answer":
        validate_short_answer(q)

    elif qtype == "numerical":
        validate_numerical(q)

    elif qtype == "essay":
        validate_essay(q)

    elif qtype == "file upload":
        validate_file_upload(q)

    if not re.fullmatch(r"\d+(\.5)?", q.points):
        raise ValueError("Question point values must be positive integers or half-integers")


def validate_settings(s: Settings):
    if s.cant_go_back and not s.one_question_at_a_time:
        raise ValueError("Can't go can only be set if one question at a time is also enabled")


def excel_to_json(input_path: str):
    df = pd.read_excel(input_path, dtype=str, engine="openpyxl");

    questions = []

    for _, row in df.iterrows():
        if row["Question Text"]:
            q = normalize_row(row)
            validate_question(q)
            questions.append(q)

    return Quiz(
        title=input_path.split("/")[-1].replace(".xlsx", ""),
        questions=questions,
        settings=[]
    )


def render_feedback(feedback):
    out = []

    if feedback.general:
        out.append(f"... {feedback.general}")

    if feedback.correct:
        out.append(f"+   {feedback.correct}")

    if feedback.incorrect:
        out.append(f"-   {feedback.incorrect}")

    return out


def render_multiple_choice(q, index):
    out = [f"Points: {q.points}", f"{index}.  {q.text}"]

    feedback = render_feedback(q.feedback)

    if feedback:
        out.extend(feedback)

    correct = set(ans.strip() for ans in q.correct)

    for idx, option in enumerate(q.options, start=1):
        letter = chr(96 + idx)

        if str(idx) in correct:
            out.append(f"*{letter}) {option}")
        else:
            out.append(f"{letter})  {option}")

    return out


def render_multiple_answer(q, index):
    out = [f"Points: {q.points}", f"{index}.  {q.text}"]

    feedback = render_feedback(q.feedback)

    if feedback:
        out.extend(feedback)

    correct = set(ans.strip() for ans in q.correct)

    for idx, option in enumerate(q.options, start=1):

        if str(idx) in correct:
            out.append(f"[*] {option}")
        else:
            out.append(f"[ ] {option}")

    return out


def render_short_answer(q, index):
    out = [f"Points: {q.points}", f"{index}.  {q.text}"]

    feedback = render_feedback(q.feedback)

    if feedback:
        out.extend(feedback)

    for answer in q.correct:
        out.append(f"*   {answer.strip()}")

    return out


def render_numerical(q, index):
    out = [f"Points: {q.points}", f"{index}.  {q.text}"]

    feedback = render_feedback(q.feedback)

    if feedback:
        out.extend(feedback)

    for answer in q.correct:
        out.append(f"=   {answer.strip()}")

    return out


def render_essay(q, index):
    out = [f"Points: {q.points}", f"{index}.  {q.text}"]

    feedback = render_feedback(q.feedback)

    if feedback:
        out.extend(feedback)

    out.append("____")

    return out


def render_upload(q, index):
    out = [f"Points: {q.points}", f"{index}.  {q.text}"]

    feedback = render_feedback(q.feedback)

    if feedback:
        out.extend(feedback)

    out.append("^^^^")

    return out


def render_quiz(quiz: Quiz):
    out = [f"Quiz title: {quiz.title}"]

    for idx, q in enumerate(quiz.questions, start=1):
        qtype = q.type

        if qtype == "multiple choice" and len(q.correct) > 1:
            out.extend(render_multiple_answer(q, idx))

        elif qtype == "multiple choice" and len(q.correct) == 1:
            out.extend(render_multiple_choice(q, idx))

        elif qtype == "short answer":
            out.extend(render_short_answer(q, idx))

        elif qtype == "numerical":
            out.extend(render_numerical(q, idx))

        elif qtype == "essay":
            out.extend(render_essay(q, idx))

        elif qtype == "file upload":
            out.extend(render_upload(q, idx))

    return "\n".join(out)


def export_markdown(quiz, output_path):
    md = render_quiz(quiz)

    with open(output_path, "w", encoding="utf-8") as f:
        f.write(md)

    return output_path


def flexiquiz_response_summary_to_markdown(input_file):
    df = pd.read_excel(input_file, header=None)

    lines = []

    for _, row in df.iterrows():
        a, b = row[0], row[1]  # extract first 2 column values
        print(a, b)
