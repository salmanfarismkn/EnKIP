param(
    [string]$BaseUrl = "http://127.0.0.1:8000",
    [string]$ComposeFile = "infrastructure/docker/compose.production.yml",
    [string]$ProjectName = ""
)

$ErrorActionPreference = "Stop"

$composeProject = @()
if ($ProjectName) {
    $composeProject = @("-p", $ProjectName)
}

docker compose @composeProject -f $ComposeFile ps

$live = Invoke-RestMethod -Uri "$BaseUrl/live" -Method Get -TimeoutSec 5
if ($live.status -ne "ok") {
    throw "Liveness check did not return ok"
}

try {
    $ready = Invoke-RestMethod -Uri "$BaseUrl/ready" -Method Get -TimeoutSec 5
    if ($ready.status -ne "ready") {
        throw "Readiness check did not return ready"
    }
}
catch {
    throw "Readiness endpoint failed; verify PostgreSQL and migration service status"
}

$postgresUser = $env:POSTGRES_USER
$postgresDatabase = $env:POSTGRES_DB
if (-not $postgresUser -or -not $postgresDatabase) {
    throw "POSTGRES_USER and POSTGRES_DB must be set for isolated deployment acceptance"
}

$migration = docker compose @composeProject -f $ComposeFile exec -T postgres `
    psql -U $postgresUser -d $postgresDatabase -tAc "SELECT version_num FROM alembic_version"
if ($LASTEXITCODE -ne 0 -or -not $migration.Trim()) {
    throw "Migration revision could not be read from the deployment database"
}

Write-Output "Migration revision: $($migration.Trim())"
Write-Output "Deployment live/readiness and migration checks passed"
