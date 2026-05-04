param(
  [string]$RunnerHome = "$env:USERPROFILE\\dashgithub-runner",
  [string]$ConfigPath = "$env:ProgramData\\dashgithub-runner\\config.yaml",
  [int]$Port = 8444
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $RunnerHome | Out-Null
New-Item -ItemType Directory -Force -Path ([System.IO.Path]::GetDirectoryName($ConfigPath)) | Out-Null

Copy-Item -Recurse -Force "$PSScriptRoot\\..\\*" $RunnerHome

py -3 -m venv "$RunnerHome\\.venv"
& "$RunnerHome\\.venv\\Scripts\\python.exe" -m pip install --upgrade pip
& "$RunnerHome\\.venv\\Scripts\\python.exe" -m pip install -r "$RunnerHome\\requirements.txt"

if (-not (Test-Path $ConfigPath)) {
  Copy-Item "$RunnerHome\\config.example.yaml" $ConfigPath
}

(Get-Content $ConfigPath) \
  -replace '^host:.*$', 'host: 0.0.0.0' \
  -replace '^port:.*$', "port: $Port" | Set-Content $ConfigPath

Write-Host "Runner files installed to $RunnerHome"
Write-Host "Config path: $ConfigPath"
Write-Host "Start command: $RunnerHome\\.venv\\Scripts\\python.exe $RunnerHome\\run.py"
Write-Host "Create a Windows service or scheduled task around that command if you need persistence."
