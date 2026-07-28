# ============================================
# AI-Interview-Agent 一键打包脚本
# 双击运行：自动生成 ai-interview_时间戳.zip 到桌面
# ============================================

function Write-Step($msg) { Write-Host "`n▶ $msg" -ForegroundColor Cyan }
function Write-OK($msg)    { Write-Host "  ✅ $msg" -ForegroundColor Green }
function Write-Err($msg)   { Write-Host "  ❌ $msg" -ForegroundColor Red }

# 0. 错误处理：捕获所有未处理的异常并详细输出
trap {
    Write-Host "`n❌ 未捕获的异常:" -ForegroundColor Red
    Write-Host "  类型: $($_.Exception.GetType().FullName)" -ForegroundColor Yellow
    Write-Host "  消息: $($_.Exception.Message)" -ForegroundColor Yellow
    Write-Host "  堆栈: $($_.ScriptStackTrace)" -ForegroundColor Gray
    pause
    exit 1
}

# 1. 定位项目根目录（脚本在 deploy/ 下，往上一级）
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectRoot = Split-Path -Parent $ScriptDir
Set-Location $ProjectRoot
Write-OK "项目根目录: $ProjectRoot"

# 2. 生成带时间戳的 zip（避免覆盖旧版本）
$Timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$ZipName = "ai-interview_$Timestamp.zip"
$DesktopPath = [Environment]::GetFolderPath("Desktop")
$ZipPath = Join-Path $DesktopPath $ZipName
Write-Step "开始打包 → $ZipName"

# 3. 执行打包（排除常见杂物）
try {
    Compress-Archive -Path "$ProjectRoot\*" `
        -DestinationPath $ZipPath `
        -Exclude @(
            "__pycache__",
            ".git",
            "*.log",
            "_*.py",
            ".env",
            "flask.err",
            "flask.log",
            "smoke_*.png",
            "check_cands.png"
        )
    Write-OK "打包完成: $ZipPath"
    Write-OK "文件大小: $((Get-Item $ZipPath).Length / 1KB) KB"
}
catch {
    Write-Err "打包失败: $_"
    pause
    exit 1
}

# 4. 在项目根目录也存一份（备份）
$LocalBackup = Join-Path $ProjectRoot "deploy_lastest.zip"
Copy-Item $ZipPath $LocalBackup -Force
Write-OK "项目内备份: deploy_lastest.zip"

# 5. 提示后续步骤
Write-Step "接下来你要做的："
Write-Host "  1. 打开 Xftp，连上服务器" -ForegroundColor Yellow
Write-Host "  2. 把桌面上的 $ZipName 拖到服务器的 /home/steve/ 目录" -ForegroundColor Yellow
Write-Host "  3. Xshell 跑解压和重启命令（见手册）" -ForegroundColor Yellow

# 6. 自动弹出文件夹
Start-Process explorer.exe "/select,$ZipPath"

Write-Host "`n=========================================" -ForegroundColor Green
Write-Host "  🎉 打包完成！" -ForegroundColor Green
Write-Host "=========================================`n" -ForegroundColor Green

pause