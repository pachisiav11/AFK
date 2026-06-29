param(
  [switch]$SkipModels,
  [switch]$SkipLlama
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$Python = Join-Path $RepoRoot "python\.venv\Scripts\python.exe"
$HfCli = Join-Path $RepoRoot "python\.venv\Scripts\hf.exe"
$ClarifyDir = Join-Path $RepoRoot "models\clarify"
$LlamaDir = Join-Path $RepoRoot "vendor\llama.cpp"
$LlamaBinDir = Join-Path $LlamaDir "llama-bin"

if (!(Test-Path $Python)) {
  throw "Python venv not found. Run 'npm run setup:python' first."
}

New-Item -ItemType Directory -Force -Path $ClarifyDir | Out-Null
New-Item -ItemType Directory -Force -Path $LlamaDir | Out-Null

& $Python -m pip install -U huggingface_hub

if (!(Test-Path $HfCli)) {
  throw "hf.exe was not installed into the Python venv."
}

if (!$SkipModels) {
  Write-Host "Downloading official GGUF Clarify models..."
  & $HfCli download ggml-org/gemma-3-270m-GGUF --include gemma-3-270m-Q8_0.gguf --local-dir $ClarifyDir
  & $HfCli download ggml-org/gemma-4-E2B-it-GGUF --include gemma-4-E2B-it-Q8_0.gguf --local-dir $ClarifyDir
}

if (!$SkipLlama) {
  Write-Host "Downloading official llama.cpp Windows CPU build..."
  $release = Invoke-RestMethod -Uri "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
  $asset = $release.assets |
    Where-Object { $_.name -match "bin-win-cpu-x64\.zip$" -or $_.name -match "bin-win-avx2-x64\.zip$" } |
    Select-Object -First 1

  if ($null -eq $asset) {
    throw "Could not find a llama.cpp Windows CPU x64 release asset."
  }

  $zipPath = Join-Path $LlamaDir $asset.name
  Invoke-WebRequest -Uri $asset.browser_download_url -OutFile $zipPath

  if (Test-Path $LlamaBinDir) {
    Remove-Item $LlamaBinDir -Recurse -Force
  }
  Expand-Archive $zipPath $LlamaBinDir -Force

  $server = Get-ChildItem $LlamaBinDir -Recurse -Filter "llama-server.exe" |
    Select-Object -First 1
  if ($null -eq $server) {
    throw "Downloaded llama.cpp archive did not contain llama-server.exe."
  }

  Copy-Item (Join-Path $server.Directory.FullName "*") $LlamaDir -Recurse -Force
  Remove-Item $LlamaBinDir -Recurse -Force -ErrorAction SilentlyContinue
  Remove-Item $zipPath -Force -ErrorAction SilentlyContinue
}

Write-Host ""
Write-Host "Clarify setup complete."
Write-Host "Models:"
Get-ChildItem $ClarifyDir -Filter "*.gguf" | Select-Object Name,Length | Format-Table -AutoSize
Write-Host "llama-server:"
$LlamaServer = Join-Path $LlamaDir "llama-server.exe"
if (Test-Path $LlamaServer) {
  Get-Item $LlamaServer | Select-Object FullName,Length | Format-Table -AutoSize
} else {
  Write-Host "Not installed. Run again without -SkipLlama."
}
