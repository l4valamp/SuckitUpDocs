Write-Host "Generating MkDocs files..." -ForegroundColor Cyan

python scripts\generate_mkdocs.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "Generation failed." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "Starting MkDocs..." -ForegroundColor Green

mkdocs serve
