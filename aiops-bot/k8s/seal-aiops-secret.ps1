param(
    [Parameter(Mandatory = $true)]
    [string]$GeminiApiKey,
    [Parameter(Mandatory = $false)]
    [string]$TelegramBotToken = "",
    [Parameter(Mandatory = $false)]
    [string]$TelegramChatId = "",
    [Parameter(Mandatory = $false)]
    [string]$DiscordWebhookUrl = ""
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$OutFile = Join-Path $ScriptDir "sealed-secret.yaml"

if (-not (Get-Command kubeseal -ErrorAction SilentlyContinue)) {
    throw "CLI 'kubeseal' not found. Please install kubeseal before sealing aiops-bot-secrets."
}

Write-Host "[+] Sealing aiops-bot-secrets for namespace 'aiops' -> $OutFile ..."
kubectl create secret generic aiops-bot-secrets `
    --namespace aiops `
    --from-literal=GEMINI_API_KEY="$GeminiApiKey" `
    --from-literal=TELEGRAM_BOT_TOKEN="$TelegramBotToken" `
    --from-literal=TELEGRAM_CHAT_ID="$TelegramChatId" `
    --from-literal=DISCORD_WEBHOOK_URL="$DiscordWebhookUrl" `
    --dry-run=client -o yaml |
kubeseal --controller-name=sealed-secrets --controller-namespace=sealed-secrets --format yaml |
Set-Content -Path $OutFile -Encoding UTF8

if ($LASTEXITCODE -ne 0) { throw "Failed to seal aiops-bot-secrets." }
Write-Host "[OK] Created $OutFile! Uncomment '- sealed-secret.yaml' in k8s/kustomization.yaml."
