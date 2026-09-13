# install-windows.ps1
# One-time bootstrap for Windows users.
# Installs WSL2 + Ubuntu if missing, then runs lecture-manager.sh inside Ubuntu.

$ErrorActionPreference = "Stop"
function Info  { Write-Host "[INFO] " -ForegroundColor Green  -NoNewline; Write-Host $args }
function Warn  { Write-Host "[WARN] " -ForegroundColor Yellow -NoNewline; Write-Host $args }
function Step  { Write-Host "`n=== $args ===" -ForegroundColor Cyan }

Write-Host @"

  📚  Lecture Manager — Windows Setup
  ------------------------------------
  This will check/install WSL2 + Ubuntu, then launch the app.

"@ -ForegroundColor Cyan

# --- Admin check ---
$pr = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $pr.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Warn "Please run in an ADMIN PowerShell (Win+X -> Terminal (Admin))."
    Read-Host "Press Enter to exit"; exit 1
}

# --- Windows version check (WSL2 needs Win10 build 19041+) ---
$v = [Environment]::OSVersion.Version
if ($v.Major -lt 10 -or ($v.Major -eq 10 -and $v.Build -lt 19041)) {
    Warn "Windows 10 build 19041 or newer required. Run Windows Update first."
    Read-Host "Press Enter"; exit 1
}
Info "Windows $($v.Major).$($v.Build) OK"

# --- Is WSL present? ---
Step "Checking WSL"
$hasWSL = $false
try { $null = wsl.exe --status 2>&1; if ($LASTEXITCODE -eq 0) { $hasWSL = $true } } catch {}

if (-not $hasWSL) {
    Warn "WSL is not installed. Installing WSL2 + Ubuntu now..."
    Write-Host "`n  One-time setup, takes 5-10 minutes.`n" -ForegroundColor Yellow
    wsl.exe --install -d Ubuntu
    Write-Host @"

  ✅ WSL installation started.
  Next steps:
    1. REBOOT your computer
    2. Open 'Ubuntu' from the Start menu once (choose a username/password)
    3. Re-run this same command:

         irm https://raw.githubusercontent.com/blee-design/lecture-manager/main/install-windows.ps1 | iex

"@ -ForegroundColor Green
    $r = Read-Host "Reboot now? (y/n)"
    if ($r -eq 'y') { Restart-Computer }
    exit 0
}
Info "WSL is installed"

# --- Is Ubuntu distro set up? ---
Step "Checking Ubuntu"
$distros = (wsl.exe -l -q 2>&1) | ForEach-Object { $_ -replace "`0","" } | Where-Object { $_ -and $_.Trim() }
if ($distros -notcontains "Ubuntu") {
    Warn "Ubuntu not found. Installing..."
    wsl.exe --install -d Ubuntu
    Write-Host "`n  Open Ubuntu from Start menu once, set user/pass, then re-run this script.`n" -ForegroundColor Green
    Read-Host "Press Enter"; exit 0
}
Info "Ubuntu is registered"

# --- Sanity check that Ubuntu responds ---
Step "Warming up Ubuntu (first run may take ~30s)"
$probe = wsl.exe -d Ubuntu -- bash -lc "echo READY" 2>&1
if ($probe -notmatch "READY") {
    Warn "Ubuntu is not responding. Open it from Start menu once, then re-run."
    Read-Host "Press Enter"; exit 1
}
Info "Ubuntu responsive"

# --- Run the Linux installer inside Ubuntu ---
Step "Running lecture-manager installer inside Ubuntu"
Write-Host "`n  (First run may take several minutes. Keep this window open.)`n" -ForegroundColor Yellow

$bash = @'
set -e
URL="https://raw.githubusercontent.com/blee-design/lecture-manager/main/lecture-manager.sh"
if [ ! -f "$HOME/lecture-manager.sh" ]; then
    curl -fsSL "$URL" -o "$HOME/lecture-manager.sh"
    chmod +x "$HOME/lecture-manager.sh"
fi
bash "$HOME/lecture-manager.sh"
'@

wsl.exe -d Ubuntu -- bash -lc $bash
