Write-Host "Generating MkDocs files..." -ForegroundColor Cyan

python scripts\generate_mkdocs.py

if ($LASTEXITCODE -ne 0) {
    Write-Host "Generation failed." -ForegroundColor Red
    exit $LASTEXITCODE
}

Write-Host "MkDocs source generated successfully." -ForegroundColor Green

if ($args -contains "build") {

    Write-Host "Building MkDocs site..." -ForegroundColor Cyan

    mkdocs build

    if ($LASTEXITCODE -ne 0) {
        Write-Host "MkDocs build failed." -ForegroundColor Red
        exit $LASTEXITCODE
    }

    Write-Host "MkDocs build complete." -ForegroundColor Green

}
else {

    Write-Host "Starting MkDocs development server..." -ForegroundColor Green

    mkdocs serve
}
