$ErrorActionPreference = 'Stop'
$target = 'E:\workbuddy\国外模型'
$link   = 'E:\workbuddy\hermes-models'
if (Test-Path $link) {
    $out = 'WARN|link already exists|' + $link
    $out | Out-File -FilePath 'E:\workbuddy\hermes-models\hermes\scripts\_fix_junction_result.txt' -Encoding ascii
    exit 0
}
New-Item -ItemType Junction -Path $link -Target $target | Out-Null
[Environment]::SetEnvironmentVariable('HERMES_HOME', $link, 'User')
$new = [Environment]::GetEnvironmentVariable('HERMES_HOME', 'User')
$scriptResolves = Test-Path (Join-Path $link 'hermes\scripts\gateway_401_selfheal.py')
$out = ('OK|link=' + $link + '|target=' + $target + '|HERMES_HOME=' + $new + '|scriptResolves=' + $scriptResolves)
$out | Out-File -FilePath 'E:\workbuddy\hermes-models\hermes\scripts\_fix_junction_result.txt' -Encoding ascii
