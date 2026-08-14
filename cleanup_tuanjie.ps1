# ============================================================
# 团结引擎残留清理脚本 (UTF-8 BOM)
# ============================================================
# 用法: 管理员 PowerShell 运行
#   powershell -ExecutionPolicy Bypass -File ".\cleanup.ps1"
# ============================================================

# 检查管理员权限
$isAdmin = ([Security.Principal.WindowsPrincipal] [Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $isAdmin) {
    Write-Host "========================================" -ForegroundColor Red
    Write-Host "  ERROR: Need administrator privileges!" -ForegroundColor Red
    Write-Host "========================================" -ForegroundColor Red
    Write-Host ""
    Write-Host "Run as Administrator: Win + X -> Windows PowerShell (Admin)" -ForegroundColor Yellow
    pause
    exit
}

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Tuanjie Cleanup - Preview" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Targets (all Tuanjie-related, safe to delete)
$targets = @(
    @{ Path = "D:\unity"; Desc = "Tuanjie fork Unity leftover" },
    @{ Path = "C:\Program Files\Tuanjie"; Desc = "Tuanjie 1.10.0 install dir" },
    @{ Path = "C:\Program Files (x86)\Tuanjie"; Desc = "Tuanjie 1.10.0 (x86)" },
    @{ Path = "C:\Users\Teio\AppData\Roaming\Tuanjie"; Desc = "Tuanjie config" },
    @{ Path = "C:\Users\Teio\AppData\Local\Tuanjie"; Desc = "Tuanjie cache" },
    @{ Path = "C:\Users\Teio\AppData\LocalLow\Tuanjie"; Desc = "Tuanjie low cache" },
    @{ Path = "C:\Users\Teio\AppData\Local\Tuanjie Cowork"; Desc = "Cowork cache" },
    @{ Path = "C:\Users\Teio\AppData\Roaming\Tuanjie Cowork"; Desc = "Cowork config" }
)

$totalSize = 0
$totalFiles = 0
$existingTargets = @()

foreach ($t in $targets) {
    if (Test-Path $t.Path) {
        $size = (Get-ChildItem -Path $t.Path -Recurse -File -ErrorAction SilentlyContinue | Measure-Object -Property Length -Sum).Sum
        $count = (Get-ChildItem -Path $t.Path -Recurse -File -ErrorAction SilentlyContinue | Measure-Object).Count

        $sizeMB = [math]::Round($size / 1MB, 1)
        Write-Host ("  [X] {0,10} MB  {1,7} files  {2}" -f $sizeMB, $count, $t.Path) -ForegroundColor Red
        Write-Host ("         {0}" -f $t.Desc) -ForegroundColor Gray

        $totalSize += $size
        $totalFiles += $count
        $existingTargets += $t
    }
}

Write-Host ""
Write-Host "  [OK] Protected: Unity International (12.5GB) + Project files" -ForegroundColor Green
Write-Host ""
Write-Host "  ============================================" -ForegroundColor Cyan
Write-Host ("  Total to delete: {0} MB ({1} files / {2} dirs)" -f [math]::Round($totalSize/1MB,1), $totalFiles, $existingTargets.Count) -ForegroundColor Yellow
Write-Host "  ============================================" -ForegroundColor Cyan
Write-Host ""

if ($existingTargets.Count -eq 0) {
    Write-Host "  No leftover found. Nothing to do." -ForegroundColor Green
    pause
    exit
}

# User confirmation
$confirm = Read-Host "  Confirm delete all above? Type y to execute (anything else = cancel)"
if ($confirm -ne 'y') {
    Write-Host ""
    Write-Host "  Cancelled. Nothing deleted." -ForegroundColor Yellow
    pause
    exit
}

# Execute deletion
Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "  Cleaning..." -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$successCount = 0
$failCount = 0

foreach ($t in $existingTargets) {
    Write-Host ("  Cleaning: {0}" -f $t.Path) -ForegroundColor Yellow
    try {
        Remove-Item -Path $t.Path -Recurse -Force -ErrorAction Stop
        Write-Host "    [OK] Deleted" -ForegroundColor Green
        $successCount++
    } catch {
        Write-Host ("    [FAIL] {0}" -f $_.Exception.Message) -ForegroundColor Red
        $failCount++
    }
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ("  Cleanup complete: success {0}, failed {1}" -f $successCount, $failCount) -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Reminder: manually delete any Tuanjie desktop shortcuts" -ForegroundColor Gray
Write-Host ""
pause
