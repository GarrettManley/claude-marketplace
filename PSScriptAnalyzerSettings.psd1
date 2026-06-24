# PSScriptAnalyzer configuration for the marketplace's PowerShell scripts.
#
# Used by scripts/verify.sh's PowerShell leg (when pwsh + PSScriptAnalyzer are
# available) and by the Windows leg of ci.yml. Gate severity is Warning+Error.
#
# The three excluded rules are deliberate, with rationale:
#
#   PSUseBOMForUnicodeEncodedFile — the scripts contain non-ASCII characters (the
#       em-dash in "[init:<plugin>] <STATE> — <detail>" status lines, matching the
#       bash siblings). The repo standardizes on UTF-8 *without* BOM; the documented
#       target shell is PowerShell 7+, which reads UTF-8 no-BOM correctly. Adding
#       BOMs would diverge from the .sh/.py corpus encoding for no benefit here.
#
#   PSAvoidUsingWriteHost — register_nightly.ps1 is an interactive installer that
#       writes colored, unconditional status directly to the console; Write-Host is
#       the correct tool for that and its output is never meant to be captured.
#
#   PSReviewUnusedParameter — false-positive for the init.ps1 -Force/-Quiet switches,
#       which ARE honored but only inside nested helper functions (Write-StatusLine /
#       Copy-IfAbsent) via PowerShell's dynamic scope; PSSA's per-scope analysis does
#       not see the cross-scope use.
@{
    Severity     = @('Error', 'Warning')
    ExcludeRules = @(
        'PSUseBOMForUnicodeEncodedFile'
        'PSAvoidUsingWriteHost'
        'PSReviewUnusedParameter'
    )
}
