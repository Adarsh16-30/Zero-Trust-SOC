param(
    [switch]$ForceRecreate
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = Resolve-Path (Join-Path $scriptDir "../..")
$composeFile = Join-Path $scriptDir "prod-stack.yml"
$envFile = Join-Path $scriptDir ".env.prod"

if (-not (Test-Path $envFile)) {
    throw ".env.prod not found at $envFile"
}

# Parse .env.prod and resolve ${VAR} references using values in the same file.
$raw = @{}
Get-Content $envFile | ForEach-Object {
    $line = $_.Trim()
    if (-not $line -or $line.StartsWith("#")) { return }
    $idx = $line.IndexOf("=")
    if ($idx -lt 1) { return }
    $k = $line.Substring(0, $idx)
    $v = $line.Substring($idx + 1)
    $raw[$k] = $v
}

function Resolve-Value([string]$value, [hashtable]$map) {
    $resolved = $value
    $guard = 0
    while ($resolved -match "\$\{([A-Za-z_][A-Za-z0-9_]*)\}" -and $guard -lt 20) {
        $guard++
        $resolved = [regex]::Replace($resolved, "\$\{([A-Za-z_][A-Za-z0-9_]*)\}", {
            param($m)
            $name = $m.Groups[1].Value
            if ($map.ContainsKey($name)) { return $map[$name] }
            return $m.Value
        })
    }
    return $resolved
}

$resolved = @{}
foreach ($k in $raw.Keys) {
    $resolved[$k] = Resolve-Value $raw[$k] $raw
}

# Ensure process environment uses .env.prod values, not shell leftovers.
foreach ($k in $resolved.Keys) {
    [System.Environment]::SetEnvironmentVariable($k, $resolved[$k], "Process")
}

Push-Location $projectRoot
try {
    $args = @("compose", "-f", $composeFile, "--env-file", $envFile, "up", "-d")
    if ($ForceRecreate) {
        $args += "--force-recreate"
    }
    & docker @args
    & docker compose -f $composeFile --env-file $envFile ps
}
finally {
    Pop-Location
}
