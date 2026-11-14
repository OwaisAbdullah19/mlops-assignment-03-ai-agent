# Load plain KEY=value entries without evaluating shell code.
Get-Content -LiteralPath (Join-Path $PSScriptRoot '..\.env') | ForEach-Object {
    $entry = $_.Trim()
    if ($entry -and -not $entry.StartsWith('#')) {
        $parts = $entry.Split('=', 2)
        if ($parts.Count -eq 2 -and $parts[0] -match '^[A-Z][A-Z0-9_]*$') {
            [Environment]::SetEnvironmentVariable($parts[0], $parts[1], 'Process')
        }
    }
}
