# Run this yourself in a PowerShell terminal: .\scripts\set_api_key.ps1
# It prompts you to paste your Anthropic API key with masked input (never echoed,
# never sent anywhere), then stores it as a persistent Windows user environment
# variable. It only ever reports the stored value's LENGTH back to you, never
# the value itself, so you can sanity-check it (a real key is 100+ characters,
# starting with sk-ant-api03-).

$secure = Read-Host "Paste your ANTHROPIC_API_KEY (input is hidden)" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}

$plain = $plain.Trim()

if ($plain.Length -lt 40) {
    Write-Host ""
    Write-Host "WARNING: that is only $($plain.Length) characters. A real Anthropic key" -ForegroundColor Yellow
    Write-Host "is normally 100+ characters and starts with sk-ant-api03-. This looks" -ForegroundColor Yellow
    Write-Host "too short -- it was NOT saved. Copy the full key from console.anthropic.com" -ForegroundColor Yellow
    Write-Host "(select the whole string) and run this script again." -ForegroundColor Yellow
    exit 1
}

[Environment]::SetEnvironmentVariable("ANTHROPIC_API_KEY", $plain, "User")
$plain = $null
[GC]::Collect()

$check = [Environment]::GetEnvironmentVariable("ANTHROPIC_API_KEY", "User")
Write-Host ""
Write-Host "Saved. Stored value length: $($check.Length) characters." -ForegroundColor Green
Write-Host "Now SIGN OUT of Windows and back in (or reboot) so new processes pick it up." -ForegroundColor Green
