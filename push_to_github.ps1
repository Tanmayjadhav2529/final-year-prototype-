# Check if git is installed
$gitInstalled = Get-Command git -ErrorAction SilentlyContinue
if (-not $gitInstalled) {
    Write-Host "Git is not detected in your PATH. Installing Git via winget..." -ForegroundColor Yellow
    winget install --id Git.Git -e --source winget
    Write-Host "`n[Action Required] Git installation has started. Once it completes, please RESTART VS Code or your terminal so the PATH is updated, and then run this script again." -ForegroundColor Green
    Exit
}

# Initialize repository
if (-not (Test-Path .git)) {
    Write-Host "Initializing local Git repository..." -ForegroundColor Cyan
    git init
}

# Add files
Write-Host "Staging files..." -ForegroundColor Cyan
git add .

# Initial commit
Write-Host "Creating commit..." -ForegroundColor Cyan
git commit -m "Initial commit of real-time metal surface inspection system with dual-loop concurrency and manual upload support"

# Configure Remote URL
Write-Host "Setting remote origin..." -ForegroundColor Cyan
$remotes = git remote
if ($remotes -contains "origin") {
    git remote set-url origin https://github.com/Tanmayjadhav2529/final-year-prototype-.git
} else {
    git remote add origin https://github.com/Tanmayjadhav2529/final-year-prototype-.git
}

# Rename branch and push
Write-Host "`nPushing code to GitHub..." -ForegroundColor Cyan
Write-Host "A browser window or popup will open for you to securely authenticate with GitHub." -ForegroundColor Yellow
git branch -M main
git push -u origin main

Write-Host "`nDone! Your project is now on GitHub." -ForegroundColor Green
