import os
import shutil
import tempfile
import re

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware

from services.converter import run_text2qti

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:1234"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.post("/convert-file")
async def convert_file(file: UploadFile = File(...)):
    file_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", file.filename)
    print(f" 🚀 Converting {file_name}")
    try:
        # validation
        if not file_name.endswith((".txt", ".md")):
            raise HTTPException(400, "Only .txt or .md files allowed.")

        tmpdir = tempfile.mkdtemp()
        input_path = os.path.join(tmpdir, file_name)

        print("INPUT PATH:", input_path)

        # save file
        with open(input_path, "wb") as f:
            shutil.copyfileobj(file.file, f)

        # convert to qti
        output_path = run_text2qti(input_path, tmpdir)
        print(f"Conversion Completed - {os.path.basename(output_path)}")

        # return qti.zip file as response
        background_tasks = BackgroundTasks()
        background_tasks.add_task(shutil.rmtree, tmpdir)

        return FileResponse(
            output_path,
            media_type="application/zip",
            filename=os.path.basename(output_path),
            background=background_tasks
        )

    except Exception as e:
        print("ERROR:", e)
        raise HTTPException(status_code=400, detail=str(e))
