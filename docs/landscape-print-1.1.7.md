# Landscape printing — 1.1.7

The print dialog previously placed paper/orientation near the bottom of a
scrolling form and always started in portrait, even for a landscape PDF page.
Paper and direction now appear directly after printer selection, and the
initial direction follows the current displayed PDF page (including /Rotate).
The selection remains editable and is passed by semantic combo-box data.

Two output defects were reproduced:

- Vector print copies imported an unrotated PDF content stream using the
  rotated page bounds. A 90/270-degree page could be cropped and oriented
  differently from the physical-device path. Normalize /Rotate on the private
  print copy after baking annotations/forms, preserving the source document.
- Annotation-summary printing discarded both selected paper and orientation.
  Apply the shared validated QPageLayout there, including PDF output. Publish
  summary PDF files atomically and refuse overwriting the current source PDF.

Physical PDF printing applies paper and direction together as a QPageLayout
and rejects a driver refusing the layout before submitting a print job.

Verification uses generated, colored corner markers on four rotated pages.
The actual PrintDialog settings and PrintProgressDialog worker are exercised
for A4, A3, Letter and Legal, each portrait and landscape. Checks include the
visibility of the direction selector, page geometry, text, all corner markers,
source bytes and rotation, Qt PDF device output, and the actual summary print
entry point with Letter landscape. On this Mac, NativeFormat is also tested
through the installed default printer driver with an explicit file destination;
no physical print job is submitted. The packaged native verification command
includes these checks, alongside the existing theme/geometry regression.

A physical paper feed and driver firmware behavior still require a device
print; automated verification does not claim that a physical sheet was tested.
The public release remains a preview without Apple notarization or Windows
Authenticode signing.
