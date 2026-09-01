# Update the table-of-contents field and export the report to PDF via Word.
# Kept deliberately minimal: ComputeStatistics and Repaginate force a full
# layout pass and were where the first attempt stalled.

$ErrorActionPreference = "Stop"
$docx = "D:\Seek_My_Services\build\Seek_My_Service_Project_Report.docx"
$pdf  = "D:\Seek_My_Services\build\Seek_My_Service_Project_Report.pdf"

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$word.Options.UpdateFieldsAtPrint = $false

$doc = $word.Documents.Open($docx, $false, $false)

foreach ($toc in $doc.TablesOfContents) { $toc.Update() }

$doc.Save()
$doc.ExportAsFixedFormat($pdf, 17)
$doc.Close(0)
$word.Quit()

[System.Runtime.InteropServices.Marshal]::ReleaseComObject($doc)  | Out-Null
[System.Runtime.InteropServices.Marshal]::ReleaseComObject($word) | Out-Null
[GC]::Collect()

Write-Output "DONE"
