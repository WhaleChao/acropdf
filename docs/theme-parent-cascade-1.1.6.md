# PDF-parented dialog theme correction — 1.1.6

A real sticky-note dialog opened from a PDF page inherited an unscoped local
`background-color` stylesheet from the viewport and canvas. That local rule
had precedence over the application stylesheet, replacing the button and
input backgrounds. The default button retained its contrasting foreground,
which became dark text on a dark canvas. The 1.1.5 detached dialog test missed
this parent cascade; byte-identical installed files did not prove correctness.

Limit the background override to each canvas widget's object-name selector.
All descendants now receive the application palette and state backgrounds.
The same correction covers other dialogs and menus parented below a PDF page.

The package regression now calls the production StickyNoteTool.mouse_release
and QInputDialog.getText with a real page parent. It checks empty/entered text,
both themes, a live theme change while modal, painted button glyph/background
contrast, input palette, acceptance, annotation insertion and saved PDF content.
Its timer callback closes the modal even on an assertion failure. The previous
standalone button, canvas resize, icon and document-preservation checks remain.

Native macOS source verification passed 16 production button states (minimum
contrast 6.12:1), two annotations saved/reopened, 96 geometry changes and 192
small control icon requests. Installed-package and Windows runner results are
recorded in the release assets. ScreenCaptureKit failed on this Mac, so these
screenshots use the application's own native QWidget rendering. No user PDF
or preferences are used by the verification command.

This remains an unsigned preview for public distribution: macOS uses ad-hoc
signing without Apple notarization; Windows lacks an Authenticode certificate.
