# Kontrollsenter – MSI-innstillinger på Windows via MSI sitt WMI-grensesnitt (root\WMI MSI_ACPI, det samme som
# MSI Center bruker). Get_Data/Set_Data: byte 0 = EC-adresse, byte 1 = verdi (svar: byte 0 = 1 betyr OK).
#
# Trygghet: skriver BARE til faste adresser med faste verdier, og BARE når EC-fastvaren er kjent
# (registerkart fra msi-ec, CONF_G2_10: Vector GP68 HX 12V/13V, 15M1IMS1 / 15M1IMS2).
# Forespørsel: JSON {"ops": [["get", adr], ["fan"], ["set", adr, verdi], ["bit", adr, på]]}
param([string]$Req = "$env:LOCALAPPDATA\Kontrollsenter\msi-req.json",
      [string]$Res = "$env:LOCALAPPDATA\Kontrollsenter\msi-res.json")
$ErrorActionPreference = "Stop"

$FW_OK  = @("15M1IMS1", "15M1IMS2")
$SET_OK = @{
    0xd2 = @(0xc1, 0xc2, 0xc4)                         # ytelsesmodus: comfort, eco, turbo
    0xd4 = @(0x0d, 0x1d, 0x8d)                         # viftemodus: auto, silent, advanced
    0xd7 = @(50..100 | ForEach-Object { $_ -bor 0x80 }) # ladegrense 50–100 %
}
$BIT_OK = @{ 0x98 = 0x80; 0xeb = 0x0f; 0x2e = 0x02 }   # Cooler Boost, Super Battery, webkamera
$READ_OK = @(0xd2, 0xd4, 0xd7, 0x98, 0xeb, 0x2e, 0x68, 0x71, 0x80, 0x89)

function Get-Bytes($r) {
    foreach ($p in $r.Properties) {
        if ($p.Value -and $p.Value.PSObject.Properties["Bytes"]) { return [byte[]]$p.Value.Bytes }
    }
    throw "tomt svar fra MSI_ACPI"
}
function New-Pkg([int]$a, [int]$v) {
    $b = New-Object byte[] 32
    $b[0] = [byte]$a; $b[1] = [byte]$v
    $p = ([wmiclass]"root\WMI:Package_32").CreateInstance()
    $p.Bytes = $b
    return $p
}

$out = [ordered]@{ ok = $true; fw = ""; known = $false; admin = $false; results = @() }
try {
    $out.admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
        [Security.Principal.WindowsBuiltInRole]::Administrator)
    $m = Get-WmiObject -Namespace root\WMI -Class MSI_ACPI | Select-Object -First 1
    if (-not $m) { throw "MSI_ACPI finnes ikke på denne maskinen" }
    try { $ec = Get-Bytes ($m.Get_EC()) } catch { $ec = Get-Bytes ($m.Get_EC((New-Pkg 0 0))) }
    $out.fw = ([Text.Encoding]::ASCII.GetString($ec, 2, 28)).Trim([char]0, ' ')
    foreach ($f in $FW_OK) { if ($out.fw.StartsWith($f)) { $out.known = $true } }

    $ops = @((Get-Content $Req -Raw | ConvertFrom-Json).ops)
    foreach ($op in $ops) {
        $kind = [string]$op[0]
        if ($kind -eq "get") {
            $a = [int]$op[1]
            if ($READ_OK -notcontains $a) { throw "lesing av 0x{0:x2} er ikke tillatt" -f $a }
            $b = Get-Bytes ($m.Get_Data((New-Pkg $a 0)))
            $out.results += , @{ a = $a; s = [int]$b[0]; v = [int]$b[1] }
        } elseif ($kind -eq "fan") {
            $b = Get-Bytes ($m.Get_Fan((New-Pkg 0 0)))
            $rpm = @()
            for ($c = 0; $c -lt 4; $c++) {
                $raw = ([int]$b[$c * 2 + 1] -shl 8) -bor [int]$b[$c * 2 + 2]
                $rpm += $(if ($raw) { [int](480000 / $raw) } else { 0 })
            }
            $out.results += , @{ fan = $rpm }
        } elseif ($kind -eq "set" -or $kind -eq "bit") {
            if (-not $out.known) { throw "EC-fastvaren $($out.fw) er ikke kjent – endrer ingenting" }
            $a = [int]$op[1]
            if ($kind -eq "set") {
                $v = [int]$op[2]
                if (-not $SET_OK.ContainsKey($a) -or $SET_OK[$a] -notcontains $v) {
                    throw "0x{0:x2} = 0x{1:x2} er ikke tillatt" -f $a, $v
                }
            } else {
                if (-not $BIT_OK.ContainsKey($a)) { throw "0x{0:x2} er ikke tillatt" -f $a }
                $cur = Get-Bytes ($m.Get_Data((New-Pkg $a 0)))
                if ($cur[0] -ne 1) { throw "kunne ikke lese 0x{0:x2}" -f $a }
                $mask = $BIT_OK[$a]
                $v = $(if ([bool]$op[2]) { $cur[1] -bor $mask } else { $cur[1] -band (0xff -bxor $mask) })
            }
            $b = Get-Bytes ($m.Set_Data((New-Pkg $a $v)))
            $out.results += , @{ a = $a; s = [int]$b[0]; v = $v }
        }
    }
} catch {
    $out.ok = $false
    $out.error = "$_"
    if ($_.Exception.HResult) { $out.hresult = "0x{0:x8}" -f $_.Exception.HResult }
}
New-Item -ItemType Directory -Force -Path (Split-Path $Res) | Out-Null
$out | ConvertTo-Json -Depth 5 -Compress | Set-Content -Encoding UTF8 $Res
