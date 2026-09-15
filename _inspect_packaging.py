import zipfile
from pathlib import Path

root=Path(r"c:/dev/NutriFAQ/nutrifaq-chat")
zip_path=Path(r"c:/dev/NutriFAQ/nutrifaq-chat/_debug_package.zip")
include={"app.py","__init__.py","requirements.txt","startup.sh"}
include_dirs={"api","static","templates"}
exclude={".git",".venv","__pycache__",".pytest_cache",".azure",".vs",".vscode",".firebase","node_modules","knowledge-base","public","doc","build-backend.bat","build-database.bat","deploy-backend.bat","deploy-frontend.bat","deploy-gcp-backend.bat","deploy-gcp-frontend.bat","index-database.bat","question_log.json","app.zip"}

if zip_path.exists():
    zip_path.unlink()

with zipfile.ZipFile(zip_path,'w',compression=zipfile.ZIP_DEFLATED) as zf:
    for entry in root.iterdir():
        if entry.name in exclude:
            continue
        if entry.name in include or (entry.is_dir() and entry.name in include_dirs):
            if entry.is_dir():
                for path in sorted(entry.rglob('*')):
                    if path.is_file() and not any(part in exclude for part in path.relative_to(root).parts):
                        zf.write(path, arcname=path.relative_to(root).as_posix())
            else:
                zf.write(entry, arcname=entry.name)

with zipfile.ZipFile(zip_path,'r') as zf:
    names=zf.namelist()
    print('has_app_py=', 'app.py' in names)
    print('has_requirements=', 'requirements.txt' in names)
    print('top_level_unique=', sorted({n.split('/')[0] for n in names})[:30])
