import pandas as pd
import subprocess
import os
import re
from text2qti.err import Text2qtiError
from text2qti.quiz import Quiz


def extract_text2qti_error(err: str) -> str:
    lines = err.splitlines()

    for i, line in enumerate(lines):
        if "text2qti.err.Text2qtiError: In" in line:
            print(f'line: {line}')
            match = re.search(r'In ".*/([^/]+)" on line (\d+):', line)

            filename = match.group(1) if match else ""
            line = match.group(2) if match else ""
            detail = lines[i+1].strip() if i+1 < len(lines) else ""

            return f'\n On line {line} of {filename}, \n {detail}'

    return f'Conversion Error: \n {err.strip()}'


def run_text2qti(input_path: str, workdir: str) -> str:
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
        raise Exception(f'TEXT2QTI ERROR:: {clean_error}')

    base = os.path.splitext(os.path.basename(input_path))[0]
    output_path = os.path.join(workdir, f'{base}.zip')

    if not os.path.exists(output_path):
        raise Exception("No output QTI.zip generated")

    return output_path


def flexiquiz_response_summary_to_markdown(input_file):
    df = pd.read_excel(input_file, header=None)

    lines = []

    for _, row in df.iterrows():
        a, b = row[0], row[1]  # extract first 2 column values
        print(a, b)
