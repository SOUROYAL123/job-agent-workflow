<#
  setup-lightsail-mumbai.ps1
  Creates a Lightsail server in Mumbai that clones your private GitHub repo
  and runs your script at 9:00 and 17:00 IST. Run from Windows PowerShell.

  Needs: AWS CLI v2 installed and configured (aws configure).
  Run:   powershell -ExecutionPolicy Bypass -File .\setup-lightsail-mumbai.ps1
#>

# ============ EDIT THESE ============
$Region        = "ap-south-1"                      # Mumbai
$AZ            = "ap-south-1a"
$InstanceName  = "job-agent"
$RepoOwner     = "SOUROYAL123"
$RepoName      = "job-agent-workflow"
$ScriptFile    = "YOUR_SCRIPT.py"                  # main script in the repo
$OldInstance   = "job-alert"
$OldRegion     = "ap-southeast-2"                  # Sydney
$MinRamGB      = 1
# ====================================

$ErrorActionPreference = "Stop"

# --- 1. Check AWS CLI ---
if (-not (Get-Command aws -ErrorAction SilentlyContinue)) {
    Write-Host "AWS CLI not found. Install from https://aws.amazon.com/cli/ then run 'aws configure'." -ForegroundColor Red
    exit 1
}
aws sts get-caller-identity --output text | Out-Null
if ($LASTEXITCODE -ne 0) { Write-Host "Run 'aws configure' first." -ForegroundColor Red; exit 1 }

if ($ScriptFile -eq "YOUR_SCRIPT.py") {
    $ScriptFile = Read-Host "Main script file name in the repo (e.g. main.py)"
}

# --- 2. GitHub token (read-only, fine-grained, this repo only) ---
$sec   = Read-Host "Paste GitHub token (hidden)" -AsSecureString
$bstr  = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($sec)
$Token = [Runtime.InteropServices.Marshal]::PtrToStringAuto($bstr)
[Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
if ([string]::IsNullOrWhiteSpace($Token)) { Write-Host "Token is empty." -ForegroundColor Red; exit 1 }

# --- 3. Optionally delete the Sydney instance ---
if ($OldInstance -ne "") {
    $ans = Read-Host "Delete '$OldInstance' in Sydney? This cannot be undone (y/N)"
    if ($ans -eq "y") {
        aws lightsail delete-instance --instance-name $OldInstance --region $OldRegion
        Write-Host "Sydney instance deleted." -ForegroundColor Green
    }
}

# --- 4. Pick the cheapest IPv4-capable Linux bundle ---
Write-Host "Finding cheapest bundle in Mumbai..."
$bundles = aws lightsail get-bundles --region $Region --no-include-inactive-bundles --output json | ConvertFrom-Json
$pick = $bundles.bundles |
    Where-Object { $_.supportedPlatforms -contains "LINUX_UNIX" -and
                   $_.bundleId -notmatch "ipv6" -and
                   $_.ramSizeInGb -ge $MinRamGB } |
    Sort-Object price | Select-Object -First 1
if (-not $pick) { Write-Host "No bundle found." -ForegroundColor Red; exit 1 }
Write-Host ("Using bundle {0}: {1} GB RAM, ${2}/month" -f $pick.bundleId, $pick.ramSizeInGb, $pick.price)

# --- 5. Server first-boot script (runs once, as root) ---
$userData = @'
#!/bin/bash
exec > /var/log/job-setup.log 2>&1
set -x
timedatectl set-timezone Asia/Kolkata
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y git python3 python3-pip python3-venv cron

# 1 GB swap so small servers do not run out of memory
if [ ! -f /swapfile ]; then
  fallocate -l 1G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

sudo -u ubuntu bash <<'INNER'
cd /home/ubuntu
git config --global credential.helper store
echo "https://__OWNER__:__TOKEN__@github.com" > ~/.git-credentials
chmod 600 ~/.git-credentials
git clone https://github.com/__OWNER__/__REPO__.git
cd __REPO__
python3 -m venv venv
if [ -f requirements.txt ]; then venv/bin/pip install -r requirements.txt; fi
( echo "0 9,17 * * * cd /home/ubuntu/__REPO__ && git pull -q && /home/ubuntu/__REPO__/venv/bin/python __SCRIPT__ >> /home/ubuntu/job.log 2>&1" ) | crontab -
INNER
systemctl enable --now cron
echo SETUP_DONE
'@

$userData = $userData.Replace("__OWNER__", $RepoOwner).Replace("__REPO__", $RepoName).
                      Replace("__TOKEN__", $Token).Replace("__SCRIPT__", $ScriptFile)
$userData = $userData -replace "`r`n", "`n"
$udFile = Join-Path $env:TEMP "lightsail-userdata.sh"
[IO.File]::WriteAllText($udFile, $userData, (New-Object Text.UTF8Encoding $false))

# --- 6. Create the Mumbai instance ---
aws lightsail create-instances `
    --instance-names $InstanceName `
    --availability-zone $AZ `
    --blueprint-id ubuntu_22_04 `
    --bundle-id $pick.bundleId `
    --user-data ("file://" + $udFile.Replace("\", "/")) `
    --region $Region
if ($LASTEXITCODE -ne 0) { Write-Host "Create failed." -ForegroundColor Red; exit 1 }

Remove-Item $udFile -Force
$Token = $null

# --- 7. Wait until running ---
Write-Host "Waiting for the server to start..."
do {
    Start-Sleep -Seconds 10
    $state = aws lightsail get-instance-state --instance-name $InstanceName --region $Region --query "state.name" --output text
    Write-Host "  state: $state"
} while ($state -ne "running")

$ip = aws lightsail get-instance --instance-name $InstanceName --region $Region --query "instance.publicIpAddress" --output text

Write-Host ""
Write-Host "DONE. Server is running in Mumbai. IP: $ip" -ForegroundColor Green
Write-Host "Setup continues inside the server for 3-5 minutes (installing packages, cloning repo)."
Write-Host ""
Write-Host "To check:"
Write-Host "  1. Lightsail console -> Region Mumbai -> $InstanceName -> Connect using SSH"
Write-Host "  2. Run:  tail -n 20 /var/log/job-setup.log    (look for SETUP_DONE)"
Write-Host "  3. Run:  crontab -l                            (should show the 9,17 line)"
Write-Host "  4. Run:  date                                  (should show IST)"
Write-Host ""
Write-Host "IMPORTANT: put API keys in /home/ubuntu/$RepoName/.env on the server, not in GitHub."
