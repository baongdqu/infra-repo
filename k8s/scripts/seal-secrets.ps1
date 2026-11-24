param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet("backup-key", "restore-key", "seal")]
    [string]$Action
)

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Resolve-Path (Join-Path $ScriptDir "..\..")
$BackupDir = Join-Path $HOME ".sealed-secrets-backup"
$KeyFile = Join-Path $BackupDir "master-key.yaml"
$EnvSecretsFile = Join-Path $ScriptDir ".env.secrets"

function Backup-MasterKey {
    New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
    Write-Host "[+] Dang sao luu Sealed Secrets master key ra $KeyFile ..."
    kubectl get secret -n sealed-secrets -l sealedsecrets.bitnami.com/sealed-secrets-key -o yaml | Set-Content -Path $KeyFile -Encoding UTF8
    if ($LASTEXITCODE -ne 0) { throw "Khong lay duoc master key tu namespace sealed-secrets." }
    Write-Host "[OK] Da sao luu master key. Giu file nay o may ca nhan (ngoai Git)!"
}

function Restore-MasterKey {
    if (-not (Test-Path $KeyFile)) {
        throw "Khong tim thay file backup tai $KeyFile. Hay chay 'backup-key' truoc khi destroy cluster!"
    }
    Write-Host "[+] Khoi phuc master key TRUOC KHI apply argocd/root-app.yaml ..."
    kubectl create namespace sealed-secrets --dry-run=client -o yaml | kubectl apply -f -
    kubectl apply -f $KeyFile
    $deploy = kubectl get deployment sealed-secrets -n sealed-secrets --ignore-not-found -o name
    if ($deploy) {
        kubectl rollout restart deployment/sealed-secrets -n sealed-secrets
        kubectl rollout status deployment/sealed-secrets -n sealed-secrets --timeout=90s
    }
    Write-Host "[OK] Master key da san sang trong namespace sealed-secrets."
}

function New-SealedSecrets {
    if (-not (Get-Command kubeseal -ErrorAction SilentlyContinue)) {
        throw "Khong tim thay CLI 'kubeseal'. Vui long cai dat kubeseal truoc khi chay lenh 'seal'."
    }
    if (-not (Test-Path $EnvSecretsFile)) {
        throw "Khong tim thay $EnvSecretsFile. Hay copy tu .env.secrets.example va dien mat khau that."
    }

    $vars = @{}
    Get-Content $EnvSecretsFile | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line -split "=", 2
            $vars[$parts[0].Trim()] = $parts[1].Trim()
        }
    }

    $envs = @(
        @{
            Namespace = "dev"
            User      = $vars["DEV_POSTGRES_USER"]
            Pass      = $vars["DEV_POSTGRES_PASSWORD"]
            Db        = $vars["DEV_POSTGRES_DB"]
            OutFile   = Join-Path $RepoRoot "k8s\overlays\dev\sealed-secret.yaml"
        },
        @{
            Namespace = "production"
            User      = $vars["PROD_POSTGRES_USER"]
            Pass      = $vars["PROD_POSTGRES_PASSWORD"]
            Db        = $vars["PROD_POSTGRES_DB"]
            OutFile   = Join-Path $RepoRoot "k8s\overlays\production\sealed-secret.yaml"
        }
    )

    foreach ($e in $envs) {
        $dbUrl = "postgresql://$($e.User):$($e.Pass)@postgres:5432/$($e.Db)"
        Write-Host "[+] Dang ma hoa app-secrets cho namespace '$($e.Namespace)' -> $($e.OutFile) ..."
        kubectl create secret generic app-secrets `
            --namespace $e.Namespace `
            --from-literal=POSTGRES_USER="$($e.User)" `
            --from-literal=POSTGRES_PASSWORD="$($e.Pass)" `
            --from-literal=POSTGRES_DB="$($e.Db)" `
            --from-literal=DATABASE_URL="$dbUrl" `
            --dry-run=client -o yaml |
        kubeseal --controller-name=sealed-secrets --controller-namespace=sealed-secrets --format yaml |
        Set-Content -Path $e.OutFile -Encoding UTF8
        if ($LASTEXITCODE -ne 0) { throw "Loi khi ma hoa SealedSecret cho $($e.Namespace)." }
    }

    Write-Host "[OK] Hoan tat! Nho bo comment '- sealed-secret.yaml' trong kustomization.yaml cua dev va production."
}

switch ($Action) {
    "backup-key"  { Backup-MasterKey }
    "restore-key" { Restore-MasterKey }
    "seal"        { New-SealedSecrets }
}
