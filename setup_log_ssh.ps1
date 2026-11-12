# Setup SSH Key untuk Windows (PowerShell)
# Menyiapkan autentikasi SSH key otomatis ke server VPS agar upload log berjalan tanpa password.
param(
    [string]$VpsHost = "217.216.146.15",
    [int]$VpsPort = 20157,
    [string]$VpsUser = "root",
    [string]$RemoteDir = "/root/log_testing"
)

$ErrorActionPreference = "Stop"

$sshDir = Join-Path $HOME ".ssh"
if (-not (Test-Path $sshDir)) {
    New-Item -ItemType Directory -Path $sshDir -Force | Out-Null
}

$keyEd = Join-Path $sshDir "id_ed25519"
$keyRsa = Join-Path $sshDir "id_rsa"
$pubKey = $null

if (-not (Test-Path $keyEd) -and -not (Test-Path $keyRsa)) {
    Write-Host "[1/3] Membuat SSH key baru: $keyEd" -ForegroundColor Cyan
    $hostname = $env:COMPUTERNAME
    ssh-keygen -t ed25519 -N '""' -C "arcade-$hostname" -f "$keyEd"
    $pubKey = "$keyEd.pub"
} elseif (Test-Path "$keyEd.pub") {
    Write-Host "[1/3] SSH key sudah ada: $keyEd" -ForegroundColor Green
    $pubKey = "$keyEd.pub"
} elseif (Test-Path "$keyRsa.pub") {
    Write-Host "[1/3] SSH key sudah ada: $keyRsa" -ForegroundColor Green
    $pubKey = "$keyRsa.pub"
}

if (-not $pubKey -or -not (Test-Path $pubKey)) {
    Write-Error "Public key tidak ditemukan di $sshDir"
    exit 1
}

$pubKeyContent = (Get-Content $pubKey -Raw).Trim()

Write-Host "[2/3] Mendaftarkan public key ke $VpsUser@$VpsHost`:$VpsPort (masukkan password VPS sekali)..." -ForegroundColor Yellow

$remoteCmd = "mkdir -p ~/.ssh '$RemoteDir' && chmod 700 ~/.ssh && touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys && grep -qxF '$pubKeyContent' ~/.ssh/authorized_keys || echo '$pubKeyContent' >> ~/.ssh/authorized_keys"

ssh -p $VpsPort -o StrictHostKeyChecking=accept-new "$VpsUser@$VpsHost" $remoteCmd

Write-Host "[3/3] Menguji login tanpa password..." -ForegroundColor Cyan
$testResult = ssh -p $VpsPort -o BatchMode=yes "$VpsUser@$VpsHost" "test -d '$RemoteDir' && echo OK"

if ($testResult -match "OK") {
    Write-Host "`n[✓] Berhasil! Komputer Windows ini siap mengirim log otomatis ke VPS ($RemoteDir)" -ForegroundColor Green
} else {
    Write-Host "`n[X] Login tanpa password gagal. Periksa kembali koneksi atau izin di VPS." -ForegroundColor Red
    exit 1
}

