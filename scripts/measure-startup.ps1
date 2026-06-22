param(
    [Parameter(Mandatory = $true)]
    [string]$Executable,
    [int]$Runs = 3,
    [int]$TimeoutSeconds = 120,
    [int]$MaxReadyMs = 2000,
    [int]$MaxPrivateMb = 30
)

$ErrorActionPreference = "Stop"
$resolved = (Resolve-Path -LiteralPath $Executable).Path
$results = @()

for ($run = 1; $run -le $Runs; $run++) {
    $startInfo = [System.Diagnostics.ProcessStartInfo]::new()
    $startInfo.FileName = $resolved
    $startInfo.UseShellExecute = $false
    $startInfo.RedirectStandardInput = $true
    $startInfo.RedirectStandardOutput = $true
    $startInfo.RedirectStandardError = $true
    $startInfo.CreateNoWindow = $true

    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    $process = [System.Diagnostics.Process]::Start($startInfo)
    $lineTask = $process.StandardOutput.ReadLineAsync()
    if (-not $lineTask.Wait([TimeSpan]::FromSeconds($TimeoutSeconds))) {
        $process.Kill($true)
        throw "Run $run did not emit a ready message within $TimeoutSeconds seconds."
    }
    $line = $lineTask.Result
    $stopwatch.Stop()
    $process.Refresh()
    $privateMb = [math]::Round($process.PrivateMemorySize64 / 1MB, 1)
    $workingSetMb = [math]::Round($process.WorkingSet64 / 1MB, 1)
    $results += [pscustomobject]@{
        Run = $run
        ReadyMs = $stopwatch.ElapsedMilliseconds
        PrivateMb = $privateMb
        WorkingSetMb = $workingSetMb
        Threads = $process.Threads.Count
        ReadyMessage = $line
    }
    $process.StandardInput.Close()
    if (-not $process.WaitForExit(5000)) {
        $process.Kill($true)
    }
}

$runtime = Get-Item -LiteralPath $resolved
$runtimeFiles = Get-ChildItem -LiteralPath $runtime.DirectoryName -Recurse -File
$summary = [pscustomobject]@{
    Executable = $resolved
    Runs = $Runs
    MaxReadyMs = ($results | Measure-Object ReadyMs -Maximum).Maximum
    MaxPrivateMb = ($results | Measure-Object PrivateMb -Maximum).Maximum
    RuntimeFiles = $runtimeFiles.Count
    RuntimeMb = [math]::Round(($runtimeFiles | Measure-Object Length -Sum).Sum / 1MB, 1)
}

$results | Format-Table Run, ReadyMs, PrivateMb, WorkingSetMb, Threads -AutoSize
$summary | Format-List

if ($summary.MaxReadyMs -gt $MaxReadyMs) {
    throw "Startup gate failed: $($summary.MaxReadyMs)ms exceeds ${MaxReadyMs}ms."
}
if ($summary.MaxPrivateMb -gt $MaxPrivateMb) {
    throw "Memory gate failed: $($summary.MaxPrivateMb)MB exceeds ${MaxPrivateMb}MB."
}

