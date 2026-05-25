import os
import shutil
import tempfile
import re

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import Response, JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from services.converter import run_text2qti, excel_to_json, export_markdown

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:1234"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/convert-file")
async def convert_file(file: UploadFile = File(...), background_tasks: BackgroundTasks = BackgroundTasks()):
    file_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", file.filename)
    print(f" 🚀 Converting {file_name}")

    # validation
    if not file_name.endswith((".txt", ".md", ".xlsx")):
        raise HTTPException(400, "Only .xlsx, .txt, or .md files allowed.")

    tmpdir = tempfile.mkdtemp()

    try:
        input_path = os.path.join(tmpdir, file_name)

        # save file
        with open(input_path, "wb") as f:
            shutil.copyfileobj(file.file, f, length=1024 * 1024)

        if file_name.endswith(".xlsx"):
            # convert xlsx to json
            quiz_json = excel_to_json(input_path)

            # convert json to md
            input_path = export_markdown(quiz_json, tmpdir)

        output_path = await run_text2qti(input_path, tmpdir)

        with open(output_path, "rb") as f:
            zip_data = f.read()

        background_tasks.add_task(shutil.rmtree, tmpdir)

        return Response(
            content=zip_data,
            media_type="application/zip",
            headers={
                "Content-Disposition": f"attachment; filename={os.path.basename(output_path)}"
            }
        )

    except Exception as e:
        shutil.rmtree(tmpdir, ignore_errors=True)
        detail = e.args[0] if isinstance(e.args[0], dict) else str(e)
        return JSONResponse(
            status_code=400,
            content=detail
        )


def main():
    q = excel_to_json("../input/test.xlsx")
    export_markdown(q, "../output")


if __name__ == "__main__":
    main()
